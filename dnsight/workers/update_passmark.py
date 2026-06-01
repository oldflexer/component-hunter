"""
Модуль обновления скоров PassMark для CPU и GPU.

Запускается отдельно (кнопка "Только PassMark") или в составе полного цикла.
Не зависит от парсинга DNS.
"""

import time
import pandas as pd
from sqlalchemy.orm import Session
from typing import Optional

from ..core.database import get_db
from ..core.models import ProductType, Model, ModelScore, Product
from ..core.logging import get_logger
from ..parsers.passmark import PassMarkParser
from ..calculators.benefit import update_benefit_for_product

logger = get_logger("passmark_updater", "logs/passmark_updater.log", mode='w')


def get_models_to_update(db: Session, max_days_old: int = 7):
    """
    Возвращает список моделей CPU/GPU, у которых нет скора или скор устарел.
    """
    cpu_type = db.query(ProductType).filter_by(name="CPU").first()
    gpu_type = db.query(ProductType).filter_by(name="GPU").first()
    type_ids = []
    if cpu_type:
        type_ids.append(cpu_type.id)
    if gpu_type:
        type_ids.append(gpu_type.id)

    if not type_ids:
        logger.warning("Типы CPU или GPU не найдены в БД. Сначала запустите парсинг DNS.")
        return []

    all_models = db.query(Model).filter(Model.type_id.in_(type_ids)).all()
    models_to_update = []
    for model in all_models:
        last_score = db.query(ModelScore).filter_by(model_id=model.id).order_by(ModelScore.updated_at.desc()).first()
        if last_score is None:
            models_to_update.append(model)
        elif (pd.Timestamp.now() - pd.Timestamp(last_score.updated_at)).days > max_days_old:
            models_to_update.append(model)
    return models_to_update


def update_model_score_and_benefit(db: Session, model: Model, score: float, source: str = "passmark"):
    """
    Сохраняет новый скор модели и пересчитывает Benefit для всех её продуктов.
    """
    # Сохраняем скор
    new_score = ModelScore(
        model_id=model.id,
        score=score,
        source=source,
        updated_at=pd.Timestamp.now()
    )
    db.add(new_score)
    db.flush()
    logger.info(f"Обновлён скор модели {model.name}: {score}")

    # Пересчитываем Benefit для всех продуктов, связанных с этой моделью
    products = db.query(Product).filter_by(model_id=model.id).all()
    for prod in products:
        update_benefit_for_product(prod, db)
        logger.debug(f"Пересчитан Benefit для продукта {prod.name}")


def update_passmark_scores(headless: bool = True, max_days_old: int = 7) -> None:
    """
    Основная функция: получает все модели CPU/GPU, у которых скор отсутствует или устарел,
    запрашивает баллы через PassMarkParser и обновляет БД.
    """
    logger.info("Запуск обновления PassMark")
    db = get_db()
    models = get_models_to_update(db, max_days_old)

    if not models:
        logger.info("Нет моделей для обновления (все скоры свежие)")
        return

    logger.info(f"Найдено моделей для обновления: {len(models)}")
    parser = PassMarkParser(headless=headless)

    try:
        for idx, model in enumerate(models):
            # Получаем тип продукта (CPU или GPU)
            product_type = db.query(ProductType).filter_by(id=model.type_id).first()
            if product_type is None:
                logger.warning(f"Не найден тип для модели {model.name}")
                continue

            logger.info(f"[{idx+1}/{len(models)}] Получение скора для {model.name} ({product_type.name})")
            score = parser.get_score(model.name, product_type.name)

            if score is not None:
                update_model_score_and_benefit(db, model, score)
                logger.info(f"Скор {model.name} = {score}")
            else:
                logger.warning(f"Не удалось получить скор для {model.name}")

            time.sleep(2)  # пауза между запросами
            db.commit()   # фиксируем изменения после каждой модели

    except Exception as e:
        logger.exception("Ошибка при обновлении PassMark")
        raise
    finally:
        parser.close()
        db.close()
        logger.info("Обновление PassMark завершено")


if __name__ == "__main__":
    # Для прямого запуска из командной строки (опционально)
    update_passmark_scores(headless=True)