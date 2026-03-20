import logging
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase
from app.core.config import settings 

logger = logging.getLogger(__name__)

# SQLAlchemy 2.0 스타일 선언적 베이스
class Base(DeclarativeBase):
    pass

connect_args = {}
if settings.DATABASE_URL.startswith("sqlite"):
    connect_args["check_same_thread"] = False

# 엔진 생성 (보안을 위해 URL 출력 제거)
engine = create_engine(
    settings.DATABASE_URL,
    connect_args=connect_args,
    pool_size=settings.DB_POOL_SIZE,
    max_overflow=settings.DB_MAX_OVERFLOW,
    pool_pre_ping=True
)

SessionLocal = sessionmaker(
    autocommit=False, 
    autoflush=True, 
    bind=engine
)

def get_db():
    """FastAPI Dependency: 세션 생명주기 및 예외 롤백 관리"""
    db = SessionLocal()
    try:
        yield db
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()