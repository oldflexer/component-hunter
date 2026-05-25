import os
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///dnsight.db")

# Категории для парсинга
DNS_CATEGORIES = {
    "cpu": "https://www.dns-shop.ru/catalog/17a899cd16404e77/processory/",
    "motherboard": "https://www.dns-shop.ru/catalog/17a89a0416404e77/materinskie-platy/",
    "gpu": "https://www.dns-shop.ru/catalog/17a89aab16404e77/videokarty/",
    "ram_dimm": "https://www.dns-shop.ru/catalog/17a89a3916404e77/operativnaa-pamat-dimm/",
    "ram_sodimm": "https://www.dns-shop.ru/catalog/17a9b91b16404e77/operativnaa-pamat-so-dimm/",
    "psu": "https://www.dns-shop.ru/catalog/17a89c2216404e77/bloki-pitania/",
    "case": "https://www.dns-shop.ru/catalog/17a89c5616404e77/korpusa/",
    "cooler": "https://www.dns-shop.ru/catalog/17a9cc2d16404e77/kulery-dla-processorov/",
    "lcs": "https://www.dns-shop.ru/catalog/17a9cc9816404e77/sistemy-zidkostnogo-ohlazdenia/",
    "ssd": "https://www.dns-shop.ru/catalog/8a9ddfba20724e77/ssd-nakopiteli/",
    "ssdm2": "https://www.dns-shop.ru/catalog/dd58148920724e77/ssd-m2-nakopiteli/",
    "hdd35": "https://www.dns-shop.ru/catalog/17a8914916404e77/zestkie-diski-35/",
    "hdd25": "https://www.dns-shop.ru/catalog/f09d15560cdd4e77/zestkie-diski-25/",
}

REQUEST_TIMEOUT = 30
MAX_RETRIES = 3
RETRY_DELAY = 2