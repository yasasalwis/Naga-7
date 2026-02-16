
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from ...database.session import get_session
from ...models.user import User
from ...schemas.user import UserSchema, UserCreate
from ..auth import get_current_active_user, pwd_context

router = APIRouter(prefix="/users", tags=["Users"])

@router.post("/", response_model=UserSchema)
async def create_user(user: UserCreate, session: AsyncSession = Depends(get_session)):
    stmt = select(User).where(User.username == user.username)
    result = await session.execute(stmt)
    if result.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Username already registered")
    
    hashed_password = pwd_context.hash(user.password)
    db_user = User(
        username=user.username,
        email=user.email,
        hashed_password=hashed_password,
        role=user.role
    )
    session.add(db_user)
    await session.commit()
    await session.refresh(db_user)
    return db_user

@router.get("/me", response_model=UserSchema)
async def read_users_me(current_user: User = Depends(get_current_active_user)):
    return current_user
