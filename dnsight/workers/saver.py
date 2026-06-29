# saver.py
from sqlalchemy.orm import Session
from typing import Optional, Dict
from datetime import datetime
import re
from ..core.models import Product, Attribute, AttributeValue, ProductType, PriceHistory, Model, ModelScore
from ..core.logging import get_logger
from ..calculators.benefit import update_benefit_for_product
from dnsight.config.attributes import (
    ATTR_GPU_CHIP, ATTR_MB_PCIE, ATTR_MODEL, ATTR_MB_PHASES, ATTR_MB_FREQ,
    ATTR_MB_MAX_RAM, ATTR_MB_CHANNELS, ATTR_PSU_CABLES, ATTR_PSU_CERT, ATTR_PSU_POWER,
    ATTR_PSU_PROTECTIONS, ATTR_PSU_SLEEVING, ATTR_PSU_STANDARD, ATTR_RAM_CAS,
    ATTR_RAM_ECC, ATTR_RAM_FREQ, ATTR_RAM_HEATSINK, ATTR_RAM_MODULE, ATTR_RAM_TOTAL,
    ATTR_STORAGE_CAPACITY, ATTR_STORAGE_READ, ATTR_STORAGE_WRITE,
    ATTR_STORAGE_TBW, ATTR_STORAGE_DWPD, ATTR_STORAGE_WARRANTY,
    ATTR_STORAGE_WARRANTY_ALT, ATTR_STORAGE_WARRANTY_ALT2
)
# from dnsight.config.settings import TDP_PHASE_RATIO  # если нужно

logger = get_logger("saver", "logs/saver.log", mode='w')

def normalize_gpu_model(raw_model: str) -> str:
    """Нормализует название GPU до вида 'GeForce RTX 5060' или 'Radeon RX 7650 GRE'."""
    nvidia_patterns = [
        r'(GeForce\s+RTX\s+\d{3,4}\s*(?:Ti|SUPER)?)',
        r'(GeForce\s+GTX\s+\d{3,4}\s*(?:Ti)?)'
    ]
    amd_patterns = [
        r'(Radeon\s+RX\s+\d{4}\s*(?:GRE|XT)?)',
        r'(Radeon\s+RX\s+\d{3}\s*(?:XT)?)',
        r'(Radeon\s+VII)',
        r'(Radeon\s+HD\s+\d{4})'
    ]
    for pattern in nvidia_patterns + amd_patterns:
        match = re.search(pattern, raw_model, re.IGNORECASE)
        if match:
            return match.group(0).strip()
    return re.sub(r'\s*\[.*?\]', '', raw_model).strip()

def ensure_product_type(db: Session, type_name: str) -> ProductType:
    pt = db.query(ProductType).filter_by(name=type_name).first()
    if not pt:
        pt = ProductType(name=type_name)
        db.add(pt)
        db.flush()
        logger.info(f"Создан новый тип продукта: {type_name}")
    return pt

def ensure_attribute(db: Session, attr_name: str, type_id: Optional[int] = None) -> Attribute:
    attr = db.query(Attribute).filter_by(name=attr_name).first()
    if not attr:
        attr = Attribute(name=attr_name, type_id=type_id)
        db.add(attr)
        db.flush()
        logger.debug(f"Создан новый атрибут: {attr_name}")
    return attr

def get_or_create_model(db: Session, model_name: str, type_id: int) -> Model:
    model = db.query(Model).filter_by(name=model_name, type_id=type_id).first()
    if not model:
        model = Model(name=model_name, type_id=type_id)
        db.add(model)
        db.flush()
        logger.info(f"Создана новая модель: {model_name}")
    return model

def calculate_motherboard_score(specs: Dict[str, str]) -> Optional[float]:
    def extract_number(value: str) -> float:
        if not value:
            return 1.0
        match = re.search(r'(\d+(?:\.\d+)?)', value)
        return float(match.group(1)) if match else 1.0

    def sum_phases(value: str) -> int:
        if not value:
            return 1
        numbers = re.findall(r'\d+', value)
        return sum(int(n) for n in numbers) if numbers else 1

    def find_key_contains(*substrings):
        for key in specs.keys():
            if all(sub in key for sub in substrings):
                return key
        return None

    # Поиск ключей
    channels_key = find_key_contains("Количество каналов памяти")
    if not channels_key:
        channels_key = find_key_contains("Каналы памяти")
    max_ram_key = find_key_contains("Максимальный объем памяти")
    if not max_ram_key:
        max_ram_key = find_key_contains("Макс. объем памяти")
    freq_key = find_key_contains("Максимальная частота памяти", "JEDEC")
    if not freq_key:
        freq_key = find_key_contains("Максимальная частота памяти")
    pcie_key = find_key_contains("Версия PCI Express")
    if not pcie_key:
        pcie_key = find_key_contains("PCI Express")
    phases_key = find_key_contains("Количество фаз питания")
    if not phases_key:
        phases_key = find_key_contains("Фазы питания")

    channels = int(extract_number(specs.get(channels_key))) if channels_key else 1
    max_ram = extract_number(specs.get(max_ram_key)) if max_ram_key else 1.0
    freq = extract_number(specs.get(freq_key)) if freq_key else 1.0
    pcie = extract_number(specs.get(pcie_key)) if pcie_key else 1.0
    phases = sum_phases(specs.get(phases_key)) if phases_key else 1

    score = (channels * max_ram * freq * pcie * phases) ** (1 / 2)
    logger.info(f"Вычислен скор для MB: {score} (каналы={channels}, max_ram={max_ram}, частота={freq}, PCIe={pcie}, фазы={phases})")
    return score

def calculate_ram_score(specs: Dict[str, str]) -> Optional[float]:
    """
    Вычисляет скор оперативной памяти по характеристикам.
    Формула: total * module * ecc_coeff * freq * (1 / cl) * heatsink_coeff
    """
    import os

    def extract_number(value: str) -> float:
        if not value:
            return 0.0
        match = re.search(r'(\d+(?:\.\d+)?)', value)
        return float(match.group(1)) if match else 0.0

    def get_ecc_coeff(value: str) -> float:
        if not value:
            return float(os.getenv("RAM_ECC_NO", "1.0"))
        value = value.strip().lower()
        if "да" in value or "есть" in value or "yes" in value:
            return float(os.getenv("RAM_ECC_YES", "1.5"))
        else:
            return float(os.getenv("RAM_ECC_NO", "1.0"))

    def get_heatsink_coeff(value: str) -> float:
        if not value:
            return float(os.getenv("RAM_HEATSINK_NO", "0.5"))
        value = value.strip().lower()
        if "да" in value or "есть" in value or "yes" in value:
            return float(os.getenv("RAM_HEATSINK_YES", "1.0"))
        else:
            return float(os.getenv("RAM_HEATSINK_NO", "0.5"))

    total_raw = specs.get(ATTR_RAM_TOTAL)
    total = extract_number(total_raw)
    if total == 0:
        logger.warning(f"Не удалось извлечь суммарный объем из '{total_raw}'")
        return None

    module_raw = specs.get(ATTR_RAM_MODULE)
    module = extract_number(module_raw)
    if module == 0:
        module = total
        logger.info(f"Объём модуля не найден, используем суммарный: {module}")

    # --- ИЗМЕНЕНИЯ ЗДЕСЬ: fallback для частоты ---
    freq_raw = specs.get(ATTR_RAM_FREQ)
    freq = extract_number(freq_raw)
    if freq == 0:
        # Пробуем альтернативный ключ "Частота"
        freq_raw_alt = specs.get("Частота")
        if freq_raw_alt:
            freq = extract_number(freq_raw_alt)
            if freq != 0:
                logger.info(f"Частота взята из альтернативного ключа 'Частота': {freq}")
    if freq == 0:
        logger.warning(f"Не удалось извлечь частоту из '{freq_raw}' (и из альтернатив)")
        return None

    cl_raw = specs.get(ATTR_RAM_CAS)
    cl = extract_number(cl_raw)
    if cl == 0:
        logger.warning(f"Не удалось извлечь CAS Latency из '{cl_raw}'")
        return None

    ecc_coeff = get_ecc_coeff(specs.get(ATTR_RAM_ECC))
    heatsink_coeff = get_heatsink_coeff(specs.get(ATTR_RAM_HEATSINK))

    score = (total * module * ecc_coeff * freq * (1.0 / cl) * heatsink_coeff) ** (1 / 1.25)
    logger.info(f"Вычислен скор для RAM: {score:.2f} (total={total}, module={module}, ecc={ecc_coeff}, "
                f"freq={freq}, cl={cl}, heatsink={heatsink_coeff})")
    return score

def calculate_psu_score(specs: Dict[str, str]) -> Optional[float]:
    """
    Вычисляет скор блока питания по характеристикам.
    Формула: power * cert_coeff * standard_coeff * protections_coeff * cables_coeff * sleeving_coeff
    """
    import os

    def extract_number(value: str) -> float:
        if not value:
            return 0.0
        match = re.search(r'(\d+(?:\.\d+)?)', value)
        return float(match.group(1)) if match else 0.0

    def get_cert_coeff(value: str) -> float:
        if not value:
            return float(os.getenv("PSU_CERT_80PLUS_NO", "1.0"))
        # Нормализуем: убираем пробелы, приводим к нижнему регистру
        value = value.strip().lower()
        if "titanium" in value:
            return float(os.getenv("PSU_CERT_80PLUS_TITANIUM", "4.0"))
        elif "platinum" in value:
            return float(os.getenv("PSU_CERT_80PLUS_PLATINUM", "3.5"))
        elif "gold" in value:
            return float(os.getenv("PSU_CERT_80PLUS_GOLD", "3.0"))
        elif "silver" in value:
            return float(os.getenv("PSU_CERT_80PLUS_SILVER", "2.5"))
        elif "bronze" in value:
            return float(os.getenv("PSU_CERT_80PLUS_BRONZE", "2.0"))
        elif "standard" in value:
            return float(os.getenv("PSU_CERT_80PLUS_STANDARD", "1.5"))
        else:
            return float(os.getenv("PSU_CERT_80PLUS_NO", "1.0"))

    def get_standard_coeff(value: str) -> float:
        if not value:
            return 1.0
        # Ищем последнее число вида "2.4"
        matches = re.findall(r'(\d+\.\d+)', value)
        if matches:
            return float(matches[-1])
        matches = re.findall(r'(\d+)', value)
        if matches:
            return float(matches[-1])
        return 1.0

    def get_protections_coeff(value: str) -> float:
        if not value:
            return float(os.getenv("PSU_PROTECTIONS_DEFAULT", "0.5"))
        # Считаем количество элементов через запятую
        items = [item.strip() for item in value.split(',') if item.strip()]
        return float(len(items))

    def get_cables_coeff(value: str) -> float:
        if not value:
            return float(os.getenv("PSU_CABLES_NO", "1.0"))
        value = value.strip().lower()
        if "полностью модульный" in value or "full" in value:
            return float(os.getenv("PSU_CABLES_FULL", "2.0"))
        elif "полумодульный" in value or "semi" in value:
            return float(os.getenv("PSU_CABLES_SEMI", "1.5"))
        else:
            return float(os.getenv("PSU_CABLES_NO", "1.0"))

    def get_sleeving_coeff(value: str) -> float:
        if not value:
            return float(os.getenv("PSU_SLEEVING_NO", "0.5"))
        value = value.strip().lower()
        if "индивидуальная тканевая оплетка" in value or "individual" in value:
            return float(os.getenv("PSU_SLEEVING_INDIVIDUAL", "2.0"))
        elif "защитная оплетка" in value or "protective" in value:
            return float(os.getenv("PSU_SLEEVING_PROTECTIVE", "1.5"))
        elif "оплетка" in value or "sleeved" in value:
            return float(os.getenv("PSU_SLEEVING_YES", "1.0"))
        else:
            return float(os.getenv("PSU_SLEEVING_NO", "0.5"))

    power_raw = specs.get(ATTR_PSU_POWER)
    power = extract_number(power_raw)
    if power == 0:
        logger.warning(f"Не удалось извлечь мощность из '{power_raw}'")
        return None

    cert_coeff = get_cert_coeff(specs.get(ATTR_PSU_CERT))
    standard_coeff = get_standard_coeff(specs.get(ATTR_PSU_STANDARD))
    protections_coeff = get_protections_coeff(specs.get(ATTR_PSU_PROTECTIONS))
    cables_coeff = get_cables_coeff(specs.get(ATTR_PSU_CABLES))
    sleeving_coeff = get_sleeving_coeff(specs.get(ATTR_PSU_SLEEVING))

    score = (power * cert_coeff * standard_coeff * protections_coeff * cables_coeff * sleeving_coeff) ** (1 / 1.25)
    logger.info(f"Вычислен скор для PSU: {score:.2f} (мощность={power}, сертификат={cert_coeff}, "
                f"стандарт={standard_coeff}, защиты={protections_coeff}, кабели={cables_coeff}, оплетка={sleeving_coeff})")
    return score

def extract_number_and_unit(value: str):
    """Извлекает число и единицу измерения из строки, например '960 ГБ' → (960, 'ГБ')."""
    if not value:
        return None, None
    match = re.search(r'([\d.]+)\s*([A-Za-zА-Яа-я/]+)', value)
    if match:
        num = float(match.group(1))
        unit = match.group(2).strip()
        return num, unit
    # если нет единицы, просто число
    match = re.search(r'([\d.]+)', value)
    if match:
        return float(match.group(1)), None
    return None, None

def calculate_storage_score(specs: Dict[str, str]) -> Optional[float]:
    """
    Вычисляет скор накопителя по характеристикам.
    Формула: capacity_GB * read_MBps * write_MBps * tbw_TB * dwpd
    Если TBW или DWPD отсутствуют, пытается вычислить их через "Гарантию продавца" и скорость записи.
    """
    def extract_number_and_unit(value: str):
        if not value:
            return None, None
        match = re.search(r'([\d.]+)\s*([A-Za-zА-Яа-я/]+)', value)
        if match:
            num = float(match.group(1))
            unit = match.group(2).strip()
            return num, unit
        match = re.search(r'([\d.]+)', value)
        if match:
            return float(match.group(1)), None
        return None, None

    def extract_months(value: str) -> Optional[int]:
        """Извлекает количество месяцев из строки вида '24 мес.', '36 мес.', '2 года'."""
        if not value:
            return None
        value = value.strip().strip('.')
        match = re.search(r'(\d+)\s*(мес|месяц|месяца|месяцев|года|год|лет)', value, re.IGNORECASE)
        if match:
            num = int(match.group(1))
            unit = match.group(2).lower()
            if 'мес' in unit:
                return num
            elif 'год' in unit or 'лет' in unit:
                return num * 12
        # Если не удалось, пробуем просто число (считаем месяцами)
        match = re.search(r'(\d+)', value)
        if match:
            return int(match.group(1))
        return None

    def get_value(key, target_unit=None):
        raw = specs.get(key)
        if not raw:
            return None
        num, unit = extract_number_and_unit(raw)
        if num is None:
            return None
        if target_unit == 'GB':
            if unit and ('TB' in unit or 'ТБ' in unit):
                return num * 1000
            return num
        elif target_unit == 'MBps':
            if unit and ('GB' in unit or 'ГБ' in unit or 'G' in unit):
                return num * 1000
            return num
        elif target_unit == 'TB':
            if unit and ('GB' in unit or 'ГБ' in unit):
                return num / 1000
            return num
        elif target_unit == 'dwpd':
            return num
        return num

    capacity = get_value(ATTR_STORAGE_CAPACITY, 'GB')
    read = get_value(ATTR_STORAGE_READ, 'MBps')
    write = get_value(ATTR_STORAGE_WRITE, 'MBps')
    tbw_raw = get_value(ATTR_STORAGE_TBW, 'TB')
    dwpd_raw = get_value(ATTR_STORAGE_DWPD, 'dwpd')

    # Поиск гарантии по нескольким возможным ключам
    warranty_raw = None
    for key in [ATTR_STORAGE_WARRANTY, ATTR_STORAGE_WARRANTY_ALT, ATTR_STORAGE_WARRANTY_ALT2]:
        if key in specs:
            warranty_raw = specs[key]
            break

    tbw = tbw_raw
    dwpd = dwpd_raw

    # Если TBW отсутствует, пробуем вычислить по гарантии и скорости записи
    if tbw is None and warranty_raw and write is not None:
        months = extract_months(warranty_raw)
        if months is not None:
            # гарантия в секундах: месяцы * 2592000 (30 дней * 24 * 3600)
            warranty_seconds = months * 2592000
            tbw = (warranty_seconds * write / 1048576) ** 0.5
            logger.info(f"TBW вычислен по гарантии: {tbw:.2f} (месяцы={months}, write={write})")

    # Если DWPD отсутствует, пробуем вычислить по TBW, ёмкости и гарантии
    if dwpd is None and tbw is not None and capacity is not None:
        if warranty_raw:
            months = extract_months(warranty_raw)
            if months is not None:
                warranty_years = months / 12
                capacity_tb = capacity / 1000
                if capacity_tb > 0 and warranty_years > 0:
                    dwpd = tbw / (capacity_tb * 365 * warranty_years)
                    logger.info(f"DWPD вычислен: {dwpd:.4f} (TBW={tbw}, capacity={capacity}GB, warranty={months}мес)")
                else:
                    # Альтернативный вариант: используем дни
                    warranty_days = months * 30
                    dwpd = tbw / (capacity * warranty_days)
                    logger.info(f"DWPD вычислен (альт.): {dwpd:.4f} (TBW={tbw}, capacity={capacity}GB, days={warranty_days})")

    if None in (capacity, read, write, tbw, dwpd):
        logger.warning(f"Недостаточно данных для Storage: capacity={capacity}, read={read}, write={write}, tbw={tbw}, dwpd={dwpd}")
        return None

    score = capacity * read * write * tbw * dwpd
    logger.info(f"Вычислен скор для Storage: {score:.2f} (capacity={capacity} GB, read={read} MB/s, write={write} MB/s, tbw={tbw} TB, dwpd={dwpd})")
    return score

def save_product_and_attributes(
    db: Session,
    type_name: str,
    product_name: str,
    url: str,
    price: Optional[float],
    specs: Dict[str, str]
) -> Product:
    prod_type = ensure_product_type(db, type_name)
    type_id_value = prod_type.id

    model_name = None

    if type_name == "GPU":
        raw_model = specs.get(ATTR_GPU_CHIP)
        if raw_model:
            model_name = normalize_gpu_model(raw_model)

    # Для CPU и MB используем атрибут "Модель"
    if not model_name:
        model_name = specs.get(ATTR_MODEL)

    model = None
    if model_name and type_name in ("CPU", "GPU", "Motherboard", "RAM", "PSU", "Storage", "Case", "Cooler"):
        model = get_or_create_model(db, model_name, type_id_value)

    # Сохранение продукта
    product = db.query(Product).filter_by(url=url).first()
    if product:
        product.name = product_name
        product.updated_at = datetime.utcnow()
        if model:
            product.model_id = model.id
    else:
        product = Product(
            type_id=type_id_value,
            model_id=model.id if model else None,
            name=product_name,
            url=url
        )
        db.add(product)
        db.flush()
        logger.info(f"Добавлен новый продукт: {product_name}")

    # Цена
    if price is not None:
        price_history = PriceHistory(
            product_id=product.id,
            price=price,
            timestamp=datetime.utcnow()
        )
        db.add(price_history)
        logger.debug(f"Добавлена цена {price} для продукта {product.id}")

    # Характеристики
    for attr_name, value in specs.items():
        attr = ensure_attribute(db, attr_name, type_id_value)
        existing = db.query(AttributeValue).filter_by(
            product_id=product.id,
            attribute_id=attr.id
        ).first()
        if existing:
            existing.raw_value = value
            existing.updated_at = datetime.utcnow()
        else:
            attr_value = AttributeValue(
                product_id=product.id,
                attribute_id=attr.id,
                raw_value=value
            )
            db.add(attr_value)
            logger.debug(f"Добавлено значение атрибута '{attr_name}' = '{value}'")

    # Для MB вычисляем и сохраняем скор
    if type_name == "Motherboard" and model:
        score = calculate_motherboard_score(specs)
        if score is not None:
            new_score = ModelScore(
                model_id=model.id,
                score=score,
                source="dns_mb_formula",
                updated_at=datetime.utcnow()
            )
            db.add(new_score)
            logger.info(f"Добавлен скор {score} для модели MB {model.name}")

    # Для RAM вычисляем скор
    if type_name == "RAM" and model:
        score = calculate_ram_score(specs)
        if score is not None:
            new_score = ModelScore(
                model_id=model.id,
                score=score,
                source="ram_formula",
                updated_at=datetime.utcnow()
            )
            db.add(new_score)
            logger.info(f"Добавлен скор {score} для модели RAM {model.name}")

    # Для PSU вычисляем скор
    if type_name == "PSU" and model:
        score = calculate_psu_score(specs)
        if score is not None:
            new_score = ModelScore(
                model_id=model.id,
                score=score,
                source="psu_formula",
                updated_at=datetime.utcnow()
            )
            db.add(new_score)
            logger.info(f"Добавлен скор {score} для модели PSU {model.name}")

    # Для Storage вычисляем скор
    if type_name == "Storage" and model:
        score = calculate_storage_score(specs)
        if score is not None:
            new_score = ModelScore(
                model_id=model.id,
                score=score,
                source="dns_storage_formula",
                updated_at=datetime.utcnow()
            )
            db.add(new_score)
            logger.info(f"Добавлен скор {score} для модели Storage {model.name}")

    db.commit()
    logger.info(f"Сохранён продукт {product_name} с {len(specs)} характеристиками")
    update_benefit_for_product(product, db)
    return product