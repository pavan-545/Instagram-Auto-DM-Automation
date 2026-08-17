import os
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import declarative_base
from backend.config import settings

Base = declarative_base()

db_url = settings.DATABASE_URL
if db_url.startswith("postgresql://"):
    db_url = db_url.replace("postgresql://", "postgresql+asyncpg://", 1)

connect_args = {}
engine_kwargs = {"echo": False}

if "sqlite" in db_url:
    connect_args["check_same_thread"] = False
    connect_args["timeout"] = 60.0
    engine_kwargs["connect_args"] = connect_args

engine = create_async_engine(db_url, **engine_kwargs)
async_session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

async def init_db():
    if "sqlite" in db_url:
        from sqlalchemy import text
        async with engine.begin() as conn:
            await conn.execute(text("PRAGMA journal_mode=WAL;"))
            await conn.execute(text("PRAGMA synchronous=NORMAL;"))
            await conn.execute(text("PRAGMA busy_timeout=60000;"))
            await conn.execute(text("PRAGMA cache_size=-20000;"))
            await conn.execute(text("PRAGMA temp_store=MEMORY;"))
    
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

async def get_db():
    async with async_session_factory() as session:
        try:
            yield session
        finally:
            await session.close()
