# scripts/analyze_cpu_tdp.py
import sys
from pathlib import Path
from collections import defaultdict
import re

sys.path.insert(0, str(Path(__file__).parent.parent))

from dnsight.core.database import get_db
from dnsight.core.models import ProductType, Product, Attribute, AttributeValue


def extract_tdp(value: str) -> int:
    """Извлекает число из строки типа '125 Вт', '95W', '65 Вт'."""
    match = re.search(r'\d+', value)
    return int(match.group()) if match else 0


def analyze_cpu_tdp():
    db = get_db()
    cpu_type = db.query(ProductType).filter_by(name="CPU").first()
    if not cpu_type:
        print("Тип 'CPU' не найден в БД.")
        return

    tdp_attr = db.query(Attribute).filter_by(name="Тепловыделение (TDP)").first()
    if not tdp_attr:
        print("Атрибут 'Тепловыделение (TDP)' не найден.")
        return

    cpu_products = db.query(Product).filter_by(type_id=cpu_type.id).all()
    print(f"Всего процессоров: {len(cpu_products)}\n")

    # Структура: data[tdp][socket] = count
    data = defaultdict(lambda: defaultdict(int))
    tdp_missing = []  # процессоры без TDP

    for prod in cpu_products:
        # Сокет
        socket_av = db.query(AttributeValue).filter_by(product_id=prod.id).join(Attribute).filter(Attribute.name == "Сокет").first()
        socket = socket_av.raw_value.strip() if socket_av else "Не указан"

        # TDP
        tdp_av = db.query(AttributeValue).filter_by(product_id=prod.id, attribute_id=tdp_attr.id).first()
        if tdp_av:
            tdp = extract_tdp(tdp_av.raw_value)
            data[tdp][socket] += 1
        else:
            tdp_missing.append(prod)

    if not data and not tdp_missing:
        print("Нет процессоров с атрибутом 'Тепловыделение (TDP)'.")
        return

    # Все сокеты, встречающиеся в данных
    all_sockets = set()
    for sockets in data.values():
        all_sockets.update(sockets.keys())
    all_sockets = sorted(all_sockets)

    # Вывод таблицы для Excel (разделитель табуляция)
    sep = "\t"
    print("=== Таблица для вставки в Excel (разделитель табуляция) ===\n")
    header = ["TDP (Вт)", "Всего"] + all_sockets
    print(sep.join(header))

    # Строки данных (TDP по возрастанию, но можно по убыванию – замените reverse=False на True)
    for tdp in sorted(data.keys(), reverse=False):
        sockets_counts = data[tdp]
        total = sum(sockets_counts.values())
        row = [str(tdp), str(total)] + [str(sockets_counts.get(s, 0)) for s in all_sockets]
        print(sep.join(row))

    # Процессоры без TDP
    if tdp_missing:
        print("\n=== Процессоры без указанного TDP ===")
        print(f"Всего таких процессоров: {len(tdp_missing)}")
        # Можно перечислить названия (раскомментировать при необходимости)
        # for prod in tdp_missing[:10]:  # первые 10, чтобы не засорять вывод
        #     print(f"  {prod.name}")

    # Детальная сводка (для чтения в консоли)
    print("\n=== Детальная сводка по TDP ===")
    for tdp in sorted(data.keys(), reverse=False):
        print(f"TDP: {tdp} Вт")
        sockets_counts = data[tdp]
        total = sum(sockets_counts.values())
        print(f"  Всего: {total}")
        for socket, count in sorted(sockets_counts.items(), key=lambda x: x[1], reverse=True):
            print(f"    {socket}: {count}")
        print()


if __name__ == "__main__":
    analyze_cpu_tdp()