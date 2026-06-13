# base.py
from abc import ABC, abstractmethod
from sqlalchemy.orm import Session
from typing import Optional

class BaseComponent(ABC):
    def __init__(self, db: Session, model_id: int, name: str):
        self.db = db
        self.model_id = model_id
        self.name = name

    @abstractmethod
    def get_score(self) -> Optional[float]:
        """Возвращает последний скор производительности."""
        pass

    @abstractmethod
    def get_benefit(self) -> float:
        """Возвращает последний Benefit (score/price)."""
        pass

    @abstractmethod
    def get_socket(self) -> str:
        """Возвращает сокет (процессора или материнской платы)."""
        pass

    @abstractmethod
    def get_pcie_version(self) -> float:
        """Возвращает версию PCIe (число)."""
        pass