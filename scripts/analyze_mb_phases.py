# scripts/analyze_mb_phases.py
import sys
from pathlib import Path
from collections import defaultdict
import re

sys.path.insert(0, str(Path(__file__).parent.parent))

from dnsight.core.database import get_db
from dnsight.core.models import ProductType, Product, Attribute, AttributeValue


def extract_first_number(value: str) -> int:
    """Извлекает первое число из строки (например, '20+1+2' → 20)."""
    match = re.search(r'\d+', value)
    return int(match.group()) if match else 0


def analyze_mb_phases():
    db = get_db()
    mb_type = db.query(ProductType).filter_by(name="Motherboard").first()
    if not mb_type:
        print("Тип 'Motherboard' не найден в БД.")
        return

    phases_attr = db.query(Attribute).filter_by(name="Количество фаз питания").first()
    if not phases_attr:
        print("Атрибут 'Количество фаз питания' не найден.")
        return

    mb_products = db.query(Product).filter_by(type_id=mb_type.id).all()

    data = defaultdict(lambda: defaultdict(int))

    for prod in mb_products:
        # Сокет
        socket_av = db.query(AttributeValue).filter_by(product_id=prod.id).join(Attribute).filter(Attribute.name == "Сокет").first()
        socket = socket_av.raw_value.strip() if socket_av else "Не указан"

        # Фазы
        phase_av = db.query(AttributeValue).filter_by(product_id=prod.id, attribute_id=phases_attr.id).first()
        if phase_av:
            first_num = extract_first_number(phase_av.raw_value)
            data[first_num][socket] += 1

    if not data:
        print("Нет материнских плат с атрибутом 'Количество фаз питания'.")
        return

    # Все сокеты (алфавитный порядок для удобства)
    all_sockets = set()
    for sockets in data.values():
        all_sockets.update(sockets.keys())
    all_sockets = sorted(all_sockets)

    # Разделитель — табуляция (копировать в Excel)
    sep = "\t"
    print("=== Таблица для вставки в Excel (разделитель табуляция) ===\n")
    # Заголовок
    header = ["Число фаз", "Всего"] + all_sockets
    print(sep.join(header))

    # Строки данных (числа фаз от большего к меньшему)
    for first_num in sorted(data.keys(), reverse=True):
        sockets_counts = data[first_num]
        total = sum(sockets_counts.values())
        row = [str(first_num), str(total)] + [str(sockets_counts.get(s, 0)) for s in all_sockets]
        print(sep.join(row))

    # Дополнительная сводка (для чтения)
    print("\n=== Детальная сводка по каждому числу фаз ===\n")
    for first_num in sorted(data.keys(), reverse=True):
        print(f"Число фаз: {first_num}")
        sockets_counts = data[first_num]
        total = sum(sockets_counts.values())
        print(f"  Всего плат: {total}")
        for socket, count in sorted(sockets_counts.items(), key=lambda x: x[1], reverse=True):
            print(f"    {socket}: {count}")
        print()


if __name__ == "__main__":
    analyze_mb_phases()