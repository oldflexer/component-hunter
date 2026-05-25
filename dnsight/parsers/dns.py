import time
import re
from typing import List, Dict, Optional
from bs4 import BeautifulSoup
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from ..core.config import DNS_CATEGORIES, REQUEST_TIMEOUT

class DNSParser:
    def __init__(self, chromedriver_path: Optional[str] = None):
        """
        :param chromedriver_path: путь к chromedriver.exe (например, "chromedriver/chromedriver.exe")
        """
        self.base_url = "https://www.dns-shop.ru"
        self.driver = None
        self.chromedriver_path = chromedriver_path

    def _get_driver(self):
        """Ленивая инициализация драйвера с указанием пути к chromedriver"""
        if self.driver is None:
            options = uc.ChromeOptions()
            # options.add_argument('--headless')
            options.add_argument('--no-sandbox')
            options.add_argument('--disable-dev-shm-usage')
            # Если передан путь к chromedriver, используем его
            if self.chromedriver_path:
                # Для undetected-chromedriver путь указывается через `executable_path`
                self.driver = uc.Chrome(
                    options=options,
                    executable_path=self.chromedriver_path
                )
            else:
                self.driver = uc.Chrome(options=options)
        return self.driver

    def _wait_for_element(self, driver, selector: str, timeout: int = REQUEST_TIMEOUT):
        return WebDriverWait(driver, timeout).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, selector))
        )

    def parse_category(self, category_key: str, max_pages: Optional[int] = 1, max_items: Optional[int] = 3) -> List[Dict]:
        if category_key not in DNS_CATEGORIES:
            raise ValueError(f"Unknown category: {category_key}")
        url = DNS_CATEGORIES[category_key]
        driver = self._get_driver()
        products = []
        page_num = 1

        while True:
            print(f"Страница {page_num} для {category_key}")
            driver.get(url)
            try:
                self._wait_for_element(driver, 'div.catalog-product', timeout=REQUEST_TIMEOUT)
            except Exception:
                print("Не удалось загрузить товары на странице, возможно, конец списка")
                break

            time.sleep(2)

            soup = BeautifulSoup(driver.page_source, 'lxml')
            cards = soup.select('div.catalog-product')
            if not cards:
                break

            for card in cards:
                name_elem = card.select_one('a.catalog-product__name')
                if not name_elem:
                    continue
                name = name_elem.text.strip()
                rel_url = name_elem.get('href')
                if not rel_url:
                    continue
                product_url = self.base_url + rel_url if rel_url.startswith('/') else rel_url

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

                if max_items and len(products) >= max_items:
                    break

            if max_items and len(products) >= max_items:
                break

            # Пагинация
            try:
                next_link = driver.find_element(By.CSS_SELECTOR, f'a.pagination-widget__page[data-page-number="{page_num + 1}"]')
                url = next_link.get_attribute('href')
                page_num += 1
                if max_pages and page_num > max_pages:
                    break
                time.sleep(1)
                continue
            except:
                break

        return products[:max_items] if max_items else products

    def parse_product_details(self, product_url: str) -> Dict[str, str]:
        driver = self._get_driver()
        # Формируем URL страницы характеристик
        if '/product/' in product_url:
            parts = product_url.split('/product/')
            if len(parts) == 2:
                characteristics_url = f"{parts[0]}/product/characteristics/{parts[1]}"
            else:
                characteristics_url = product_url.rstrip('/') + '/characteristics/'
        else:
            characteristics_url = product_url.rstrip('/') + '/characteristics/'

        driver.get(characteristics_url)

        try:
            expand_button = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, '.product-characteristics__expand'))
            )
            expand_button.click()
            time.sleep(2)
        except Exception:
            pass

        soup = BeautifulSoup(driver.page_source, 'lxml')
        specs = {}

        spec_items = soup.select('div.characteristics__item')
        if not spec_items:
            spec_items = soup.select('div.product-params__item')
        if not spec_items:
            spec_items = soup.select('div.product-characteristics__spec')

        for item in spec_items:
            title_elem = item.select_one('div.characteristics__title')
            value_elem = item.select_one('div.characteristics__value')
            if not title_elem or not value_elem:
                title_elem = item.select_one('div.product-params__title')
                value_elem = item.select_one('div.product-params__value')
            if not title_elem or not value_elem:
                title_elem = item.select_one('.product-characteristics__spec-title-content')
                value_elem = item.select_one('.product-characteristics__spec-value')
            if title_elem and value_elem:
                key = title_elem.text.strip().rstrip(':')
                val = value_elem.text.strip()
                specs[key] = val

        return specs

    def close(self):
        if self.driver:
            self.driver.quit()