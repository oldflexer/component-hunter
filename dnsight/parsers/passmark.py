import re
import time
import random
from typing import Optional

import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup

from ..core.config import REQUEST_TIMEOUT
from ..core.logging import get_logger

logger = get_logger("passmark", "logs/passmark.log", mode='w')


class PassMarkParser:
    def __init__(self, headless: bool = False):
        self.driver = None
        self.headless = headless
        self.cpu_base_url = "https://www.cpubenchmark.net"
        self.gpu_base_url = "https://www.videocardbenchmark.net"

    def _get_driver(self):
        if self.driver is not None:
            return self.driver

        options = uc.ChromeOptions()
        options.page_load_strategy = 'eager'
        if self.headless:
            options.add_argument('--headless')
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        self.driver = uc.Chrome(version_main=148, options=options)
        self.driver.set_page_load_timeout(REQUEST_TIMEOUT)
        time.sleep(5)
        self.driver.switch_to.window(self.driver.current_window_handle)
        logger.info("Инициализирован ChromeDriver для PassMark (версия 148)")
        return self.driver

    def _search_cpu(self, model_name: str) -> Optional[float]:
        driver = self._get_driver()
        mega_page_url = f"{self.cpu_base_url}/CPU_mega_page.html"
        driver.get(mega_page_url)

        try:
            search_input = WebDriverWait(driver, 20).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "input#search_name"))
            )
        except Exception as e:
            logger.warning(f"Не найдено поле поиска #search_name на CPU Mega Page: {e}")
            return None

        search_input.clear()
        search_input.send_keys(model_name)
        time.sleep(random.uniform(5, 10))

        try:
            WebDriverWait(driver, 15).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "#cputable tbody tr"))
            )
        except Exception as e:
            logger.warning(f"Таблица с результатами не загрузилась для CPU {model_name}: {e}")
            return None

        soup = BeautifulSoup(driver.page_source, 'lxml')
        rows = soup.select("#cputable tbody tr")
        if not rows:
            logger.debug(f"Нет строк в таблице для CPU {model_name}")
            return None

        # Ищем строку, где название совпадает с model_name (или частично)
        target_row = None
        for row in rows:
            name_cell = row.select_one("td:nth-child(2)")  # второй столбец — название CPU
            if name_cell:
                name = name_cell.get_text(strip=True)
                if name.lower() == model_name.lower():
                    target_row = row
                    break
        if not target_row:
            # если точного совпадения нет, ищем частичное (модель входит в название)
            for row in rows:
                name_cell = row.select_one("td:nth-child(2)")
                if name_cell:
                    name = name_cell.get_text(strip=True)
                    if model_name.lower() in name.lower():
                        target_row = row
                        break
        if not target_row:
            logger.debug(f"Не найдена строка для CPU {model_name}")
            return None

        columns = target_row.find_all("td")
        if len(columns) < 4:
            logger.debug(f"Недостаточно колонок в таблице для CPU {model_name}")
            return None

        score_cell = columns[3].get_text(strip=True)
        score_text = re.sub(r"[^\d.]", "", score_cell)
        try:
            return float(score_text)
        except ValueError:
            logger.debug(f"Не удалось преобразовать значение '{score_cell}' в число")
            return None

    def _search_gpu(self, model_name: str) -> Optional[float]:
        driver = self._get_driver()
        mega_page_url = f"{self.gpu_base_url}/GPU_mega_page.html"
        driver.get(mega_page_url)

        try:
            search_input = WebDriverWait(driver, 20).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "input#search_name"))
            )
        except Exception as e:
            logger.warning(f"Не найдено поле поиска #search_name на GPU Mega Page: {e}")
            return None

        search_input.clear()
        search_input.send_keys(model_name)
        time.sleep(random.uniform(5, 10))

        try:
            WebDriverWait(driver, 15).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "#cputable tbody tr"))
            )
        except Exception as e:
            logger.warning(f"Таблица с результатами не загрузилась для GPU {model_name}: {e}")
            return None

        soup = BeautifulSoup(driver.page_source, 'lxml')
        rows = soup.select("#cputable tbody tr")
        if not rows:
            logger.debug(f"Нет строк в таблице для GPU {model_name}")
            return None

        # Ищем строку, где название совпадает с search_name (или частично)
        target_row = None
        for row in rows:
            name_cell = row.select_one("td:nth-child(2)")  # второй столбец — название GPU
            if name_cell:
                name = name_cell.get_text(strip=True)
                if name.lower() == model_name.lower():
                    target_row = row
                    break
        if not target_row:
            # частичное совпадение
            for row in rows:
                name_cell = row.select_one("td:nth-child(2)")
                if name_cell:
                    name = name_cell.get_text(strip=True)
                    if model_name.lower() in name.lower():
                        target_row = row
                        break
        if not target_row:
            logger.debug(f"Не найдена строка для GPU {model_name}")
            return None

        columns = target_row.find_all("td")
        if len(columns) < 3:
            logger.debug(f"Недостаточно колонок в таблице для GPU {model_name}")
            return None

        score_cell = columns[2].get_text(strip=True)
        score_text = re.sub(r"[^\d.]", "", score_cell)
        try:
            return float(score_text)
        except ValueError:
            logger.debug(f"Не удалось преобразовать значение '{score_cell}' в число для GPU")
            return None

    def get_score(self, model_name: str, component_type: str) -> Optional[float]:
        if component_type.upper() == "CPU":
            return self._search_cpu(model_name)
        elif component_type.upper() == "GPU":
            return self._search_gpu(model_name)
        else:
            logger.error(f"Неподдерживаемый тип компонента: {component_type}")
            return None

    def close(self):
        if self.driver:
            self.driver.quit()
            logger.info("Драйвер PassMark закрыт")