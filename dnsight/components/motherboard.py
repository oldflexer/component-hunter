# motherboard.py
import re
from typing import Optional
from sqlalchemy.orm import Session
from .base import BaseComponent
from dnsight.core.models import Product, AttributeValue
from dashboard.utils import get_last_score, get_last_benefit
from dnsight.config.attributes import ATTR_SOCKET, ATTR_MB_PCIE, ATTR_MB_PHASES

class MotherboardComponent(BaseComponent):
    def __init__(self, db: Session, product_id: int, name: str, model_id: Optional[int] = None):
        # Для MB компонент создаётся не по модели, а по продукту (так как модель может отсутствовать)
        super().__init__(db, model_id, name)
        self.product_id = product_id
        self._product = db.query(Product).filter_by(id=product_id).first()
        self._attrs = self._load_attrs()

    def _load_attrs(self) -> dict:
        attrs = self.db.query(AttributeValue).filter_by(product_id=self.product_id).all()
        return {av.attribute.name: av.raw_value for av in attrs}

    def get_score(self) -> Optional[float]:
        if self.model_id:
            return get_last_score(self.db, self.model_id)
        return 0.0

    def get_benefit(self) -> float:
        return get_last_benefit(self.db, self.product_id) or 0.0

    def get_socket(self) -> str:
        return self._attrs.get(ATTR_SOCKET, "").strip()

    def get_pcie_version(self) -> float:
        raw = self._attrs.get(ATTR_MB_PCIE, "")
        if not raw:
            return 0.0
        match = re.search(r'(\d+\.?\d*)', raw)
        return float(match.group(1)) if match else 0.0

    def get_phase(self) -> int:
        raw = self._attrs.get(ATTR_MB_PHASES, "")
        if not raw:
            return 0
        numbers = re.findall(r'\d+', raw)
        return sum(int(n) for n in numbers) if numbers else 0