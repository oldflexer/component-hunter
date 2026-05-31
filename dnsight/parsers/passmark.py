import re
import asyncio
from typing import Optional

from ..core.parser import AsyncBaseParser
from ..core.logging import get_logger


class AsyncPassMarkParser(AsyncBaseParser):
    """Асинхронный парсер PassMark для CPU и GPU."""

    def __init__(self, log_file="logs/passmark.log"):
        super().__init__()
        self.logger = get_logger("async_passmark", log_file, mode='a')
        self.cpu_base_url = "https://www.cpubenchmark.net"
        self.gpu_base_url = "https://www.videocardbenchmark.net"

    async def _search_cpu(self, model_name: str) -> Optional[float]:
        page = await self.browser.get(f"{self.cpu_base_url}/CPU_mega_page.html")
        search_input = await page.select('input#search_name', timeout=10)
        if search_input is None:
            self.logger.warning(f"Поле поиска не найдено для CPU {model_name}")
            return None
        await search_input.send_keys(model_name)
        await asyncio.sleep(2)

        try:
            first_row = await page.select('#cputable tbody tr', timeout=10)
            if first_row is None:
                raise Exception("Строка не найдена")
        except Exception:
            self.logger.warning(f"Не найдена таблица для CPU {model_name}")
            return None

        cells = await first_row.select_all('td') # pyright: ignore[reportOptionalCall]
        if len(cells) < 4:
            self.logger.debug(f"Недостаточно столбцов для CPU {model_name}")
            return None

        score_td = cells[3]
        if score_td is None:
            self.logger.debug(f"Ячейка с баллом не найдена для CPU {model_name}")
            return None

        assert score_td is not None
        score_cell = await score_td.text  # type: ignore[union-attr]
        score_text = re.sub(r'[^\d.]', '', score_cell)
        try:
            return float(score_text)
        except ValueError:
            self.logger.debug(f"Не удалось преобразовать '{score_cell}' в число")
            return None

    async def _search_gpu(self, model_name: str) -> Optional[float]:
        page = await self.browser.get(f"{self.gpu_base_url}/GPU_mega_page.html")
        search_input = await page.select('input#search_name', timeout=10)
        if search_input is None:
            self.logger.warning(f"Поле поиска не найдено для GPU {model_name}")
            return None
        await search_input.send_keys(model_name)
        await asyncio.sleep(2)

        try:
            first_row = await page.select('#gputable tbody tr', timeout=10)
            if first_row is None:
                raise Exception("Строка не найдена")
        except Exception:
            self.logger.warning(f"Не найдена таблица для GPU {model_name}")
            return None

        cells = await first_row.select_all('td') # pyright: ignore[reportOptionalCall]
        if len(cells) < 3:
            self.logger.debug(f"Недостаточно столбцов для GPU {model_name}")
            return None

        score_td = cells[2]
        if score_td is None:
            self.logger.debug(f"Ячейка с баллом не найдена для GPU {model_name}")
            return None

        assert score_td is not None
        score_cell = await score_td.text  # type: ignore[union-attr]
        score_text = re.sub(r'[^\d.]', '', score_cell)
        try:
            return float(score_text)
        except ValueError:
            self.logger.debug(f"Не удалось преобразовать '{score_cell}' в число для GPU")
            return None

    async def get_score(self, model_name: str, component_type: str) -> Optional[float]:
        if component_type.upper() == "CPU":
            return await self._search_cpu(model_name)
        elif component_type.upper() == "GPU":
            return await self._search_gpu(model_name)
        else:
            self.logger.error(f"Неподдерживаемый тип: {component_type}")
            return None