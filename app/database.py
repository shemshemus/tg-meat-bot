from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

from app.config import settings

# Engine = the connection to your database
# It manages a pool of connections under the hood
engine = create_engine(settings.database_url)

# SessionLocal = a factory that creates new database sessions
# autocommit=False: we control when to save (explicit > implicit)
# autoflush=False: don't auto-sync Python objects to DB (we do it manually)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Base = parent class for all our models
# Every model that inherits from Base becomes a database table
Base = declarative_base()


def get_db():
    """Yield a database session, then close it when done.

    Used as a FastAPI dependency — FastAPI calls this automatically
    for every request that needs a DB connection.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
