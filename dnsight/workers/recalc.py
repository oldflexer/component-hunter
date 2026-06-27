from sqlalchemy.orm import Session
from ..core.database import get_db
from ..core.models import ProductType, Product, Model, ModelScore, AttributeValue
from ..core.logging import get_logger
from ..workers.saver import calculate_motherboard_score, calculate_ram_score, calculate_psu_score
from ..calculators.benefit import update_benefit_for_product
from ..config.attributes import ATTR_MODEL
from datetime import datetime

logger = get_logger("recalc", "logs/recalc.log", mode='w')

def recalculate_scores():
    db = get_db()
    try:
        for type_name, calc_func in [("Motherboard", calculate_motherboard_score),
                                     ("RAM", calculate_ram_score),
                                     ("PSU", calculate_psu_score)]:
            type_obj = db.query(ProductType).filter_by(name=type_name).first()
            if not type_obj:
                logger.warning(f"Тип {type_name} не найден")
                continue
            products = db.query(Product).filter_by(type_id=type_obj.id).all()
            logger.info(f"Пересчёт для {type_name}: {len(products)} продуктов")
            updated = 0
            for prod in products:
                attrs = db.query(AttributeValue).filter_by(product_id=prod.id).all()
                specs = {av.attribute.name: av.raw_value for av in attrs}
                score = calc_func(specs)
                if score is None:
                    continue
                # Проверяем модель
                if prod.model_id:
                    model = db.query(Model).filter_by(id=prod.model_id).first()
                else:
                    # Создаём модель, если нет
                    model_name = specs.get(ATTR_MODEL) or prod.name.split('[')[0].strip()
                    model = db.query(Model).filter_by(name=model_name, type_id=type_obj.id).first()
                    if not model:
                        model = Model(name=model_name, type_id=type_obj.id)
                        db.add(model)
                        db.flush()
                        prod.model_id = model.id
                        db.commit()
                        logger.info(f"Создана модель {model_name} для {type_name}")
                if model:
                    source = f"dns_{type_name.lower()}_formula"
                    # Удаляем старые скоры этого источника
                    db.query(ModelScore).filter_by(model_id=model.id, source=source).delete()
                    # Добавляем новый скор
                    new_score = ModelScore(
                        model_id=model.id,
                        score=score,
                        source=source,
                        updated_at=datetime.utcnow()
                    )
                    db.add(new_score)
                    db.commit()  # фиксируем скор
                    # Пересчитываем Benefit для всех продуктов этой модели
                    products_for_model = db.query(Product).filter_by(model_id=model.id).all()
                    for prod_model in products_for_model:
                        update_benefit_for_product(prod_model, db)
                    db.commit()  # фиксируем benefit'ы
                    updated += 1
                    logger.info(f"Обновлён скор {score:.2f} для {model.name}, пересчитан Benefit для {len(products_for_model)} продуктов")
            db.commit()
            logger.info(f"Обновлено {updated} скоров для {type_name}")
    except Exception as e:
        logger.exception("Ошибка пересчёта")
        db.rollback()
        raise
    finally:
        db.close()

if __name__ == "__main__":
    recalculate_scores()