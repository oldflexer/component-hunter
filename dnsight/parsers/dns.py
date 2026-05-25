import re
import random
import time
from typing import List, Dict, Optional
from bs4 import BeautifulSoup
from ..core.config import DNS_CATEGORIES, REQUEST_TIMEOUT, MAX_RETRIES, USER_AGENTS
from ..core.utils import random_sleep
from .base import BaseParser

class DNSParser(BaseParser):
    def __init__(self, use_proxy: bool = False):
        super().__init__(use_proxy)
        self.base_url = "https://www.dns-shop.ru"

    def parse_category(self, category_key: str) -> List[Dict]:
        """Парсинг списка товаров в категории (например, 'cpu')"""
        if category_key not in DNS_CATEGORIES:
            raise ValueError(f"Unknown category: {category_key}")
        url = DNS_CATEGORIES[category_key]
        soup = self._get_soup(url)
        products = []
        
        # Селекторы (можно вынести в config)
        card_selector = 'div.catalog-product'
        name_selector = 'a.catalog-product__name'
        price_selector = 'div.product-buy__price'
        # Альтернативные селекторы на случай изменений
        alt_price_selector = 'div.catalog-product__price span.price'
        
        for card in soup.select(card_selector):
            name_elem = card.select_one(name_selector)
            if not name_elem:
                continue
            name = name_elem.text.strip()
            rel_url = name_elem.get('href')
            product_url = self.base_url + rel_url if rel_url.startswith('/') else rel_url
            
            price_elem = card.select_one(price_selector) or card.select_one(alt_price_selector)
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
            random_sleep(0.2, 0.8)
        
        return products

    def parse_product_details(self, product_url: str) -> Dict[str, str]:
        """Извлечение технических характеристик со страницы товара"""
        soup = self._get_soup(product_url)
        specs = {}
        
        # Блок характеристик (адаптируйте под реальную верстку)
        spec_blocks = soup.select('div.product-characteristics dl')  # или ul
        for block in spec_blocks:
            # Вариант: dt -> dd
            for dt, dd in zip(block.select('dt'), block.select('dd')):
                key = dt.text.strip().rstrip(':')
                val = dd.text.strip()
                specs[key] = val
        
        # Если не нашли, пробуем альтернативный селектор
        if not specs:
            rows = soup.select('div.characteristics__item')
            for row in rows:
                key_elem = row.select_one('div.characteristics__title')
                val_elem = row.select_one('div.characteristics__value')
                if key_elem and val_elem:
                    specs[key_elem.text.strip()] = val_elem.text.strip()
        
        return specs