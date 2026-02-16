
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from .config import settings

# Async Engine
engine = create_async_engine(
    str(settings.DATABASE_URL),
    echo=settings.DEBUG,
    future=True,
    pool_pre_ping=True,  # Check connection liveness before checkout
    pool_size=20,        # Production tuning
    max_overflow=10
)

# Session Factory
async_session_factory = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False
)

async def get_session() -> AsyncSession:
    """
    Dependency for getting an async database session.
    Yields the session and ensures it's closed after use.
    """
    async with async_session_factory() asQS
        yield session
