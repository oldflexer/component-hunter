from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, JSON
from sqlalchemy.orm import declarative_base, relationship
from datetime import datetime

Base = declarative_base()

class ComponentType(Base):
    __tablename__ = "component_types"
    id = Column(Integer, primary_key=True)
    name = Column(String(50), unique=True, nullable=False)
    description = Column(String(200))
    
    components = relationship("Component", back_populates="component_type")
    attributes = relationship("Attribute", back_populates="component_type")

class Component(Base):
    __tablename__ = "components"
    id = Column(Integer, primary_key=True)
    type_id = Column(Integer, ForeignKey("component_types.id"), nullable=False)
    name = Column(String(200), nullable=False)
    dns_url = Column(String(500), unique=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, onupdate=datetime.utcnow)
    
    component_type = relationship("ComponentType", back_populates="components")
    attribute_values = relationship("AttributeValue", back_populates="component", cascade="all, delete-orphan")
    price_history = relationship("PriceHistory", back_populates="component", cascade="all, delete-orphan")
    score_history = relationship("ScoreHistory", back_populates="component", cascade="all, delete-orphan")
    benefit_history = relationship("BenefitHistory", back_populates="component", cascade="all, delete-orphan")

class Attribute(Base):
    __tablename__ = "attributes"
    id = Column(Integer, primary_key=True)
    name = Column(String(200), nullable=False)
    type_id = Column(Integer, ForeignKey("component_types.id"), nullable=True)
    aliases = Column(JSON, default=list)
    
    component_type = relationship("ComponentType", back_populates="attributes")
    attribute_values = relationship("AttributeValue", back_populates="attribute", cascade="all, delete-orphan")
    value_aliases = relationship("ValueAlias", back_populates="attribute", cascade="all, delete-orphan")

class AttributeValue(Base):
    __tablename__ = "attribute_values"
    id = Column(Integer, primary_key=True)
    component_id = Column(Integer, ForeignKey("components.id"), nullable=False)
    attribute_id = Column(Integer, ForeignKey("attributes.id"), nullable=False)
    value_raw = Column(String(500), nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    component = relationship("Component", back_populates="attribute_values")
    attribute = relationship("Attribute", back_populates="attribute_values")

class ValueAlias(Base):
    __tablename__ = "value_aliases"
    id = Column(Integer, primary_key=True)
    attribute_id = Column(Integer, ForeignKey("attributes.id"), nullable=False)
    raw_value = Column(String(200), nullable=False)
    canonical_value = Column(String(200), nullable=False)
    
    attribute = relationship("Attribute", back_populates="value_aliases")

class PriceHistory(Base):
    __tablename__ = "price_history"
    id = Column(Integer, primary_key=True)
    component_id = Column(Integer, ForeignKey("components.id"), nullable=False)
    price = Column(Float, nullable=False)
    timestamp = Column(DateTime, default=datetime.utcnow, index=True)
    
    component = relationship("Component", back_populates="price_history")

class ScoreHistory(Base):
    __tablename__ = "score_history"
    id = Column(Integer, primary_key=True)
    component_id = Column(Integer, ForeignKey("components.id"), nullable=False)
    score = Column(Float, nullable=False)
    source = Column(String(50), default="passmark")
    timestamp = Column(DateTime, default=datetime.utcnow, index=True)
    
    component = relationship("Component", back_populates="score_history")

class BenefitHistory(Base):
    __tablename__ = "benefit_history"
    id = Column(Integer, primary_key=True)
    component_id = Column(Integer, ForeignKey("components.id"), nullable=False)
    benefit = Column(Float, nullable=False)
    timestamp = Column(DateTime, default=datetime.utcnow, index=True)
    
    component = relationship("Component", back_populates="benefit_history")