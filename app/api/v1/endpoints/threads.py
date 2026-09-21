import uuid
from typing import Annotated, List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_active_user, get_db
from app.models.message import Message
from app.models.project import Project
from app.models.thread import Thread
from app.models.user import User
from app.schemas.message import MessageRead
from app.schemas.thread import ThreadCreate, ThreadRead, ThreadUpdate

router = APIRouter()


async def _verify_project_ownership(
    project_id: uuid.UUID,
    user_id: uuid.UUID,
    db: AsyncSession,
) -> Project:
    """Helper to verify that a project exists and is owned by the user."""
    query = select(Project).where(Project.id == project_id, Project.user_id == user_id)
    result = await db.execute(query)
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Case project not found or access denied",
        )
    return project


@router.post("/projects/{project_id}/threads", response_model=ThreadRead, status_code=status.HTTP_201_CREATED)
async def create_thread(
    project_id: uuid.UUID,
    thread_in: ThreadCreate,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: AsyncSession = Depends(get_db),
) -> Thread:
    """
    Create a new chat session thread under a specific case project.
    (e.g., 'Drafting Bail Application' or 'Cross-Exam Prep')
    """
    await _verify_project_ownership(project_id, current_user.id, db)

    thread = Thread(
        project_id=project_id,
        title=thread_in.title,
    )
    db.add(thread)
    await db.commit()
    await db.refresh(thread)
    return thread


@router.get("/projects/{project_id}/threads", response_model=List[ThreadRead])
async def list_project_threads(
    project_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: AsyncSession = Depends(get_db),
) -> List[Thread]:
    """
    List all chat session threads under a specific case project.
    Fast query using indexed `project_id`.
    """
    await _verify_project_ownership(project_id, current_user.id, db)

    query = (
        select(Thread)
        .where(Thread.project_id == project_id)
        .order_by(Thread.created_at.asc())
    )
    result = await db.execute(query)
    return list(result.scalars().all())


@router.get("/threads/{thread_id}", response_model=ThreadRead)
async def get_thread_by_id(
    thread_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: AsyncSession = Depends(get_db),
) -> Thread:
    """
    Retrieve a single chat session thread by ID, ensuring user ownership of the parent project.
    """
    query = (
        select(Thread)
        .join(Project, Thread.project_id == Project.id)
        .where(Thread.id == thread_id, Project.user_id == current_user.id)
    )
    result = await db.execute(query)
    thread = result.scalar_one_or_none()

    if not thread:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Chat thread not found or access denied",
        )
    return thread


@router.patch("/threads/{thread_id}", response_model=ThreadRead)
async def update_thread(
    thread_id: uuid.UUID,
    thread_in: ThreadUpdate,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: AsyncSession = Depends(get_db),
) -> Thread:
    """
    Rename or update a chat session thread.
    """
    query = (
        select(Thread)
        .join(Project, Thread.project_id == Project.id)
        .where(Thread.id == thread_id, Project.user_id == current_user.id)
    )
    result = await db.execute(query)
    thread = result.scalar_one_or_none()

    if not thread:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Chat thread not found or access denied",
        )

    if thread_in.title is not None:
        thread.title = thread_in.title

    db.add(thread)
    await db.commit()
    await db.refresh(thread)
    return thread


@router.delete("/threads/{thread_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_thread(
    thread_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: AsyncSession = Depends(get_db),
) -> None:
    """
    Delete a chat session thread.
    """
    query = (
        select(Thread)
        .join(Project, Thread.project_id == Project.id)
        .where(Thread.id == thread_id, Project.user_id == current_user.id)
    )
    result = await db.execute(query)
    thread = result.scalar_one_or_none()

    if not thread:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Chat thread not found or access denied",
        )

    await db.delete(thread)
    await db.commit()
    return None


@router.get("/threads/{thread_id}/messages", response_model=List[MessageRead])
async def get_thread_messages(
    thread_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: AsyncSession = Depends(get_db),
) -> List[Message]:
    """
    Retrieve all conversation messages and cited precedents in a thread in chronological order.
    """
    query = (
        select(Thread)
        .join(Project, Thread.project_id == Project.id)
        .where(Thread.id == thread_id, Project.user_id == current_user.id)
    )
    result = await db.execute(query)
    if not result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Chat thread not found or access denied",
        )

    msg_query = (
        select(Message)
        .where(Message.thread_id == thread_id)
        .order_by(Message.created_at.asc())
    )
    msg_result = await db.execute(msg_query)
    return list(msg_result.scalars().all())


@router.delete("/threads/{thread_id}/messages", status_code=status.HTTP_204_NO_CONTENT)
async def clear_thread_messages(
    thread_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: AsyncSession = Depends(get_db),
) -> None:
    """
    Clear all conversation messages in a thread while keeping the thread active.
    """
    query = (
        select(Thread)
        .join(Project, Thread.project_id == Project.id)
        .where(Thread.id == thread_id, Project.user_id == current_user.id)
    )
    result = await db.execute(query)
    if not result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Chat thread not found or access denied",
        )

    await db.execute(delete(Message).where(Message.thread_id == thread_id))
    await db.commit()
    return None
