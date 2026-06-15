# gpu.py
from typing import Optional
from sqlalchemy.orm import Session
from .base import BaseComponent
from dashboard.utils import get_last_score, get_last_benefit
from dnsight.core.models import Product


class GPUComponent(BaseComponent):
    def __init__(self, db: Session, model_id: int, name: str):
        super().__init__(db, model_id, name)
        self._product = db.query(Product).filter_by(model_id=model_id).first()

    def get_score(self) -> Optional[float]:
        return get_last_score(self.db, self.model_id)

    def get_benefit(self) -> float:
        benefit = get_last_benefit(self.db, self._product.id) if self._product else None
        return benefit if benefit is not None else 0.0

    def get_socket(self) -> str:
        return ""

    def get_pcie_version(self) -> float:
        return 0.0