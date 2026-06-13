# heatmap_service.py
from typing import List, Callable, Tuple, Optional
from dnsight.components.base import BaseComponent

class HeatmapService:
    @staticmethod
    def build_matrix(
        rows: List[BaseComponent],
        cols: List[BaseComponent],
        value_func: Callable[[BaseComponent, BaseComponent], Optional[float]]
    ) -> Tuple[List[str], List[str], List[List[Optional[float]]]]:
        row_names = [c.name for c in rows]
        col_names = [c.name for c in cols]
        matrix = []
        for row in rows:
            row_vals = []
            for col in cols:
                val = value_func(row, col)
                row_vals.append(val)
            matrix.append(row_vals)
        return row_names, col_names, matrix