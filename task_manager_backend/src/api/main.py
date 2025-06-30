"""Main FastAPI app for Task Manager backend.

Implements all CRUD routes for managing tasks in a SQLite database using SQLAlchemy ORM,
with proper API documentation, validation, and business logic for listing, updating,
deleting, filtering, and marking complete/incomplete.

OpenAPI docs available at /docs.
"""

from typing import List, Optional
from fastapi import FastAPI, HTTPException, Query, status, Depends
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import (
    Boolean, Column, DateTime, Integer, String,
    create_engine, desc, asc
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from pydantic import BaseModel, Field, validator
from datetime import datetime


# DATABASE CONFIG
SQLALCHEMY_DATABASE_URL = "sqlite:///./tasks.sqlite3"
engine = create_engine(
    SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


# SQLAlchemy Task Model
class Task(Base):
    __tablename__ = "tasks"
    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(256), nullable=False)
    description = Column(String(1024), nullable=True)
    completed = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, nullable=False)


# Create tables at startup
Base.metadata.create_all(bind=engine)


# Pydantic Schemas
class TaskBase(BaseModel):
    title: str = Field(
        ..., min_length=1, max_length=256, description="Title of the task"
    )
    description: Optional[str] = Field(
        None, max_length=1024, description="Detailed description (optional)"
    )

    # PUBLIC_INTERFACE
    @validator("title")
    def title_not_empty(cls, v):
        if not v.strip():
            raise ValueError("Title must not be empty or whitespace")
        return v


class TaskCreate(TaskBase):
    pass


class TaskUpdate(BaseModel):
    title: Optional[str] = Field(
        None, min_length=1, max_length=256, description="Title of the task"
    )
    description: Optional[str] = Field(
        None, max_length=1024, description="Detailed description (optional)"
    )
    completed: Optional[bool] = Field(None, description="Completion status")

    # PUBLIC_INTERFACE
    @validator("title")
    def title_not_empty(cls, v):
        if v is not None and not v.strip():
            raise ValueError("Title must not be empty or whitespace")
        return v


class TaskOut(TaskBase):
    id: int
    completed: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        orm_mode = True


# FastAPI app setup
app = FastAPI(
    title="Task Manager API",
    version="1.0.0",
    description=(
        "REST API for managing tasks: create, read, update, delete, "
        "mark complete/incomplete. Supports filtering and sorting."
    ),
)


# CORS - allow all for MVP
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Dependency for session
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# HEALTH CHECK: For backend liveness
@app.get("/", tags=["Health"], summary="Health check", response_description="API is running")
# PUBLIC_INTERFACE
def health_check():
    """Health check endpoint."""
    return {"message": "Healthy"}


# CREATE TASK
@app.post(
    "/tasks",
    response_model=TaskOut,
    status_code=status.HTTP_201_CREATED,
    tags=["Tasks"],
    summary="Create a new task",
)
# PUBLIC_INTERFACE
def create_task(task: TaskCreate, db: Session = Depends(get_db)):
    """Create a new task.

    Parameters:
        - title: str (required)
        - description: str (optional)
    """
    db_task = Task(
        title=task.title.strip(),
        description=task.description.strip() if task.description else None,
        completed=False,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(db_task)
    db.commit()
    db.refresh(db_task)
    return db_task


# GET ALL TASKS (List)
@app.get(
    "/tasks",
    response_model=List[TaskOut],
    tags=["Tasks"],
    summary="List all tasks",
)
# PUBLIC_INTERFACE
def list_tasks(
    db: Session = Depends(get_db),
    completed: Optional[bool] = Query(
        None, description="Filter by completion", example=False
    ),
    search: Optional[str] = Query(
        None, description="Search in task title/description"
    ),
    sort_by: Optional[str] = Query(
        "created_at", description="Sort by 'created_at', 'title', or 'updated_at'"
    ),
    sort_order: Optional[str] = Query(
        "desc", description="Sort 'asc' or 'desc'"
    ),
    limit: Optional[int] = Query(
        100, ge=1, le=200, description="Limit number of results"
    ),
    offset: Optional[int] = Query(
        0, ge=0, description="Pagination offset"
    ),
):
    """Get all tasks, optionally filtered and sorted."""
    query = db.query(Task)

    if completed is not None:
        query = query.filter(Task.completed == completed)
    if search:
        like = f"%{search}%"
        query = query.filter(
            (Task.title.ilike(like)) | (Task.description.ilike(like))
        )
    if sort_by not in {"created_at", "updated_at", "title"}:
        sort_by = "created_at"
    sort_col = getattr(Task, sort_by)
    if sort_order == "asc":
        query = query.order_by(asc(sort_col))
    else:
        query = query.order_by(desc(sort_col))
    tasks = query.offset(offset).limit(limit).all()
    return tasks


# GET SINGLE TASK
@app.get(
    "/tasks/{task_id}",
    response_model=TaskOut,
    tags=["Tasks"],
    summary="Get a task by id",
)
# PUBLIC_INTERFACE
def get_task(task_id: int, db: Session = Depends(get_db)):
    """Get a specific task by its id."""
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


# UPDATE TASK (edit, mark as complete/incomplete)
@app.put(
    "/tasks/{task_id}",
    response_model=TaskOut,
    tags=["Tasks"],
    summary="Update task details or mark completion status",
)
# PUBLIC_INTERFACE
def update_task(task_id: int, update: TaskUpdate, db: Session = Depends(get_db)):
    """Update task fields, or mark as (in)complete.

    Fields not provided will not be modified.
    """
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    any_update = False

    if update.title is not None:
        task.title = update.title.strip()
        any_update = True
    if update.description is not None:
        task.description = update.description.strip() if update.description else None
        any_update = True
    if update.completed is not None:
        task.completed = update.completed
        any_update = True

    if any_update:
        task.updated_at = datetime.utcnow()
        db.commit()
        db.refresh(task)
    return task


# DELETE TASK
@app.delete(
    "/tasks/{task_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    tags=["Tasks"],
    summary="Delete a task by id",
)
# PUBLIC_INTERFACE
def delete_task(task_id: int, db: Session = Depends(get_db)):
    """Delete a task."""
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    db.delete(task)
    db.commit()
    return
