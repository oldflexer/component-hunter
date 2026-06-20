import logging
import random
import time
import re
from typing import List, Dict, Optional

import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
from bs4 import BeautifulSoup

from ..config.settings import DNS_CATEGORIES, REQUEST_TIMEOUT
from ..core.logging import get_logger


class DNSParser:
    def __init__(self, log_file="logs/parser.log", log_level=logging.DEBUG, headless: bool = False):
        self.logger = get_logger("parser", log_file, level=log_level, mode='w')
        self.base_url = "https://www.dns-shop.ru"
        self.driver = None
        self.headless = headless

    def _get_driver(self):
        if self.driver is not None:
            return self.driver

        options = uc.ChromeOptions()
        if self.headless:
            options.add_argument('--headless')
        options.page_load_strategy = 'eager'
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        
        self.driver = uc.Chrome(version_main=149, options=options)
        self.driver.set_page_load_timeout(REQUEST_TIMEOUT)
        time.sleep(random.uniform(5, 10))
        self.driver.switch_to.window(self.driver.current_window_handle)
        self.logger.info(f"undetected ChromeDriver инициализирован (версия 148, eager strategy, headless={self.headless})")
        
        return self.driver

    def parse_category(self, category_key: str, max_pages: Optional[int] = None, max_items: Optional[int] = None) -> List[Dict]:
        if category_key not in DNS_CATEGORIES:
            raise ValueError(f"Unknown category: {category_key}")

        url = DNS_CATEGORIES[category_key]
        driver = self._get_driver()

        for attempt in range(3):
            try:
                driver.get(url)
                break
            except Exception as e:
                self.logger.warning(f"Ошибка загрузки {url}, попытка {attempt+1}/3: {e}")
                time.sleep(random.uniform(5, 10))
        else:
            self.logger.error(f"Не удалось загрузить {url} после 3 попыток")
            return []

        # --- Смена города на "Каменск-Уральский" ---
        try:
            # 1. Кликнуть на текущий город (Москва)
            city_selector = 'span.city-select__text_90n, span[data-analytics-city-id], span[class*="city-select__text"]'
            city_element = WebDriverWait(driver, 30).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, city_selector))
            )
            city_element.click()
            self.logger.info("Кликнут текущий город, ожидаем модальное окно")
            time.sleep(random.uniform(5, 10))

            # 2. Найти поле ввода города
            input_selector = 'input[data-city-select="city-modal-input-attr"], input[placeholder="Найти город"]'
            city_input = WebDriverWait(driver, 30).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, input_selector))
            )
            city_input.clear()
            city_input.send_keys("Каменск-Уральский")
            self.logger.info("Введён город 'Каменск-Уральский'")
            time.sleep(random.uniform(5, 10))

            # 3. Найти кнопку с нужным городом и кликнуть
            target_button = WebDriverWait(driver, 30).until(
                EC.element_to_be_clickable((By.XPATH, "//button//mark[contains(text(),'Каменск-Уральский')]/ancestor::button"))
            )
            target_button.click()
            self.logger.info("Выбран город 'Каменск-Уральский'")
            time.sleep(random.uniform(5, 10))  # ожидание перезагрузки страницы
        except Exception as e:
            self.logger.warning(f"Не удалось сменить город: {e}. Продолжаем с текущим городом.")

        # --- Далее существующий код парсинга ---
        self.logger.info(f"Начинаем парсинг категории {category_key} (бесконечная прокрутка)")

        products = []
        seen_urls = set()
        last_height = 0
        scroll_attempts = 0

        # Ждём появления первых карточек
        try:
            WebDriverWait(driver, 30).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, 'div.catalog-product'))
            )
        except TimeoutException:
            self.logger.warning("Не удалось загрузить товары")
            return []

        def parse_current_page():
            nonlocal products, seen_urls
            soup = BeautifulSoup(driver.page_source, 'lxml')
            cards = soup.select('div.catalog-product')
            new_count = 0
            for card in cards:
                name_elem = card.select_one('a.catalog-product__name')
                if not name_elem:
                    continue
                name = name_elem.text.strip()
                rel_url = name_elem.get('href')
                if not rel_url:
                    continue
                product_url = self.base_url + rel_url if rel_url.startswith('/') else rel_url
                if product_url in seen_urls:
                    continue
                seen_urls.add(product_url)

                # Поиск цены
                price_elem = card.select_one('div.product-buy__price')
                if not price_elem:
                    price_elem = card.select_one('div.catalog-product__price span.price')
                price = None
                if price_elem:
                    price_text = re.sub(r'[^0-9]', '', price_elem.text)
                    if price_text:
                        price = float(price_text)
                products.append({
                    'name': name,
                    'url': product_url,
                    'price': price
                })
                new_count += 1
                if max_items and len(products) >= max_items:
                    break
            return new_count

        new_items = parse_current_page()
        self.logger.info(f"Первая загрузка: {new_items} товаров, всего {len(products)}")
        if max_items and len(products) >= max_items:
            return products[:max_items]

        scrolling = True
        while scrolling:
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(random.uniform(5, 10))

            new_height = driver.execute_script("return document.body.scrollHeight")
            if new_height == last_height:
                scroll_attempts += 1
                if scroll_attempts >= 10:
                    self.logger.info("Высота страницы не меняется, завершаем")
                    break
            else:
                scroll_attempts = 0
                last_height = new_height

            new_items = parse_current_page()
            if new_items == 0:
                self.logger.info("Новых товаров не добавлено, завершаем")
                break
            else:
                self.logger.info(f"Подгружено {new_items} новых товаров, всего {len(products)}")

            if max_items and len(products) >= max_items:
                break

        self.logger.info(f"Категория {category_key} обработана, собрано {len(products)} товаров")
        return products[:max_items] if max_items else products

    def parse_product_details(self, product_url: str) -> Dict[str, str]:
        driver = self._get_driver()

        if '/product/' in product_url:
            parts = product_url.split('/product/')
            if len(parts) == 2:
                characteristics_url = f"{parts[0]}/product/characteristics/{parts[1]}"
            else:
                characteristics_url = product_url.rstrip('/') + '/characteristics/'
        else:
            characteristics_url = product_url.rstrip('/') + '/characteristics/'

        for attempt in range(3):
            try:
                driver.get(characteristics_url)
                WebDriverWait(driver, 15).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, 'body'))
                )
                break
            except Exception as e:
                self.logger.warning(f"Ошибка загрузки {characteristics_url}: {e}, попытка {attempt+1}/3")
                time.sleep(random.uniform(5, 10))
                if attempt == 2:
                    return {}

        try:
            expand_btn = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, '.product-characteristics__expand'))
            )
            expand_btn.click()
            time.sleep(random.uniform(5, 10))
        except Exception:
            pass

        try:
            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, '.product-characteristics__spec, .characteristics__item, .product-params__item'))
            )
        except Exception:
            self.logger.warning(f"Блок характеристик не найден для {product_url}")

        soup = BeautifulSoup(driver.page_source, 'lxml')
        specs = {}

        spec_items = soup.select('div.product-characteristics__spec')
        if spec_items:
            for item in spec_items:
                title_elem = item.select_one('.product-characteristics__spec-title-content')
                value_elem = item.select_one('.product-characteristics__spec-value')
                if title_elem and value_elem:
                    key = title_elem.text.strip().rstrip(':')
                    val = value_elem.text.strip()
                    specs[key] = val
        else:
            spec_items = soup.select('div.characteristics__item')
            if not spec_items:
                spec_items = soup.select('div.product-params__item')
            for item in spec_items:
                title_elem = item.select_one('div.characteristics__title')
                value_elem = item.select_one('div.characteristics__value')
                if not title_elem or not value_elem:
                    title_elem = item.select_one('div.product-params__title')
                    value_elem = item.select_one('div.product-params__value')
                if title_elem and value_elem:
                    key = title_elem.text.strip().rstrip(':')
                    val = value_elem.text.strip()
                    specs[key] = val

        if not specs:
            for title_elem in soup.select('[class*="spec-title"]'):
                parent = title_elem.find_parent()
                if parent:
                    value_elem = parent.select_one('[class*="spec-value"]')
                    if value_elem:
                        key = title_elem.text.strip().rstrip(':')
                        val = value_elem.text.strip()
                        specs[key] = val

        self.logger.debug(f"Извлечено {len(specs)} характеристик для {product_url}")
        return specs

    def close(self):
        if self.driver:
            self.driver.quit()
            self.logger.info("Драйвер закрыт")