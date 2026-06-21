# settings.py
import os
from enum import Enum
from dotenv import load_dotenv

load_dotenv()  # загружаем .env

# --- Переменные из .env с дефолтами ---
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///dnsight.db")

REQUEST_TIMEOUT = int(os.getenv("REQUEST_TIMEOUT", "60"))
MAX_RETRIES = int(os.getenv("MAX_RETRIES", "5"))
RETRY_DELAY = int(os.getenv("RETRY_DELAY", "5"))

CACHE_TTL = int(os.getenv("CACHE_TTL", "3600"))

GPU_TARGET_MULTIPLIER = float(os.getenv("GPU_TARGET_MULTIPLIER", "1.25"))
TDP_PHASE_RATIO = float(os.getenv("TDP_PHASE_RATIO", "10.58"))
INF_REPLACEMENT = float(os.getenv("INF_REPLACEMENT", "0.0"))

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
LOG_FILE = os.getenv("LOG_FILE", "logs/app.log")

# --- DNS категории (можно переопределить через .env) ---
DNS_CATEGORIES = {
    # "cpu": os.getenv("DNS_CPU_URL", "https://www.dns-shop.ru/catalog/17a899cd16404e77/processory/"),
    # "gpu": os.getenv("DNS_GPU_URL", "https://www.dns-shop.ru/catalog/17a89aab16404e77/videokarty/"),
    # "motherboard": os.getenv("DNS_MOTHERBOARD_URL", "https://www.dns-shop.ru/catalog/17a89a0416404e77/materinskie-platy/"),
    "ram_dimm": os.getenv("DNS_RAM_DIMM_URL", "https://www.dns-shop.ru/catalog/17a89a3916404e77/operativnaa-pamat-dimm/"),
    "ram_sodimm": os.getenv("DNS_RAM_SODIMM_URL", "https://www.dns-shop.ru/catalog/17a9b91b16404e77/operativnaa-pamat-so-dimm/"),
    "psu": os.getenv("DNS_PSU_URL", "https://www.dns-shop.ru/catalog/17a89c2216404e77/bloki-pitania/"),
    # "case": os.getenv("DNS_CASE_URL", "https://www.dns-shop.ru/catalog/17a89c5616404e77/korpusa/"),
    # "cooler": os.getenv("DNS_COOLER_URL", "https://www.dns-shop.ru/catalog/17a9cc2d16404e77/kulery-dla-processorov/"),
    # "lcs": os.getenv("DNS_LCS_URL", "https://www.dns-shop.ru/catalog/17a9cc9816404e77/sistemy-zidkostnogo-ohlazdenia/"),
    # "ssd": os.getenv("DNS_SSD_URL", "https://www.dns-shop.ru/catalog/8a9ddfba20724e77/ssd-nakopiteli/"),
    # "ssdm2": os.getenv("DNS_SSDM2_URL", "https://www.dns-shop.ru/catalog/dd58148920724e77/ssd-m2-nakopiteli/"),
    # "hdd35": os.getenv("DNS_HDD35_URL", "https://www.dns-shop.ru/catalog/17a8914916404e77/zestkie-diski-35/"),
    # "hdd25": os.getenv("DNS_HDD25_URL", "https://www.dns-shop.ru/catalog/f09d15560cdd4e77/zestkie-diski-25/"),
}

# --- Константы (не зависят от окружения) ---
class ComponentType(str, Enum):
    CPU = "CPU"
    GPU = "GPU"
    MOTHERBOARD = "Motherboard"
    RAM = "RAM"
    PSU = "PSU"
    CASE = "Case"
    COOLER = "Cooler"
    STORAGE = "Storage"

# Формулы расчёта скора материнской платы (весовые коэффициенты)
MB_SCORE_WEIGHTS = {
    "slots": 1.0,
    "channels": 1.0,
    "max_ram": 1.0,
    "freq": 1.0,
    "pcie": 1.0,
    "phases": 1.0
}

# Конфигурация для дашборда (маппинг ключей категорий на типы)
CATEGORY_MAPPING = {
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

# Коэффициент для расчета динамики (по умолчанию)
DEFAULT_DAYS_BACK = 7