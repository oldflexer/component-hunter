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

logger = get_logger("passmark", "logs/passmark.log", mode='a')


class PassMarkParser:
    def __init__(self, headless: bool = False):
        self.driver = None
        self.headless = headless
        self.cpu_base_url = "https://www.cpubenchmark.net"
        self.gpu_base_url = "https://www.videocardbenchmark.net"

    def _get_driver(self):
        if self.driver is None:
            options = uc.ChromeOptions()
            if self.headless:
                options.add_argument('--headless')
            options.add_argument('--no-sandbox')
            options.add_argument('--disable-dev-shm-usage')
            self.driver = uc.Chrome(options=options)
            self.driver.set_page_load_timeout(REQUEST_TIMEOUT)
            logger.info("Инициализирован ChromeDriver для PassMark")
        return self.driver

    def _search_cpu(self, model_name: str) -> Optional[float]:
        driver = self._get_driver()
        mega_page_url = f"{self.cpu_base_url}/CPU_mega_page.html"
        driver.get(mega_page_url)

        try:
            search_input = WebDriverWait(driver, 15).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "input#search_name"))
            )
        except Exception as e:
            logger.warning(f"Не найдено поле поиска #search_name на CPU Mega Page: {e}")
            return None

        search_input.clear()
        search_input.send_keys(model_name)
        time.sleep(random.uniform(1.5, 3.0))

        try:
            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "#cputable tbody tr"))
            )
        except Exception as e:
            logger.warning(f"Таблица с результатами не загрузилась для CPU {model_name}: {e}")
            return None

        soup = BeautifulSoup(driver.page_source, 'lxml')
        first_row = soup.select_one("#cputable tbody tr")
        if not first_row:
            logger.debug(f"Нет строк в таблице для CPU {model_name}")
            return None

        # CPU Mark находится в 4-м столбце (индекс 3)
        columns = first_row.find_all("td")
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
            search_input = WebDriverWait(driver, 15).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "input#search_name"))
            )
        except Exception as e:
            logger.warning(f"Не найдено поле поиска #search_name на GPU Mega Page: {e}")
            return None

        search_input.clear()
        search_input.send_keys(model_name)
        time.sleep(random.uniform(1.5, 3.0))

        try:
            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "#gputable tbody tr"))
            )
        except Exception as e:
            logger.warning(f"Таблица с результатами не загрузилась для GPU {model_name}: {e}")
            return None

        soup = BeautifulSoup(driver.page_source, 'lxml')
        first_row = soup.select_one("#gputable tbody tr")
        if not first_row:
            logger.debug(f"Нет строк в таблице для GPU {model_name}")
            return None

        # G3D Mark находится в 3-м столбце (индекс 2)
        columns = first_row.find_all("td")
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