from pydantic import BaseModel, Field, ConfigDict, EmailStr
from typing import List, Optional, Literal
import uuid
from datetime import datetime, timezone

# User Models
class User(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    email: EmailStr
    name: str = ""
    role: str = "agent"
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

class UserCreate(BaseModel):
    email: EmailStr
    password: str
    name: str

class UserLogin(BaseModel):
    email: EmailStr
    password: str

class TokenResponse(BaseModel):
    token: str
    user: User

# Message Models
class Message(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    conversation_id: str
    sender_type: Literal["customer", "agent", "ai"] = "customer"
    sender_name: str
    content: str
    channel: Literal["email", "whatsapp", "slack", "telegram"] = "email"
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict = {}

class MessageCreate(BaseModel):
    conversation_id: str
    content: str
    sender_name: str
    sender_type: Literal["customer", "agent", "ai"] = "customer"
    channel: Literal["email", "whatsapp", "slack", "telegram"] = "email"

class AIAnalysis(BaseModel):
    intent: str
    sentiment: str
    priority: str
    is_spam: bool
    confidence: float
    suggested_response: Optional[str] = None

# Conversation Models
class Conversation(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    customer_name: str
    customer_contact: str
    channel: str
    status: str = "open"
    priority: str = "medium"
    sentiment: str = "neutral"
    intent: str = "general"
    assigned_to: Optional[str] = None
    last_message_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    unread_count: int = 0

class ConversationFilter(BaseModel):
    channel: Optional[str] = None
    status: Optional[str] = None
    priority: Optional[str] = None
    sentiment: Optional[str] = None
    search: Optional[str] = None

class AgentResponse(BaseModel):
    conversation_id: str
    content: str

# Integration Models
class TelegramToken(BaseModel):
    token: str

class SlackToken(BaseModel):
    token: str
