from datetime import datetime, timedelta
from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from ..database.session import get_session
from ..models.user import User

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

# Password hashing context
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=15)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


async def get_current_user(token: str = Depends(oauth2_scheme), session: AsyncSession = Depends(get_session)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    result = await session.execute(select(User).where(User.username == username))
    user = result.scalar_one_or_none()

    if user is None:
        raise credentials_exception
    return user


async def get_current_active_user(current_user: User = Depends(get_current_user)):
    if not current_user.is_active:
        raise HTTPException(status_code=400, detail="Inactive user")
    return current_user


# Agent API Key Authentication
from fastapi import Security
from fastapi.security import APIKeyHeader
from ..models.agent import Agent

agent_api_key_header = APIKeyHeader(name="X-Agent-API-Key", auto_error=True)


async def get_agent_from_api_key(
        api_key: str = Security(agent_api_key_header),
        session: AsyncSession = Depends(get_session)
) -> Agent:
    """
    Validates agent API key against database using O(1) prefix lookup.
    Production-ready implementation with indexed prefix for fast lookup.
    """
    # Extract prefix (first 16 characters) for O(1) indexed lookup
    api_key_prefix = api_key[:16] if len(api_key) >= 16 else api_key

    # Fast O(1) lookup by indexed prefix
    result = await session.execute(
        select(Agent).where(Agent.api_key_prefix == api_key_prefix)
    )
    agent = result.scalar_one_or_none()

    # Verify the full API key hash
    if agent and pwd_context.verify(api_key, agent.api_key_hash):
        return agent

    # Invalid API key or no matching agent
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid API key"
    )
