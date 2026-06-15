# cpu.py
import re
from typing import Optional
from sqlalchemy.orm import Session
from .base import BaseComponent
from dnsight.core.models import Product, AttributeValue
from dashboard.utils import get_last_score, get_last_benefit
from dnsight.config.attributes import ATTR_SOCKET, ATTR_CPU_PCIE, ATTR_CPU_TDP


class CPUComponent(BaseComponent):
    def __init__(self, db: Session, model_id: int, name: str):
        super().__init__(db, model_id, name)
        self._product = db.query(Product).filter_by(model_id=model_id).first()
        self._attrs = self._load_attrs() if self._product else {}

    def _load_attrs(self) -> dict:
        attrs = self.db.query(AttributeValue).filter_by(product_id=self._product.id).all()
        return {av.attribute.name: av.raw_value for av in attrs}

    def get_score(self) -> Optional[float]:
        return get_last_score(self.db, self.model_id)

    def get_benefit(self) -> float:
        benefit = get_last_benefit(self.db, self._product.id) if self._product else None
        return benefit if benefit is not None else 0.0

    def get_socket(self) -> str:
        return self._attrs.get(ATTR_SOCKET, "").strip()

    def get_pcie_version(self) -> float:
        raw = self._attrs.get(ATTR_CPU_PCIE, "")
        if not raw:
            return 0.0
        match = re.search(r'(\d+\.?\d*)', raw)
        return float(match.group(1)) if match else 0.0

    def get_tdp(self) -> int:
        raw = self._attrs.get(ATTR_CPU_TDP, "")
        if not raw:
            return 0
        match = re.search(r'\d+', raw)
        return int(match.group()) if match else 0