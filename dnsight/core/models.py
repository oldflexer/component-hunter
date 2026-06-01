from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey
from sqlalchemy.orm import declarative_base, relationship
from datetime import datetime

Base = declarative_base()

class ProductType(Base):
    __tablename__ = "product_types"
    id = Column(Integer, primary_key=True)
    name = Column(String(50), unique=True, nullable=False)
    description = Column(String(200))

    products = relationship("Product", back_populates="product_type")
    attributes = relationship("Attribute", back_populates="product_type")
    models = relationship("Model", back_populates="product_type")

class Model(Base):
    __tablename__ = "models"
    id = Column(Integer, primary_key=True)
    name = Column(String(200), unique=True, nullable=False)
    type_id = Column(Integer, ForeignKey("product_types.id"), nullable=False)

    product_type = relationship("ProductType", back_populates="models")
    scores = relationship("ModelScore", back_populates="model", cascade="all, delete-orphan")
    products = relationship("Product", back_populates="model")

class ModelScore(Base):
    __tablename__ = "model_scores"
    id = Column(Integer, primary_key=True)
    model_id = Column(Integer, ForeignKey("models.id"), nullable=False)
    score = Column(Float, nullable=False)
    source = Column(String(50), default="passmark")
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, index=True)

    model = relationship("Model", back_populates="scores")

class Product(Base):
    __tablename__ = "products"
    id = Column(Integer, primary_key=True)
    type_id = Column(Integer, ForeignKey("product_types.id"), nullable=False)
    model_id = Column(Integer, ForeignKey("models.id"), nullable=True)
    name = Column(String(200), nullable=False)
    url = Column(String(500), unique=True)   # dns_url
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, onupdate=datetime.utcnow)

    product_type = relationship("ProductType", back_populates="products")
    model = relationship("Model", back_populates="products")
    attribute_values = relationship("AttributeValue", back_populates="product", cascade="all, delete-orphan")
    price_history = relationship("PriceHistory", back_populates="product", cascade="all, delete-orphan")
    benefit_history = relationship("BenefitHistory", back_populates="product", cascade="all, delete-orphan")

class Attribute(Base):
    __tablename__ = "attributes"
    id = Column(Integer, primary_key=True)
    name = Column(String(200), nullable=False)
    type_id = Column(Integer, ForeignKey("product_types.id"), nullable=True)

    product_type = relationship("ProductType", back_populates="attributes")
    attribute_values = relationship("AttributeValue", back_populates="attribute", cascade="all, delete-orphan")

class AttributeValue(Base):
    __tablename__ = "attribute_values"
    id = Column(Integer, primary_key=True)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False)
    attribute_id = Column(Integer, ForeignKey("attributes.id"), nullable=False)
    raw_value = Column(String(500), nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    product = relationship("Product", back_populates="attribute_values")
    attribute = relationship("Attribute", back_populates="attribute_values")

class PriceHistory(Base):
    __tablename__ = "price_history"
    id = Column(Integer, primary_key=True)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False)
    price = Column(Float, nullable=False)
    timestamp = Column(DateTime, default=datetime.utcnow, index=True)

    product = relationship("Product", back_populates="price_history")

class BenefitHistory(Base):
    __tablename__ = "benefit_history"
    id = Column(Integer, primary_key=True)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False)
    benefit = Column(Float, nullable=False)
    timestamp = Column(DateTime, default=datetime.utcnow, index=True)

    product = relationship("Product", back_populates="benefit_history")