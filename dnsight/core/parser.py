from abc import ABC
import nodriver as uc


class AsyncBaseParser(ABC):
    def __init__(self):
        self.browser = None

    async def start_browser(self, headless: bool = False):
        self.browser = await uc.start(headless=headless)

    async def close_browser(self):
        if self.browser is not None:
            await self.browser.stop()
            self.browser = None

    async def parse(self, *args, **kwargs):
        pass