import logging

from sqlalchemy.orm import Session
from typing import Optional, Dict
from ..core.models import Component, Attribute, AttributeValue, ComponentType, PriceHistory
from datetime import datetime
from ..core.logging import get_logger

logger = get_logger("saver", "logs/saver.log", level=logging.DEBUG, mode='a')

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

    comp = db.query(Component).filter_by(dns_url=dns_url).first()
    if comp:
        comp.name = component_name
        comp.updated_at = datetime.utcnow()
        logger.debug(f"Обновлён компонент: {component_name}")
    else:
        comp = Component(
            type_id=type_id_value,
            name=component_name,
            dns_url=dns_url
        )
        db.add(comp)
        db.flush()
        logger.info(f"Добавлен новый компонент: {component_name}")

    if price is not None:
        price_history = PriceHistory(
            component_id=comp.id,
            price=price,
            timestamp=datetime.utcnow()
        )
        db.add(price_history)
        logger.debug(f"Добавлена цена {price} для компонента {comp.id}")

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
    return comp