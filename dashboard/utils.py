from datetime import datetime, timedelta
import pandas as pd
from sqlalchemy.orm import Session

from dnsight.core.models import PriceHistory, ModelScore, BenefitHistory


def get_last_price(db: Session, product_id: int):
    """Возвращает последнюю цену продукта."""
    ph = db.query(PriceHistory).filter_by(product_id=product_id).order_by(PriceHistory.timestamp.desc()).first()
    return ph.price if ph else None


def get_last_score(db: Session, model_id: int):
    """Возвращает последний скор модели."""
    ms = db.query(ModelScore).filter_by(model_id=model_id).order_by(ModelScore.updated_at.desc()).first()
    return ms.score if ms else None


def get_last_benefit(db: Session, product_id: int):
    """Возвращает последний Benefit продукта."""
    bh = db.query(BenefitHistory).filter_by(product_id=product_id).order_by(BenefitHistory.timestamp.desc()).first()
    return bh.benefit if bh else None


def get_delta_ratio(db: Session, product_id: int, days: int = 7) -> float:
    """
    Возвращает отношение текущего Benefit к Benefit `days` дней назад.
    Если данных недостаточно, возвращает 1.0.
    """
    now = datetime.now()
    cutoff = now - timedelta(days=days)
    last = db.query(BenefitHistory).filter_by(product_id=product_id).order_by(BenefitHistory.timestamp.desc()).first()
    if not last or last.benefit == 0:
        return 1.0
    prev = db.query(BenefitHistory).filter(
        BenefitHistory.product_id == product_id,
        BenefitHistory.timestamp <= cutoff
    ).order_by(BenefitHistory.timestamp.desc()).first()
    if not prev or prev.benefit == 0:
        return 1.0
    return last.benefit / prev.benefit


def normalize_matrix(matrix):
    # Собираем все числовые значения (игнорируем None, inf, NaN)
    flat = []
    for row in matrix:
        for val in row:
            if val is not None and val != float('inf') and not pd.isna(val):
                flat.append(val)
    if not flat:
        # Нет данных – все ячейки серые (0.5)
        return [[0.5] * len(matrix[0]) for _ in range(len(matrix))]
    min_val = min(flat)
    max_val = max(flat)
    if max_val == min_val:
        return [[0.5] * len(row) for row in matrix]
    norm = []
    for row in matrix:
        norm_row = []
        for val in row:
            if val is None or val == float('inf') or pd.isna(val):
                norm_row.append(None)   # → белая ячейка (plotly не рисует)
            else:
                norm_row.append((val - min_val) / (max_val - min_val))
        norm.append(norm_row)
    return norm