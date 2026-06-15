from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, Session
from ..config.settings import DATABASE_URL
from .models import Base

engine = create_engine(DATABASE_URL, echo=False)
SessionLocal = sessionmaker(bind=engine)

def get_db() -> Session:
    return SessionLocal()

def init_db():
    Base.metadata.create_all(bind=engine)

@event.listens_for(engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON;")
    cursor.close()