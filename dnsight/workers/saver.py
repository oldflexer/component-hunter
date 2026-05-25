from sqlalchemy.orm import Session
from typing import Optional, Dict
from ..core.models import Component, Attribute, AttributeValue, ComponentType, PriceHistory
from datetime import datetime

def ensure_component_type(db: Session, type_name: str) -> ComponentType:
    ct = db.query(ComponentType).filter_by(name=type_name).first()
    if not ct:
        ct = ComponentType(name=type_name)
        db.add(ct)
        db.flush()
    return ct

def ensure_attribute(db: Session, attr_name: str, type_id: Optional[int] = None) -> Attribute:
    attr = db.query(Attribute).filter_by(name=attr_name).first()
    if not attr:
        attr = Attribute(name=attr_name, type_id=type_id)
        db.add(attr)
        db.flush()
    return attr

def save_component_and_attributes(
    db: Session,
    type_name: str,
    component_name: str,
    dns_url: str,
    price: Optional[float],
    specs: Dict[str, str]
) -> Component:
    comp_type = ensure_component_type(db, type_name)
    type_id_value = comp_type.id  # type: ignore

    comp = db.query(Component).filter_by(dns_url=dns_url).first()
    if comp:
        comp.name = component_name          # type: ignore
        comp.updated_at = datetime.utcnow() # type: ignore
    else:
        comp = Component(
            type_id=type_id_value,          # type: ignore
            name=component_name,
            dns_url=dns_url
        )
        db.add(comp)
        db.flush()
    
    if price is not None:
        price_history = PriceHistory(
            component_id=comp.id,           # type: ignore
            price=price,
            timestamp=datetime.utcnow()
        )
        db.add(price_history)
    
    for attr_name, value in specs.items():
        attr = ensure_attribute(db, attr_name, type_id_value)  # type: ignore
        existing = db.query(AttributeValue).filter_by(
            component_id=comp.id,
            attribute_id=attr.id
        ).first()
        if existing:
            existing.value_raw = value          # type: ignore
            existing.updated_at = datetime.utcnow()  # type: ignore
        else:
            attr_value = AttributeValue(
                component_id=comp.id,
                attribute_id=attr.id,
                value_raw=value
            )
            db.add(attr_value)
    
    db.commit()
    return comp