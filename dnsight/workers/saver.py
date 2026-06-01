from sqlalchemy.orm import Session
from typing import Optional, Dict
from datetime import datetime
from ..core.models import Product, Attribute, AttributeValue, ProductType, PriceHistory, Model, ModelScore
from ..core.logging import get_logger
from ..parsers.passmark import PassMarkParser
from ..calculators.benefit import update_benefit_for_product   # ниже переименуем

logger = get_logger("saver", "logs/saver.log", mode='w')

_score_cache = {}

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

def get_latest_model_score(db: Session, model_id: int) -> Optional[float]:
    score_record = db.query(ModelScore).filter_by(model_id=model_id).order_by(ModelScore.updated_at.desc()).first()
    return score_record.score if score_record else None # pyright: ignore[reportReturnType]

def update_model_score(db: Session, model_id: int, score: float, source: str = "passmark") -> None:
    last_score = get_latest_model_score(db, model_id)
    if last_score == score:
        return
    new_score = ModelScore(model_id=model_id, score=score, source=source, updated_at=datetime.utcnow())
    db.add(new_score)
    db.flush()
    logger.info(f"Обновлён скор модели ID {model_id}: {score} ({source})")

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

    # Извлечение названия модели
    model_name = specs.get("Модель") or specs.get("Графический процессор")
    if not model_name:
        model_name = product_name.split('[')[0].strip()

    model = None
    if model_name and type_name in ("CPU", "GPU"):
        model = get_or_create_model(db, model_name, type_id_value)
        if model.id not in _score_cache:
            last_score = get_latest_model_score(db, model.id)
            if last_score is not None:
                _score_cache[model.id] = last_score
            else:
                parser = PassMarkParser(headless=True)
                try:
                    score = parser.get_score(model_name, type_name)
                    if score is not None:
                        update_model_score(db, model.id, score, "passmark")
                        _score_cache[model.id] = score
                    else:
                        _score_cache[model.id] = None
                finally:
                    parser.close()

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

    db.commit()
    logger.info(f"Сохранён продукт {product_name} с {len(specs)} характеристиками")

    # Benefit
    update_benefit_for_product(product, db)

    return product