# gpu.py
from typing import Optional
from sqlalchemy.orm import Session
from .base import BaseComponent
from dashboard.utils import get_last_score, get_last_benefit
from dnsight.config.attributes import ATTR_GPU_CHIP

class GPUComponent(BaseComponent):
    def __init__(self, db: Session, model_id: int, name: str):
        super().__init__(db, model_id, name)
        # Для GPU модель идентифицируется по атрибуту "Графический процессор"
        # Но в БД модель уже должна быть создана при парсинге
        self._raw_chip = name  # имя модели и есть чип

    def get_score(self) -> Optional[float]:
        return get_last_score(self.db, self.model_id)

    def get_benefit(self) -> float:
        # Найдём продукт, связанный с этой моделью (первый попавшийся)
        from dnsight.core.models import Product
        product = self.db.query(Product).filter_by(model_id=self.model_id).first()
        return get_last_benefit(self.db, product.id) if product else 0.0

    def get_socket(self) -> str:
        # Для GPU сокет не определён, возвращаем пустую строку
        return ""

    def get_pcie_version(self) -> float:
        # Для GPU версия PCIe не используется в тепловых картах (можно оставить 0)
        return 0.0