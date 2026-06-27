"""
Модуль обновления скоров PassMark для CPU и GPU.
"""

import time
import pandas as pd
from sqlalchemy.orm import Session

from ..core.database import get_db
from ..core.models import ProductType, Model, ModelScore, Product, Attribute, AttributeValue
from ..core.logging import get_logger
from ..parsers.passmark import PassMarkParser
from ..calculators.benefit import update_benefit_for_product
from ..config.attributes import ATTR_GPU_CHIP

logger = get_logger("passmark_updater", "logs/passmark_updater.log", mode='w')

def get_gpu_attribute_id(db: Session) -> int:
    attr = db.query(Attribute).filter_by(name=ATTR_GPU_CHIP).first()
    if not attr:
        raise ValueError(f"Атрибут '{ATTR_GPU_CHIP}' не найден. Запустите парсинг DNS для GPU.")
    return attr.id

def get_unique_gpu_raw_values(db: Session, attr_id: int) -> list:
    raw_values = db.query(AttributeValue.raw_value).filter_by(attribute_id=attr_id).distinct().all()
    return [rv[0] for rv in raw_values if rv[0]]

def get_model_ids_for_raw_value(db: Session, attr_id: int, raw_value: str) -> list:
    product_ids = db.query(AttributeValue.product_id).filter(
        AttributeValue.attribute_id == attr_id,
        AttributeValue.raw_value == raw_value
    ).distinct().all()
    product_ids = [pid[0] for pid in product_ids]
    if not product_ids:
        return []
    models = db.query(Product.model_id).filter(Product.id.in_(product_ids), Product.model_id.isnot(None)).distinct().all()
    return [m[0] for m in models]

def update_model_scores_and_benefit(db: Session, model_ids: list, score: float) -> None:
    for model_id in model_ids:
        new_score = ModelScore(
            model_id=model_id,
            score=score,
            source="passmark",
            updated_at=pd.Timestamp.now()
        )
        db.add(new_score)
        logger.info(f"Обновлён скор для модели ID {model_id}: {score}")
        products = db.query(Product).filter_by(model_id=model_id).all()
        for prod in products:
            update_benefit_for_product(prod, db)
        db.flush()

def update_passmark_scores(headless: bool = True, update_cpu: bool = True, update_gpu: bool = True) -> None:
    logger.info("Запуск обновления PassMark")
    db = get_db()
    parser = PassMarkParser(headless=headless)

    try:
        # --- Обновление CPU ---
        if update_cpu:
            cpu_type = db.query(ProductType).filter_by(name="CPU").first()
            if cpu_type:
                cpu_models = db.query(Model).filter_by(type_id=cpu_type.id).all()
                if cpu_models:
                    logger.info(f"Найдено CPU моделей для обновления: {len(cpu_models)}")
                    for idx, model in enumerate(cpu_models):
                        score = parser.get_score(model.name, "CPU")
                        if score is not None:
                            new_score = ModelScore(
                                model_id=model.id,
                                score=score,
                                source="passmark",
                                updated_at=pd.Timestamp.now()
                            )
                            db.add(new_score)
                            db.flush()
                            logger.info(f"Обновлён скор CPU {model.name}: {score}")
                            for prod in db.query(Product).filter_by(model_id=model.id).all():
                                update_benefit_for_product(prod, db)
                        else:
                            logger.warning(f"Не удалось получить скор для CPU {model.name}")
                        time.sleep(2)
                        db.commit()
                else:
                    logger.info("Нет CPU моделей в БД")
            else:
                logger.warning("Тип CPU не найден в БД")
        else:
            logger.info("Обновление CPU пропущено (update_cpu=False)")

        # --- Обновление GPU ---
        if update_gpu:
            try:
                gpu_attr_id = get_gpu_attribute_id(db)
            except ValueError as e:
                logger.warning(e)
                gpu_attr_id = None

            if gpu_attr_id:
                raw_values = get_unique_gpu_raw_values(db, gpu_attr_id)
                logger.info(f"Найдено уникальных значений 'Графический процессор': {len(raw_values)}")
                for idx, raw_val in enumerate(raw_values):
                    logger.info(f"[GPU {idx+1}/{len(raw_values)}] Обработка: '{raw_val}'")
                    model_ids = get_model_ids_for_raw_value(db, gpu_attr_id, raw_val)
                    if not model_ids:
                        logger.info(f"Нет продуктов с model_id для raw_value '{raw_val}', пропускаем")
                        continue

                    score = parser.get_score(raw_val, "GPU")
                    if score is not None:
                        update_model_scores_and_benefit(db, model_ids, score)
                        logger.info(f"Обновлены скоры для {len(model_ids)} моделей, значение: {score}")
                    else:
                        logger.warning(f"Не удалось получить скор для GPU: {raw_val}")

                    time.sleep(2)
                    db.commit()
        else:
            logger.info("Обновление GPU пропущено (update_gpu=False)")

    except Exception as e:
        logger.exception("Ошибка при обновлении PassMark")
        raise
    finally:
        parser.close()
        db.close()
        logger.info("Обновление PassMark завершено")

if __name__ == "__main__":
    update_passmark_scores(headless=True)