# scripts/recalc_psu_scores.py
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dnsight.core.database import get_db
from dnsight.core.models import ProductType, Product, Model, ModelScore, AttributeValue
from dnsight.workers.saver import calculate_psu_score
from dnsight.config.attributes import ATTR_MODEL


def recalc_psu_scores():
    db = get_db()
    psu_type = db.query(ProductType).filter_by(name="PSU").first()
    if not psu_type:
        print("Тип 'PSU' не найден в БД.")
        return

    products = db.query(Product).filter_by(type_id=psu_type.id).all()
    print(f"Найдено блоков питания: {len(products)}")

    updated = 0
    for prod in products:
        # Получаем атрибуты
        attrs = db.query(AttributeValue).filter_by(product_id=prod.id).all()
        specs = {av.attribute.name: av.raw_value for av in attrs}

        score = calculate_psu_score(specs)
        if score is None:
            print(f"⚠️ Пропускаем {prod.name} – не удалось вычислить скор")
            continue

        # Проверяем наличие модели
        if prod.model_id:
            model = db.query(Model).filter_by(id=prod.model_id).first()
        else:
            # Пробуем создать модель
            model_name = specs.get(ATTR_MODEL) or prod.name.split('[')[0].strip()
            # Проверяем, не существует ли уже модель с таким именем и типом
            model = db.query(Model).filter_by(name=model_name, type_id=psu_type.id).first()
            if not model:
                model = Model(name=model_name, type_id=psu_type.id)
                db.add(model)
                db.flush()
                prod.model_id = model.id
                db.commit()
                print(f"✅ Создана новая модель: {model_name}")

        if model:
            # Удаляем старые скоры с источником "psu_formula" (опционально)
            db.query(ModelScore).filter_by(model_id=model.id, source="psu_formula").delete()
            new_score = ModelScore(
                model_id=model.id,
                score=score,
                source="psu_formula",
                updated_at=datetime.utcnow()
            )
            db.add(new_score)
            print(f"✅ Обновлён скор {score:.2f} для {model.name}")
            updated += 1

    db.commit()
    print(f"\nОбновлено блоков питания: {updated}")


if __name__ == "__main__":
    from datetime import datetime
    recalc_psu_scores()