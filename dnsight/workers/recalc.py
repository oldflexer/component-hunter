from sqlalchemy.orm import Session
from ..core.database import get_db
from ..core.models import ProductType, Product, Model, ModelScore, AttributeValue
from ..core.logging import get_logger
from ..workers.saver import (
    calculate_motherboard_score, calculate_ram_score,
    calculate_psu_score, calculate_storage_score
)
from ..calculators.benefit import update_benefit_for_product
from ..config.attributes import ATTR_MODEL
from datetime import datetime
import time
from datetime import timedelta

logger = get_logger("recalc", "logs/recalc.log", mode='w')

def recalculate_scores(status=None, progress_bar=None, text_callback=None):
    db = get_db()
    try:
        type_functions = [
            ("Motherboard", calculate_motherboard_score),
            ("RAM", calculate_ram_score),
            ("PSU", calculate_psu_score),
            ("Storage", calculate_storage_score),
        ]
        total_types = len(type_functions)
        start_time = time.time()
        total_models_processed = 0
        total_models = 0

        # Предварительный подсчёт общего количества моделей для прогресса
        for type_name, _ in type_functions:
            type_obj = db.query(ProductType).filter_by(name=type_name).first()
            if type_obj:
                # Считаем уникальные модели в этом типе
                model_count = db.query(Model).filter_by(type_id=type_obj.id).count()
                total_models += model_count

        if text_callback:
            text_callback(f"Всего моделей для пересчёта: {total_models}")

        for idx_type, (type_name, calc_func) in enumerate(type_functions, 1):
            if text_callback:
                text_callback(f"Пересчёт {type_name} ({idx_type}/{total_types})")
            elif status:
                status.update(label=f"Пересчёт {type_name} ({idx_type}/{total_types})")

            type_obj = db.query(ProductType).filter_by(name=type_name).first()
            if not type_obj:
                logger.warning(f"Тип {type_name} не найден")
                continue

            # Получаем все модели этого типа
            models = db.query(Model).filter_by(type_id=type_obj.id).all()
            if not models:
                logger.info(f"Нет моделей для {type_name}")
                continue

            updated = 0
            for idx_model, model in enumerate(models, 1):
                # Берём первый продукт модели (любой, т.к. характеристики одинаковы для модели)
                product = db.query(Product).filter_by(model_id=model.id).first()
                if not product:
                    continue

                # Получаем характеристики продукта
                attrs = db.query(AttributeValue).filter_by(product_id=product.id).all()
                specs = {av.attribute.name: av.raw_value for av in attrs}
                score = calc_func(specs)
                if score is None:
                    continue

                # Удаляем старые скоры этого источника
                source = f"dns_{type_name.lower()}_formula"
                db.query(ModelScore).filter_by(model_id=model.id, source=source).delete()
                # Добавляем новый скор
                new_score = ModelScore(
                    model_id=model.id,
                    score=score,
                    source=source,
                    updated_at=datetime.utcnow()
                )
                db.add(new_score)
                updated += 1

                # Пересчитываем Benefit для всех продуктов этой модели
                products_for_model = db.query(Product).filter_by(model_id=model.id).all()
                for prod_model in products_for_model:
                    update_benefit_for_product(prod_model, db)

                # Обновление прогресса (каждые 5 моделей или последняя)
                total_models_processed += 1
                if progress_bar and (idx_model % 5 == 0 or idx_model == len(models)):
                    progress = total_models_processed / total_models if total_models > 0 else 0
                    progress = min(progress, 1.0)
                    elapsed = time.time() - start_time
                    avg_time = elapsed / total_models_processed if total_models_processed > 0 else 0
                    remaining = total_models - total_models_processed
                    eta_seconds = avg_time * remaining
                    eta_str = str(timedelta(seconds=int(eta_seconds))) if eta_seconds > 0 else "< 1 сек"
                    progress_bar.progress(progress)
                    if text_callback:
                        text_callback(f"{type_name}: {total_models_processed}/{total_models}, ETA: {eta_str}")

            db.commit()
            logger.info(f"Обновлено {updated} скоров для {type_name}")

        if text_callback:
            text_callback("✅ Пересчёт завершён!")
        elif status:
            status.update(label="✅ Пересчёт завершён!", state="complete")

    except Exception as e:
        logger.exception("Ошибка пересчёта")
        if text_callback:
            text_callback(f"❌ Ошибка: {e}")
        elif status:
            status.update(label=f"❌ Ошибка: {e}", state="error")
        db.rollback()
        raise
    finally:
        db.close()

if __name__ == "__main__":
    recalculate_scores()