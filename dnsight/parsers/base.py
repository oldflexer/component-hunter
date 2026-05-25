# parsers/base.py
import requests
import time
import logging
from abc import ABC, abstractmethod
from bs4 import BeautifulSoup
from ..core.config import REQUEST_TIMEOUT, MAX_RETRIES, RETRY_DELAY, USER_AGENTS
from ..core.utils import random_ua

logger = logging.getLogger(__name__)

class BaseParser(ABC):
    def __init__(self, use_proxy=False):
        self.session = requests.Session()
        self.session.headers.update({'User-Agent': random_ua()})
        if use_proxy:
            # настройка прокси из переменных окружения
            pass
        self.timeout = REQUEST_TIMEOUT

    def _get_soup(self, url: str, retries=MAX_RETRIES) -> BeautifulSoup:
        for attempt in range(retries):
            try:
                # обновляем User-Agent при каждой попытке
                self.session.headers.update({'User-Agent': random_ua()})
                resp = self.session.get(url, timeout=self.timeout)
                resp.raise_for_status()
                # Проверяем, не капча ли (можно по keywords в тексте)
                if "captcha" in resp.text.lower():
                    raise Exception("Captcha detected")
                return BeautifulSoup(resp.text, 'lxml')
            except Exception as e:
                logger.warning(f"Attempt {attempt+1} failed for {url}: {e}")
                if attempt == retries - 1:
                    raise
                time.sleep(RETRY_DELAY * (attempt + 1))