import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dnsight.core.database import get_db
from dnsight.core.models import ProductType, Product
from dnsight.calculators.benefit import update_benefit_for_product

def recalc_benefit_for_types(type_names: list):
    db = get_db()
    for type_name in type_names:
        type_obj = db.query(ProductType).filter_by(name=type_name).first()
        if not type_obj:
            print(f"Тип '{type_name}' не найден в БД.")
            continue
        products = db.query(Product).filter_by(type_id=type_obj.id).all()
        print(f"Обработка типа '{type_name}': {len(products)} продуктов")
        updated = 0
        for prod in products:
            # update_benefit_for_product проверит наличие скор и цены и сохранит benefit_history
            try:
                update_benefit_for_product(prod, db)
                updated += 1
            except Exception as e:
                print(f"Ошибка при обновлении benefit для продукта {prod.id}: {e}")
        db.commit()
        print(f"Обновлено benefit для {updated} продуктов типа '{type_name}'")

if __name__ == "__main__":
    # Можно указать типы, которые нужно пересчитать, или все, но пользователь просил MB, RAM, PSU
    target_types = ["Motherboard", "RAM", "PSU"]
    recalc_benefit_for_types(target_types)