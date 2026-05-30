from sqlalchemy.orm import Session
from typing import Optional, Dict
from datetime import datetime
from ..core.models import Component, Attribute, AttributeValue, ComponentType, PriceHistory, Model, ModelScore
from ..core.logging import get_logger
from ..parsers.passmark import PassMarkParser
from ..calculators.benefit import update_benefit_for_component   # <-- добавить

logger = get_logger("saver", "logs/saver.log", mode='a')

_score_cache = {}

def ensure_component_type(db: Session, type_name: str) -> ComponentType:
    ct = db.query(ComponentType).filter_by(name=type_name).first()
    if not ct:
        ct = ComponentType(name=type_name)
        db.add(ct)
        db.flush()
        logger.info(f"Создан новый тип компонента: {type_name}")
    return ct

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
    return score_record.score if score_record else None

def update_model_score(db: Session, model_id: int, score: float, source: str = "passmark") -> None:
    last_score = get_latest_model_score(db, model_id)
    if last_score == score:
        return
    new_score = ModelScore(model_id=model_id, score=score, source=source, updated_at=datetime.utcnow())
    db.add(new_score)
    db.flush()
    logger.info(f"Обновлён скор модели ID {model_id}: {score} ({source})")

def save_component_and_attributes(
    db: Session,
    type_name: str,
    component_name: str,
    dns_url: str,
    price: Optional[float],
    specs: Dict[str, str]
) -> Component:
    comp_type = ensure_component_type(db, type_name)
    type_id_value = comp_type.id

    # Извлечение названия модели
    model_name = None
    if "Модель" in specs:
        model_name = specs["Модель"].strip()
    else:
        raw_name = component_name.split('[')[0].strip()
        model_name = raw_name

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

    # Сохранение компонента
    comp = db.query(Component).filter_by(dns_url=dns_url).first()
    if comp:
        comp.name = component_name
        comp.updated_at = datetime.utcnow()
        if model:
            comp.model_id = model.id
    else:
        comp = Component(
            type_id=type_id_value,
            model_id=model.id if model else None,
            name=component_name,
            dns_url=dns_url
        )
        db.add(comp)
        db.flush()
        logger.info(f"Добавлен новый компонент: {component_name}")

    # Цена
    if price is not None:
        price_history = PriceHistory(
            component_id=comp.id,
            price=price,
            timestamp=datetime.utcnow()
        )
        db.add(price_history)
        logger.debug(f"Добавлена цена {price} для компонента {comp.id}")

    # Характеристики
    for attr_name, value in specs.items():
        attr = ensure_attribute(db, attr_name, type_id_value)
        existing = db.query(AttributeValue).filter_by(
            component_id=comp.id,
            attribute_id=attr.id
        ).first()
        if existing:
            existing.value_raw = value
            existing.updated_at = datetime.utcnow()
        else:
            attr_value = AttributeValue(
                component_id=comp.id,
                attribute_id=attr.id,
                value_raw=value
            )
            db.add(attr_value)
            logger.debug(f"Добавлено значение атрибута '{attr_name}' = '{value}'")

    db.commit()
    logger.info(f"Сохранён компонент {component_name} с {len(specs)} характеристиками")

    # Добавляем расчёт Benefit для этого компонента
    update_benefit_for_component(comp, db)

    return comp