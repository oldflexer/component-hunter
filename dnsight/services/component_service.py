# component_service.py
from typing import List, Union
from sqlalchemy.orm import Session
from dnsight.core.models import ProductType, Model, Product, Attribute, AttributeValue
from dnsight.components.cpu import CPUComponent
from dnsight.components.gpu import GPUComponent
from dnsight.components.motherboard import MotherboardComponent
from dnsight.config.settings import ComponentType
from dnsight.config.attributes import ATTR_GPU_CHIP

class ComponentService:
    def __init__(self, db: Session):
        self.db = db

    def get_type_id(self, type_name: ComponentType) -> int:
        pt = self.db.query(ProductType).filter_by(name=type_name).first()
        return pt.id if pt else None

    def get_models_by_type(self, type_name: ComponentType) -> List[Model]:
        type_id = self.get_type_id(type_name)
        if not type_id:
            return []
        return self.db.query(Model).filter_by(type_id=type_id).all()

    def get_products_by_type(self, type_name: ComponentType) -> List[Product]:
        type_id = self.get_type_id(type_name)
        if not type_id:
            return []
        return self.db.query(Product).filter_by(type_id=type_id).all()

    def get_cpu_components(self) -> List[CPUComponent]:
        models = self.get_models_by_type(ComponentType.CPU)
        components = []
        for model in models:
            score = get_last_score(self.db, model.id)
            if score is not None:
                components.append(CPUComponent(self.db, model.id, model.name))
        return components

    def get_gpu_components(self) -> List[GPUComponent]:
        models = self.get_models_by_type(ComponentType.GPU)
        components = []
        for model in models:
            score = get_last_score(self.db, model.id)
            if score is not None:
                components.append(GPUComponent(self.db, model.id, model.name))
        return components

    def get_mb_components(self) -> List[MotherboardComponent]:
        products = self.get_products_by_type(ComponentType.MOTHERBOARD)
        components = []
        for prod in products:
            # Определяем отображаемое имя
            attrs = {av.attribute.name: av.raw_value for av in self.db.query(AttributeValue).filter_by(product_id=prod.id).all()}
            name = None
            if prod.model_id:
                model = self.db.query(Model).filter_by(id=prod.model_id).first()
                if model:
                    name = model.name
            if not name:
                name = attrs.get(ATTR_MODEL, prod.name)
            components.append(MotherboardComponent(self.db, prod.id, name, prod.model_id))
        return components

# Вспомогательная функция (нужна для импорта)
from dashboard.utils import get_last_score, get_last_benefit, get_delta_ratio