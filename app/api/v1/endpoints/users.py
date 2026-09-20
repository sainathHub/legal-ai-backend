from typing import Annotated, List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_active_superuser, get_current_active_user, get_db
from app.core.security import get_password_hash
from app.models.user import User
from app.schemas.user import UserRead, UserUpdate

router = APIRouter()


@router.patch("/me", response_model=UserRead)
async def update_my_profile(
    user_in: UserUpdate,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: AsyncSession = Depends(get_db),
) -> User:
    """
    Update the authenticated user's own profile information.
    """
    if user_in.email is not None and user_in.email != current_user.email:
        # Check if email is already taken
        result = await db.execute(select(User).where(User.email == user_in.email.lower()))
        if result.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email is already taken by another account",
            )
        current_user.email = user_in.email.lower()

    if user_in.full_name is not None:
        current_user.full_name = user_in.full_name

    if user_in.password is not None:
        current_user.hashed_password = get_password_hash(user_in.password)

    db.add(current_user)
    await db.commit()
    await db.refresh(current_user)
    return current_user


@router.get("/", response_model=List[UserRead])
async def list_users(
    skip: int = 0,
    limit: int = 50,
    _: Annotated[User, Depends(get_current_active_superuser)] = None,
    db: AsyncSession = Depends(get_db),
) -> List[User]:
    """
    List all registered users. Restricted to administrators/superusers.
    """
    result = await db.execute(select(User).offset(skip).limit(limit))
    return list(result.scalars().all())


@router.get("/{user_id}", response_model=UserRead)
async def get_user_by_id(
    user_id: str,
    _: Annotated[User, Depends(get_current_active_superuser)] = None,
    db: AsyncSession = Depends(get_db),
) -> User:
    """
    Get user profile by UUID. Restricted to administrators/superusers.
    """
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )
    return user
