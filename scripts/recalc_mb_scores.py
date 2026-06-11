import sys
from pathlib import Path

# Добавляем корень проекта в путь поиска модулей
sys.path.insert(0, str(Path(__file__).parent.parent))

from dnsight.core.database import get_db
from dnsight.core.models import ProductType, Product, Model, ModelScore, AttributeValue
from dnsight.workers.saver import calculate_motherboard_score

db = get_db()
mb_type = db.query(ProductType).filter_by(name="Motherboard").first()
if mb_type:
    products = db.query(Product).filter_by(type_id=mb_type.id).all()
    for prod in products:
        attrs = db.query(AttributeValue).filter_by(product_id=prod.id).all()
        specs = {av.attribute.name: av.raw_value for av in attrs}
        score = calculate_motherboard_score(specs)
        if score and prod.model_id:
            model = db.query(Model).filter_by(id=prod.model_id).first()
            if model:
                # Удаляем старые скоры (опционально)
                db.query(ModelScore).filter_by(model_id=model.id).delete()
                new_score = ModelScore(model_id=model.id, score=score, source="dns_mb_formula")
                db.add(new_score)
                print(f"Added score {score} for {model.name}")
    db.commit()
else:
    print("Тип Motherboard не найден в БД.")