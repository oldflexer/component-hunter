import logging
import random
import time
import re
import os
import urllib.request
from io import BytesIO
from typing import List, Dict, Optional

import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from bs4 import BeautifulSoup

from ..core.config import DNS_CATEGORIES, REQUEST_TIMEOUT
from ..core.logging import get_logger


class DNSParser:
    def __init__(self, log_file="logs/parser.log", log_level=logging.DEBUG):
        self.logger = get_logger("parser", log_file, level=log_level, mode='w')
        self.base_url = "https://www.dns-shop.ru"
        self.driver = None

    def _get_driver(self):
        if self.driver is not None:
            return self.driver

        options = uc.ChromeOptions()
        self.driver = uc.Chrome(version_main=148, options=options)
        self.driver.set_page_load_timeout(REQUEST_TIMEOUT)
        self.logger.info("undetected ChromeDriver инициализирован (версия 148, без локального драйвера)")

        return self.driver

    def _safe_get(self, url: str, retries: int = 3) -> bool:
        driver = self._get_driver()
        for attempt in range(retries):
            try:
                driver.get(url)
                WebDriverWait(driver, 15).until(
                    EC.presence_of_element_located((By.TAG_NAME, "body"))
                )
                return True
            except Exception as e:
                self.logger.warning(f"Ошибка загрузки {url}, попытка {attempt+1}/{retries}: {e}")
                try:
                    driver.execute_script("window.stop();")
                except:
                    pass
                time.sleep(5 * (attempt + 1))
        self.logger.error(f"Не удалось загрузить {url} после {retries} попыток")
        return False

    def parse_category(self, category_key: str, max_pages: Optional[int] = None, max_items: Optional[int] = None) -> List[Dict]:
        if category_key not in DNS_CATEGORIES:
            raise ValueError(f"Unknown category: {category_key}")

        url = DNS_CATEGORIES[category_key]
        if not self._safe_get(url):
            return []

        driver = self._get_driver()
        self.logger.info(f"Начинаем парсинг категории {category_key} (пагинация)")

        products = []
        seen_urls = set()
        page_num = 1

        while True:
            if max_pages and page_num > max_pages:
                self.logger.info(f"Достигнуто максимальное количество страниц ({max_pages})")
                break

            try:
                WebDriverWait(driver, 20).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, 'div.catalog-product'))
                )
            except TimeoutException:
                self.logger.warning(f"Не удалось загрузить товары на странице {page_num}")
                break

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

                price_elem = card.select_one('div.product-buy__price')
                if not price_elem:
                    price_elem = card.select_one('div.catalog-product__price span.price')
                price = None
                if price_elem:
                    price_text = re.sub(r'[^\d]', '', price_elem.text)
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

            self.logger.info(f"Страница {page_num}: собрано {new_count} товаров, всего {len(products)}")

            if max_items and len(products) >= max_items:
                break

            # Пагинация через кнопку "Показать ещё"
            try:
                show_more_btn = driver.find_element(By.CSS_SELECTOR, 'button.pagination-widget__show-more-btn')
                if show_more_btn.is_enabled():
                    driver.execute_script("arguments[0].scrollIntoView(true);", show_more_btn)
                    time.sleep(0.5)
                    show_more_btn.click()
                    page_num += 1
                    time.sleep(random.uniform(2, 4))
                    continue
                else:
                    self.logger.info("Кнопка 'Показать ещё' неактивна, завершаем")
                    break
            except NoSuchElementException:
                self.logger.info("Кнопка пагинации не найдена, завершаем")
                break
            except Exception as e:
                self.logger.warning(f"Ошибка пагинации: {e}")
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
                time.sleep(5)
                if attempt == 2:
                    return {}

        try:
            expand_btn = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, '.product-characteristics__expand'))
            )
            expand_btn.click()
            time.sleep(random.uniform(1, 2))
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