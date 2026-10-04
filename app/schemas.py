from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models import Role, TicketStatus


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=1, max_length=256)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserRead(BaseModel):
    id: int
    email: str
    role: Role

    model_config = ConfigDict(from_attributes=True)


class TicketCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=3, max_length=120)
    description: str = Field(min_length=5, max_length=4000)


class MessageCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    body: str = Field(min_length=1, max_length=4000)


class CloseTicketRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    resolution: str = Field(min_length=3, max_length=4000)


class MessageRead(BaseModel):
    id: int
    author_id: int
    body: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class TicketRead(BaseModel):
    id: int
    title: str
    description: str
    status: TicketStatus
    resolution: str | None
    author_id: int
    assignee_id: int | None
    created_at: datetime
    updated_at: datetime
    messages: list[MessageRead]


class InternalNoteRead(MessageRead):
    pass


class HealthResponse(BaseModel):
    status: str
