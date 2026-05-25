import time

from dnsight.core.database import init_db, get_db
from dnsight.parsers.dns import DNSParser
from dnsight.workers.saver import save_component_and_attributes
from dnsight.core.config import DNS_CATEGORIES

CATEGORY_TO_TYPE = {
    "cpu": "CPU",
    "gpu": "GPU",
    "motherboard": "Motherboard",
    "ram_dimm": "RAM",
    "ram_sodimm": "RAM",
    "psu": "PSU",
    "case": "Case",
    "cooler": "Cooler",
    "lcs": "Cooler",
    "ssd": "Storage",
    "ssdm2": "Storage",
    "hdd35": "Storage",
    "hdd25": "Storage",
}

def parse_and_save_category(parser, db, category_key: str, max_pages: int = 1, max_items: int = 3):
    type_name = CATEGORY_TO_TYPE[category_key]
    print(f"Парсинг категории {category_key} -> {type_name}")
    products = parser.parse_category(category_key, max_pages=max_pages, max_items=max_items)
    print(f"Найдено товаров: {len(products)}")
    
    for idx, prod in enumerate(products, 1):
        print(f"  [{idx}/{len(products)}] Обработка: {prod['name']}")
        specs = parser.parse_product_details(prod['url'])
        save_component_and_attributes(
            db=db,
            type_name=type_name,
            component_name=prod['name'],
            dns_url=prod['url'],
            price=prod['price'],
            specs=specs
        )
        time.sleep(0.5)
    print(f"Категория {category_key} завершена.\n")

def main():
    init_db()
    db = get_db()
    parser = DNSParser()
    try:
        for cat_key in CATEGORY_TO_TYPE:
            parse_and_save_category(parser, db, cat_key, max_pages=1, max_items=3)
    finally:
        parser.close()

if __name__ == "__main__":
    main()