import time
import logging
import asyncio
from dnsight.core.database import init_db, get_db
from dnsight.parsers.dns import DNSParser
from dnsight.workers.saver import save_product_and_attributes
from dnsight.core.config import DNS_CATEGORIES
import os
from dnsight.core.logging import setup_logging

os.makedirs("logs", exist_ok=True)
setup_logging(level=logging.INFO, log_file="logs/parser.log", mode='w')

logger = logging.getLogger(__name__)

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
    logger.info(f"Парсинг категории {category_key} -> {type_name}")
    products = parser.parse_category(category_key, max_pages=max_pages, max_items=max_items)
    logger.info(f"Найдено товаров: {len(products)}")
    
    for idx, prod in enumerate(products, 1):
        logger.info(f"[{idx}/{len(products)}] Обработка: {prod['name']}")
        specs = parser.parse_product_details(prod['url'])
        save_product_and_attributes(
            db=db,
            type_name=type_name,
            product_name=prod['name'],
            url=prod['url'],
            price=prod['price'],
            specs=specs
        )
        time.sleep(0.5)
    logger.info(f"Категория {category_key} завершена.\n")

def main():
    logger.info("Запуск парсера DNSight")
    init_db()
    db = get_db()
    parser = DNSParser(headless=True)
    try:
        for cat_key in CATEGORY_TO_TYPE:
            if cat_key not in DNS_CATEGORIES:
                logger.warning(f"Категория {cat_key} отсутствует в конфиге, пропускаем")
                continue
            parse_and_save_category(parser, db, cat_key, max_pages=10, max_items=None)  # все товары
    except Exception as e:
        logger.exception("Критическая ошибка в основном цикле")
    finally:
        parser.close()
    logger.info("Парсинг завершён")

if __name__ == "__main__":
    main()