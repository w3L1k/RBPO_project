from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, status
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import Base, SessionLocal, engine
from app.dependencies import CurrentUser, DbSession
from app.models import AuditEvent, Message, Role, Ticket, TicketStatus, User
from app.schemas import (
    CloseTicketRequest,
    HealthResponse,
    InternalNoteRead,
    LoginRequest,
    MessageCreate,
    MessageRead,
    TicketCreate,
    TicketRead,
    TokenResponse,
    UserRead,
)
from app.security import create_access_token, hash_password, verify_password


def seed_demo_users(db: Session) -> None:
    if db.scalar(select(User.id).limit(1)) is not None:
        return
    password = get_settings().seed_password
    demo_users = [
        User(email="user1@campus.local", password_hash=hash_password(password), role=Role.USER),
        User(email="user2@campus.local", password_hash=hash_password(password), role=Role.USER),
        User(
            email="specialist@campus.local",
            password_hash=hash_password(password),
            role=Role.SPECIALIST,
        ),
    ]
    db.add_all(demo_users)
    db.commit()


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    get_settings()
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        seed_demo_users(db)
    yield


app = FastAPI(
    title="Campus Helpdesk",
    version="0.1.0",
    description="Minimal runnable foundation for the RBPO course project",
    lifespan=lifespan,
)


def require_role(user: User, role: Role) -> None:
    if user.role != role:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient role")


def get_ticket_or_404(db: Session, ticket_id: int) -> Ticket:
    ticket = db.get(Ticket, ticket_id)
    if ticket is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ticket not found")
    return ticket


def require_ticket_view(ticket: Ticket, user: User) -> None:
    if user.role == Role.USER and ticket.author_id != user.id:
        # Deliberately hide whether another user's ticket exists.
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ticket not found")
    if user.role == Role.SPECIALIST and not (
        ticket.assignee_id == user.id
        or ticket.status in (TicketStatus.OPEN, TicketStatus.REOPENED)
    ):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ticket not found")


def require_assigned_specialist(ticket: Ticket, user: User) -> None:
    require_role(user, Role.SPECIALIST)
    if ticket.assignee_id != user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the assigned specialist may perform this action",
        )


def ticket_view(db: Session, ticket: Ticket) -> TicketRead:
    public_messages = db.scalars(
        select(Message)
        .where(Message.ticket_id == ticket.id, Message.is_internal.is_(False))
        .order_by(Message.created_at, Message.id)
    ).all()
    return TicketRead(
        id=ticket.id,
        title=ticket.title,
        description=ticket.description,
        status=ticket.status,
        resolution=ticket.resolution,
        author_id=ticket.author_id,
        assignee_id=ticket.assignee_id,
        created_at=ticket.created_at,
        updated_at=ticket.updated_at,
        messages=[MessageRead.model_validate(message) for message in public_messages],
    )


def audit(db: Session, ticket_id: int, actor_id: int, action: str) -> None:
    db.add(AuditEvent(ticket_id=ticket_id, actor_id=actor_id, action=action))


@app.get("/health", response_model=HealthResponse, tags=["system"])
def health() -> HealthResponse:
    return HealthResponse(status="ok")


@app.post("/auth/login", response_model=TokenResponse, tags=["auth"])
def login(payload: LoginRequest, db: DbSession) -> TokenResponse:
    user = db.scalar(select(User).where(User.email == payload.email))
    if user is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    return TokenResponse(access_token=create_access_token(user.id, user.role))


@app.get("/users/me", response_model=UserRead, tags=["auth"])
def read_me(user: CurrentUser) -> User:
    return user


@app.post(
    "/tickets",
    response_model=TicketRead,
    status_code=status.HTTP_201_CREATED,
    tags=["tickets"],
)
def create_ticket(payload: TicketCreate, user: CurrentUser, db: DbSession) -> TicketRead:
    require_role(user, Role.USER)
    ticket = Ticket(
        title=payload.title,
        description=payload.description,
        author_id=user.id,
        status=TicketStatus.OPEN,
    )
    db.add(ticket)
    db.flush()
    audit(db, ticket.id, user.id, "ticket_created")
    db.commit()
    db.refresh(ticket)
    return ticket_view(db, ticket)


@app.get("/tickets", response_model=list[TicketRead], tags=["tickets"])
def list_tickets(user: CurrentUser, db: DbSession) -> list[TicketRead]:
    query = select(Ticket).order_by(Ticket.created_at, Ticket.id)
    if user.role == Role.USER:
        query = query.where(Ticket.author_id == user.id)
    else:
        query = query.where(
            (Ticket.assignee_id == user.id)
            | (Ticket.status.in_([TicketStatus.OPEN, TicketStatus.REOPENED]))
        )
    tickets = db.scalars(query).all()
    return [ticket_view(db, ticket) for ticket in tickets]


@app.get("/tickets/{ticket_id}", response_model=TicketRead, tags=["tickets"])
def read_ticket(ticket_id: int, user: CurrentUser, db: DbSession) -> TicketRead:
    ticket = get_ticket_or_404(db, ticket_id)
    require_ticket_view(ticket, user)
    return ticket_view(db, ticket)


@app.post("/tickets/{ticket_id}/accept", response_model=TicketRead, tags=["workflow"])
def accept_ticket(ticket_id: int, user: CurrentUser, db: DbSession) -> TicketRead:
    require_role(user, Role.SPECIALIST)
    result = db.execute(
        update(Ticket)
        .where(
            Ticket.id == ticket_id,
            Ticket.assignee_id.is_(None),
            Ticket.status.in_([TicketStatus.OPEN, TicketStatus.REOPENED]),
        )
        .values(assignee_id=user.id, status=TicketStatus.IN_PROGRESS)
    )
    if result.rowcount != 1:
        db.rollback()
        get_ticket_or_404(db, ticket_id)
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Ticket is not available for acceptance",
        )
    audit(db, ticket_id, user.id, "ticket_accepted")
    db.commit()
    return ticket_view(db, get_ticket_or_404(db, ticket_id))


@app.post(
    "/tickets/{ticket_id}/messages",
    response_model=MessageRead,
    status_code=status.HTTP_201_CREATED,
    tags=["messages"],
)
def add_public_message(
    ticket_id: int, payload: MessageCreate, user: CurrentUser, db: DbSession
) -> Message:
    ticket = get_ticket_or_404(db, ticket_id)
    require_ticket_view(ticket, user)
    if user.role == Role.SPECIALIST:
        require_assigned_specialist(ticket, user)
    message = Message(
        ticket_id=ticket.id,
        author_id=user.id,
        body=payload.body,
        is_internal=False,
    )
    db.add(message)
    db.commit()
    db.refresh(message)
    return message


@app.post(
    "/tickets/{ticket_id}/internal-notes",
    response_model=InternalNoteRead,
    status_code=status.HTTP_201_CREATED,
    tags=["internal notes"],
)
def add_internal_note(
    ticket_id: int, payload: MessageCreate, user: CurrentUser, db: DbSession
) -> Message:
    ticket = get_ticket_or_404(db, ticket_id)
    require_assigned_specialist(ticket, user)
    note = Message(
        ticket_id=ticket.id,
        author_id=user.id,
        body=payload.body,
        is_internal=True,
    )
    db.add(note)
    db.commit()
    db.refresh(note)
    return note


@app.get(
    "/tickets/{ticket_id}/internal-notes",
    response_model=list[InternalNoteRead],
    tags=["internal notes"],
)
def list_internal_notes(ticket_id: int, user: CurrentUser, db: DbSession) -> list[Message]:
    ticket = get_ticket_or_404(db, ticket_id)
    require_assigned_specialist(ticket, user)
    return list(
        db.scalars(
            select(Message)
            .where(Message.ticket_id == ticket.id, Message.is_internal.is_(True))
            .order_by(Message.created_at, Message.id)
        ).all()
    )


@app.post("/tickets/{ticket_id}/close", response_model=TicketRead, tags=["workflow"])
def close_ticket(
    ticket_id: int,
    payload: CloseTicketRequest,
    user: CurrentUser,
    db: DbSession,
) -> TicketRead:
    ticket = get_ticket_or_404(db, ticket_id)
    require_assigned_specialist(ticket, user)
    if ticket.status != TicketStatus.IN_PROGRESS:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Only an in-progress ticket may be closed",
        )
    ticket.status = TicketStatus.CLOSED
    ticket.resolution = payload.resolution
    audit(db, ticket.id, user.id, "ticket_closed")
    db.commit()
    db.refresh(ticket)
    return ticket_view(db, ticket)


@app.post("/tickets/{ticket_id}/reopen", response_model=TicketRead, tags=["workflow"])
def reopen_ticket(
    ticket_id: int, payload: MessageCreate, user: CurrentUser, db: DbSession
) -> TicketRead:
    require_role(user, Role.USER)
    ticket = get_ticket_or_404(db, ticket_id)
    if ticket.author_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ticket not found")
    if ticket.status != TicketStatus.CLOSED:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Only a closed ticket may be reopened",
        )
    db.add(
        Message(
            ticket_id=ticket.id,
            author_id=user.id,
            body=payload.body,
            is_internal=False,
        )
    )
    ticket.status = TicketStatus.REOPENED
    ticket.assignee_id = None
    audit(db, ticket.id, user.id, "ticket_reopened")
    db.commit()
    db.refresh(ticket)
    return ticket_view(db, ticket)
