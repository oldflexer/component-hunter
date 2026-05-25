# parsers/base.py
import requests
import time
import logging
from abc import ABC
from bs4 import BeautifulSoup
from ..core.config import REQUEST_TIMEOUT, MAX_RETRIES, RETRY_DELAY, USER_AGENTS

logger = logging.getLogger(__name__)

def random_ua() -> str:
    import random
    return random.choice(USER_AGENTS) if USER_AGENTS else "Mozilla/5.0"

class BaseParser(ABC):
    def __init__(self, use_proxy: bool = False):
        self.session = requests.Session()
        self.session.headers.update({'User-Agent': random_ua()})
        if use_proxy:
            pass
        self.timeout = REQUEST_TIMEOUT

    def _get_soup(self, url: str, retries: int = MAX_RETRIES) -> BeautifulSoup:
        for attempt in range(retries):
            try:
                self.session.headers.update({'User-Agent': random_ua()})
                resp = self.session.get(url, timeout=self.timeout)
                resp.raise_for_status()
                if "captcha" in resp.text.lower():
                    raise Exception("Captcha detected")
                return BeautifulSoup(resp.text, 'lxml')
            except Exception as e:
                logger.warning(f"Attempt {attempt+1} failed for {url}: {e}")
                if attempt == retries - 1:
                    raise
                time.sleep(RETRY_DELAY * (attempt + 1))
        raise RuntimeError("Unreachable")  # для статического анализатора