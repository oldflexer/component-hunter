import re
import asyncio
from typing import List, Dict, Optional

import nodriver as uc
from bs4 import BeautifulSoup

from ..core.parser import AsyncBaseParser
from ..core.config import DNS_CATEGORIES
from ..core.logging import get_logger


class AsyncDNSParser(AsyncBaseParser):
    """Асинхронный парсер DNS‑Shop с использованием nodriver."""

    def __init__(self, log_file="logs/parser.log", log_level="DEBUG"):
        super().__init__()
        self.logger = get_logger("async_dns", log_file, mode='w')
        self.base_url = "https://www.dns-shop.ru"

    async def _wait_for_products(self, page, timeout: int = 20):
        """Ожидание появления хотя бы одного товара на странице."""
        # Сначала ждём загрузки body
        await page.wait_for('body', timeout=10)
        # Затем ждём карточки
        await page.select('div.catalog-product', timeout=timeout)

    async def parse_category(
        self,
        category_key: str,
        max_pages: Optional[int] = None,  # интерпретируется как макс. количество прокруток
        max_items: Optional[int] = None
    ) -> List[Dict]:
        if category_key not in DNS_CATEGORIES:
            raise ValueError(f"Unknown category: {category_key}")

        url = DNS_CATEGORIES[category_key]
        page = await self.browser.get(url)
        await page.wait_for('body', timeout=30)
        self.logger.info(f"Начинаем парсинг категории {category_key} (бесконечная прокрутка)")

        # Ждём появления первой карточки с увеличенным таймаутом
        try:
            await page.select('div.catalog-product', timeout=30)
        except Exception as e:
            self.logger.warning(f"Не удалось загрузить товары: {e}")
            return []

        products = []
        seen_urls = set()
        scroll_attempts = 0
        max_scrolls = max_pages if max_pages else 30
        no_new_items_count = 0

        # Первичный парсинг
        html = await page.get_content()
        soup = BeautifulSoup(html, 'lxml')
        cards = soup.select('div.catalog-product')
        for card in cards:
            name_elem = card.select_one('a.catalog-product__name')
            if not name_elem:
                continue
            name = name_elem.text.strip()
            href = name_elem.get('href')
            if not href:
                continue
            product_url = self.base_url + href if href.startswith('/') else href
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
            if max_items and len(products) >= max_items:
                return products[:max_items]

        self.logger.info(f"Первая загрузка: {len(products)} товаров")

        # Цикл прокрутки
        while scroll_attempts < max_scrolls:
            if max_items and len(products) >= max_items:
                break

            # Прокручиваем вниз
            await page.scroll_down(800)
            await asyncio.sleep(3)  # Увеличил задержку

            # Парсим все карточки заново
            html = await page.get_content()
            soup = BeautifulSoup(html, 'lxml')
            cards = soup.select('div.catalog-product')
            new_count = 0
            for card in cards:
                name_elem = card.select_one('a.catalog-product__name')
                if not name_elem:
                    continue
                name = name_elem.text.strip()
                href = name_elem.get('href')
                if not href:
                    continue
                product_url = self.base_url + href if href.startswith('/') else href
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

            if new_count == 0:
                no_new_items_count += 1
                if no_new_items_count >= 2:
                    self.logger.info("Новых товаров не добавлено, завершаем")
                    break
            else:
                no_new_items_count = 0
                self.logger.info(f"Подгружено {new_count} новых товаров, всего {len(products)}")
                scroll_attempts = 0  # сбрасываем счётчик, если есть новые товары
            scroll_attempts += 1

        self.logger.info(f"Категория {category_key} обработана, собрано {len(products)} товаров")
        return products[:max_items] if max_items else products

    async def parse_product_details(self, product_url: str) -> Dict[str, str]:
        if '/product/' in product_url:
            parts = product_url.split('/product/')
            if len(parts) == 2:
                characteristics_url = f"{parts[0]}/product/characteristics/{parts[1]}"
            else:
                characteristics_url = product_url.rstrip('/') + '/characteristics/'
        else:
            characteristics_url = product_url.rstrip('/') + '/characteristics/'

        page = await self.browser.get(characteristics_url)
        try:
            await page.select('.product-characteristics__spec, .characteristics__item, .product-params__item', timeout=15)
        except Exception:
            self.logger.warning(f"Блок характеристик не найден для {product_url}")
            return {}

        try:
            expand_btn = await page.select('.product-characteristics__expand', timeout=5)
            if expand_btn:
                await expand_btn.click()
                await asyncio.sleep(1)
        except Exception:
            pass

        html = await page.get_content()
        soup = BeautifulSoup(html, 'lxml')
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