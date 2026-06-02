from sqlalchemy.orm import Session
from typing import Optional, Dict
from datetime import datetime
import re
from ..core.models import Product, Attribute, AttributeValue, ProductType, PriceHistory, Model, ModelScore
from ..core.logging import get_logger
from ..calculators.benefit import update_benefit_for_product

logger = get_logger("saver", "logs/saver.log", mode='w')

def normalize_gpu_model(raw_model: str) -> str:
    """
    Нормализует название GPU до вида 'GeForce RTX 5060' или 'Radeon RX 7650 GRE'.
    Удаляет производителя, дополнительные слова вроде OC, Dual, Ventus и т.п.
    """
    # Паттерны для NVIDIA
    nvidia_patterns = [
        r'(GeForce\s+RTX\s+\d{3,4}\s*(?:Ti|SUPER)?)',
        r'(GeForce\s+GTX\s+\d{3,4}\s*(?:Ti)?)'
    ]
    # Паттерны для AMD
    amd_patterns = [
        r'(Radeon\s+RX\s+\d{4}\s*(?:GRE|XT)?)',
        r'(Radeon\s+RX\s+\d{3}\s*(?:XT)?)',
        r'(Radeon\s+VII)',
        r'(Radeon\s+HD\s+\d{4})'
    ]
    for pattern in nvidia_patterns + amd_patterns:
        match = re.search(pattern, raw_model, re.IGNORECASE)
        if match:
            # Приводим к правильному регистру: Radeon RX 7650 GRE
            result = match.group(0).strip()
            # Можно дополнительно привести первые буквы к верхнему регистру
            return result
    # Если ничего не найдено, возвращаем исходную строку, но удаляем квадратные скобки и лишнее
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

    model_name = specs.get("Модель") or product_name.split('[')[0].strip()

    model = None
    if model_name and type_name in ("CPU", "GPU"):
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

    # Характеристики (сохраняем все, как есть)
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

    db.commit()
    logger.info(f"Сохранён продукт {product_name} с {len(specs)} характеристиками")

    update_benefit_for_product(product, db)
    return product