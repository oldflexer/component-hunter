# attributes.py
# General
ATTR_SOCKET = "Сокет"
ATTR_MODEL = "Модель"

# CPU
ATTR_CPU_PCIE = "Встроенный контроллер PCI Express"
ATTR_CPU_TDP = "Тепловыделение (TDP)"

# GPU
ATTR_GPU_CHIP = "Графический процессор"

# MB
ATTR_MB_PCIE = "Версия PCI Express"
ATTR_MB_PHASES = "Количество фаз питания"
ATTR_MB_FREQ = "Максимальная частота памяти (JEDEC / без разгона)"
ATTR_MB_MAX_RAM = "Максимальный объем памяти"
ATTR_MB_SLOTS = "Количество слотов памяти"
ATTR_MB_CHANNELS = "Количество каналов памяти"

# RAM
ATTR_RAM_TOTAL = "Суммарный объем памяти всего комплекта"
ATTR_RAM_MODULE = "Объем одного модуля памяти"
ATTR_RAM_ECC = "ECC-память"
ATTR_RAM_FREQ = "Тактовая частота"
ATTR_RAM_CAS = "CAS Latency (CL)"
ATTR_RAM_HEATSINK = "Наличие радиатора"

# PSU
ATTR_PSU_POWER = "Мощность (номинал)"
ATTR_PSU_CERT = "Сертификат 80 PLUS"
ATTR_PSU_STANDARD = "Соответствие стандартам"
ATTR_PSU_PROTECTIONS = "Технологии защиты"
ATTR_PSU_CABLES = "Отстегивающиеся кабели"
ATTR_PSU_SLEEVING = "Оплетка проводов"

# Storage
ATTR_STORAGE_CAPACITY = "Объем накопителя"
ATTR_STORAGE_READ = "Максимальная скорость последовательного чтения"
ATTR_STORAGE_WRITE = "Максимальная скорость последовательной записи"
ATTR_STORAGE_TBW = "Максимальный ресурс записи (TBW)"
ATTR_STORAGE_DWPD = "DWPD"
ATTR_STORAGE_WARRANTY = "Гарантия продавца"
ATTR_STORAGE_WARRANTY_ALT = "Гарантия продавца / производителя"
ATTR_STORAGE_WARRANTY_ALT2 = "Гарантия"