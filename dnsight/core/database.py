from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from .config import DATABASE_URL
from .models import Base

engine = create_engine(DATABASE_URL, echo=False)
SessionLocal = sessionmaker(bind=engine)

def get_db() -> Session:
    return SessionLocal()

def init_db():
    Base.metadata.create_all(bind=engine)