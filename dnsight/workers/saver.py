from sqlalchemy.orm import Session
from typing import Optional, Dict
from datetime import datetime

from ..core.models import Component, Attribute, AttributeValue, ComponentType, PriceHistory, Model, ModelScore
from ..core.logging import get_logger
# from ..parsers.async_passmark import AsyncPassMarkParser   # временно отключено
from ..calculators.benefit import update_benefit_for_component
import asyncio

logger = get_logger("async_saver", "logs/saver.log", mode='w')

_score_cache = {}


async def ensure_component_type(db: Session, type_name: str) -> ComponentType:
    ct = db.query(ComponentType).filter_by(name=type_name).first()
    if not ct:
        ct = ComponentType(name=type_name)
        db.add(ct)
        db.flush()
        logger.info(f"Создан новый тип: {type_name}")
    return ct


async def ensure_attribute(db: Session, attr_name: str, type_id: Optional[int] = None) -> Attribute:
    attr = db.query(Attribute).filter_by(name=attr_name).first()
    if not attr:
        attr = Attribute(name=attr_name, type_id=type_id)
        db.add(attr)
        db.flush()
    return attr


async def get_or_create_model(db: Session, model_name: str, type_id: int) -> Model:
    model = db.query(Model).filter_by(name=model_name, type_id=type_id).first()
    if not model:
        model = Model(name=model_name, type_id=type_id)
        db.add(model)
        db.flush()
        logger.info(f"Новая модель: {model_name}")
    return model


async def update_model_score(db: Session, model_id: int, score: float, source: str = "passmark"):
    last_score = db.query(ModelScore).filter_by(model_id=model_id).order_by(ModelScore.updated_at.desc()).first()
    if last_score and last_score.score == score:
        return
    new_score = ModelScore(model_id=model_id, score=score, source=source, updated_at=datetime.utcnow())
    db.add(new_score)
    db.flush()
    logger.info(f"Скор модели {model_id}: {score}")


async def save_component_and_attributes(
    db: Session,
    type_name: str,
    component_name: str,
    dns_url: str,
    price: Optional[float],
    specs: Dict[str, str]
) -> Component:
    comp_type = await ensure_component_type(db, type_name)
    type_id_value = comp_type.id

    # Извлечение модели: для GPU приоритет у "Графический процессор"
    model_name = None
    if type_name == "GPU":
        model_name = specs.get("Графический процессор")
        if not model_name:
            model_name = specs.get("Модель")
    else:
        model_name = specs.get("Модель")
    
    if not model_name:
        model_name = component_name.split('[')[0].strip()

    model = None
    if model_name and type_name in ("CPU", "GPU"):
        model = await get_or_create_model(db, model_name, type_id_value)

        # PassMark временно отключён – раскомментировать при необходимости
        """
        if model.id not in _score_cache:
            last_score = db.query(ModelScore).filter_by(model_id=model.id).order_by(ModelScore.updated_at.desc()).first()
            if last_score is not None:
                _score_cache[model.id] = last_score.score
            else:
                parser = AsyncPassMarkParser()
                await parser.start_browser(headless=True)
                try:
                    score = await parser.get_score(model_name, type_name)
                    if score is not None:
                        await update_model_score(db, model.id, score)
                        _score_cache[model.id] = score
                    else:
                        _score_cache[model.id] = None
                finally:
                    await parser.close_browser()
        """

    # Сохраняем компонент
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
        logger.info(f"Новый компонент: {component_name}")

    # Сохраняем цену
    if price is not None:
        price_history = PriceHistory(
            component_id=comp.id,
            price=price,
            timestamp=datetime.utcnow()
        )
        db.add(price_history)

    # Сохраняем характеристики (атрибуты)
    for attr_name, value in specs.items():
        attr = await ensure_attribute(db, attr_name, type_id_value)
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

    db.commit()
    update_benefit_for_component(comp, db)

    logger.info(f"Сохранён компонент {component_name}")
    return comp