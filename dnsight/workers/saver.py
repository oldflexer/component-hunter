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
    ATTR_MB_MAX_RAM, ATTR_MB_CHANNELS, ATTR_PSU_CABLES, ATTR_PSU_CERT, ATTR_PSU_POWER, ATTR_PSU_PROTECTIONS, ATTR_PSU_SLEEVING, ATTR_PSU_STANDARD, ATTR_RAM_CAS, ATTR_RAM_ECC, ATTR_RAM_FREQ, ATTR_RAM_HEATSINK, ATTR_RAM_MODULE, ATTR_RAM_TOTAL
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
        # Если нет объёма модуля, используем total (иногда этого атрибута нет)
        module = total
        logger.info(f"Объём модуля не найден, используем суммарный: {module}")

    freq_raw = specs.get(ATTR_RAM_FREQ)
    freq = extract_number(freq_raw)
    if freq == 0:
        logger.warning(f"Не удалось извлечь частоту из '{freq_raw}'")
        return None

    cl_raw = specs.get(ATTR_RAM_CAS)
    cl = extract_number(cl_raw)
    if cl == 0:
        logger.warning(f"Не удалось извлечь CAS Latency из '{cl_raw}'")
        return None

    ecc_coeff = get_ecc_coeff(specs.get(ATTR_RAM_ECC))
    heatsink_coeff = get_heatsink_coeff(specs.get(ATTR_RAM_HEATSINK))

    score = total * module * ecc_coeff * freq * (1.0 / cl) * heatsink_coeff
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

    score = power * cert_coeff * standard_coeff * protections_coeff * cables_coeff * sleeving_coeff
    logger.info(f"Вычислен скор для PSU: {score:.2f} (мощность={power}, сертификат={cert_coeff}, "
                f"стандарт={standard_coeff}, защиты={protections_coeff}, кабели={cables_coeff}, оплетка={sleeving_coeff})")
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
            existing_score = db.query(ModelScore).filter_by(model_id=model.id).order_by(ModelScore.updated_at.desc()).first()
            if not existing_score or existing_score.score != score:
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
            existing_score = db.query(ModelScore).filter_by(model_id=model.id).order_by(ModelScore.updated_at.desc()).first()
            if not existing_score or existing_score.score != score:
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
            existing_score = db.query(ModelScore).filter_by(model_id=model.id).order_by(ModelScore.updated_at.desc()).first()
            if not existing_score or existing_score.score != score:
                new_score = ModelScore(
                    model_id=model.id,
                    score=score,
                    source="psu_formula",
                    updated_at=datetime.utcnow()
                )
                db.add(new_score)
                logger.info(f"Добавлен скор {score} для модели PSU {model.name}")

    db.commit()
    logger.info(f"Сохранён продукт {product_name} с {len(specs)} характеристиками")
    update_benefit_for_product(product, db)
    return product