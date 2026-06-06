from fastapi import FastAPI, APIRouter, HTTPException, Depends, status, WebSocket, WebSocketDisconnect
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import asyncio
import logging
from pathlib import Path
from pydantic import BaseModel, Field, ConfigDict, EmailStr
from typing import List, Optional, Literal
import uuid
from datetime import datetime, timezone, timedelta
import jwt
import bcrypt
from services.ai_service import ai_service
from services.gmail_service import gmail_service
from websocket.manager import connection_manager
from utils.mongo_serializer import prepare_api_response, prepare_websocket_message
import json
import os
from bson import ObjectId

def serialize_mongo_doc(doc):
    """Convert MongoDB document to JSON-serializable format."""
    if doc is None:
        return None
    
    if isinstance(doc, ObjectId):
        return str(doc)
    
    if isinstance(doc, datetime):
        return doc.isoformat()
    
    if isinstance(doc, dict):
        return {key: serialize_mongo_doc(value) for key, value in doc.items()}
    
    if isinstance(doc, list):
        return [serialize_mongo_doc(item) for item in doc]
    
    return doc

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

mongo_url = os.environ.get('MONGO_URL', 'mongodb://localhost:27017')
try:
    client = AsyncIOMotorClient(mongo_url, serverSelectionTimeoutMS=1000)
    db = client[os.environ.get('DB_NAME', 'test_database')]
except Exception as e:
    print(f"Warning: MongoDB connection failed - {e}")
    client = None
    db = None

app = FastAPI()
api_router = APIRouter(prefix="/api")
# HTTPBearer with auto_error=False to handle missing credentials gracefully
security = HTTPBearer(auto_error=False)

# Add CORS middleware first, before router
app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get('CORS_ORIGINS', '*').split(','),
    allow_methods=["*"],
    allow_headers=["*"],
)

# ============================================================================
# WebSocket Connection Manager
# ============================================================================
class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []
    
    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info(f"WebSocket connected. Total connections: {len(self.active_connections)}")
    
    def disconnect(self, websocket: WebSocket):
        try:
            self.active_connections.remove(websocket)
            logger.info(f"WebSocket disconnected. Total connections: {len(self.active_connections)}")
        except ValueError:
            # Connection not in list - safe to ignore
            pass
    
    async def broadcast(self, message: dict):
        """Broadcast message to all connected clients"""
        disconnected = []
        for connection in self.active_connections:
            try:
                # Serialize message before sending
                serialized_message = serialize_mongo_doc(message)
                await connection.send_json(serialized_message)
            except Exception as e:
                logger.error(f"Error sending WebSocket message: {str(e)}")
                disconnected.append(connection)
        
        # Remove dead connections
        for conn in disconnected:
            if conn in self.active_connections:
                self.active_connections.remove(conn)

manager = ConnectionManager()

JWT_SECRET = os.environ.get('JWT_SECRET', 'convo-sphere-secret-key-2025')
JWT_ALGORITHM = os.environ.get('JWT_ALGORITHM', 'HS256')
EMERGENT_LLM_KEY = os.environ.get('EMERGENT_LLM_KEY')

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Models
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

class AIAnalysis(BaseModel):
    intent: str
    sentiment: str
    priority: str
    is_spam: bool
    confidence: float
    suggested_response: Optional[str] = None

class MessageCreate(BaseModel):
    conversation_id: str
    content: str
    sender_name: str
    sender_type: Literal["customer", "agent", "ai"] = "customer"
    channel: Literal["email", "whatsapp", "slack", "telegram"] = "email"

class ConversationFilter(BaseModel):
    channel: Optional[str] = None
    status: Optional[str] = None
    priority: Optional[str] = None
    sentiment: Optional[str] = None
    search: Optional[str] = None

class AgentResponse(BaseModel):
    conversation_id: str
    content: str

class TelegramToken(BaseModel):
    token: str

class SlackToken(BaseModel):
    token: str

# Helper Functions
def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

def verify_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode('utf-8'), hashed.encode('utf-8'))

def create_token(user_id: str) -> str:
    payload = {
        'user_id': user_id,
        'exp': datetime.now(timezone.utc) + timedelta(days=7)
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)

async def get_current_user(credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)):
    """Authenticate user from Bearer token"""
    try:
        # Check if credentials are provided
        if not credentials:
            logger.warning("No credentials provided")
            raise HTTPException(status_code=401, detail="Missing credentials")
        
        token = credentials.credentials
        if not token:
            logger.warning("Empty token")
            raise HTTPException(status_code=401, detail="Empty token")
        
        logger.debug(f"Decoding token: {token[:30]}...")
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        user_id = payload.get('user_id')
        
        if not user_id:
            logger.warning("No user_id in token")
            raise HTTPException(status_code=401, detail="Invalid token payload")
        
        if db is None:
            logger.error("Database connection lost")
            raise HTTPException(status_code=503, detail="Database unavailable")
        
        logger.debug(f"Looking up user: {user_id}")
        user = await db.users.find_one({'id': user_id}, {'_id': 0})
        if not user:
            logger.warning(f"User not found: {user_id}")
            raise HTTPException(status_code=401, detail="User not found")
        
        logger.info(f"User authenticated: {user.get('email', user_id)}")
        return User(**user)
    
    except jwt.ExpiredSignatureError as e:
        logger.warning(f"Token expired: {str(e)}")
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError as e:
        logger.warning(f"Invalid token: {str(e)}")
        raise HTTPException(status_code=401, detail="Invalid token")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Auth error: {type(e).__name__}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=401, detail=f"Authentication failed: {str(e)}")

# AI Analysis Function
async def analyze_message_with_ai(content: str, conversation_history: List[str] = None) -> AIAnalysis:
    return AIAnalysis(
        intent="general",
        sentiment="neutral",
        priority="medium",
        is_spam=False,
        confidence=0.5,
        suggested_response="Thank you for reaching out. An agent will assist you shortly."
    )

# Auth Endpoints
@api_router.post("/auth/register", response_model=TokenResponse)
async def register(user_data: UserCreate):
    existing = await db.users.find_one({'email': user_data.email}, {'_id': 0})
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")
    
    user = User(email=user_data.email, name=user_data.name)
    user_doc = user.model_dump()
    user_doc['password'] = hash_password(user_data.password)
    
    await db.users.insert_one(user_doc)
    token = create_token(user.id)
    
    return TokenResponse(token=token, user=user)

@api_router.post("/auth/login", response_model=TokenResponse)
async def login(credentials: UserLogin):
    try:
        if db is None:
            raise HTTPException(status_code=503, detail="Database connection unavailable")
        
        # Check if user exists in database
        user_doc = await db.users.find_one({'email': credentials.email}, {'_id': 0})
        if not user_doc:
            logger.warning(f"Login attempt - user not found: {credentials.email}")
            raise HTTPException(status_code=401, detail="Invalid credentials")
        
        # Verify password
        password_valid = verify_password(credentials.password, user_doc['password'])
        if not password_valid:
            logger.warning(f"Login attempt - invalid password for: {credentials.email}")
            raise HTTPException(status_code=401, detail="Invalid credentials")
        
        # Convert datetime string if needed
        if isinstance(user_doc['created_at'], str):
            pass  # already a string, no conversion needed
        elif isinstance(user_doc['created_at'], datetime):
            user_doc['created_at'] = user_doc['created_at'].isoformat()
        
        # Create user object and token
        user = User(**{k: v for k, v in user_doc.items() if k != 'password'})
        token = create_token(user.id)
        
        logger.info(f"Successful login: {credentials.email}")
        logger.info(f"Response: token={token[:20]}..., user={user.email}")
        response = TokenResponse(token=token, user=user)
        logger.info(f"TokenResponse created: {response}")
        return response
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Login error for {credentials.email}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Login error: {str(e)}")

@api_router.get("/auth/me", response_model=User)
async def get_me(current_user: User = Depends(get_current_user)):
    return current_user

@api_router.post("/auth/logout")
async def logout(current_user: User = Depends(get_current_user)):
    """Logout endpoint - client should remove token from localStorage"""
    return {"message": "Logged out successfully"}

@api_router.get("/auth/debug/users")
async def debug_users():
    """DEBUG ONLY - List all users in database"""
    try:
        if db is None:
            return {"error": "Database not connected"}
        
        users = await db.users.find({}, {'_id': 0, 'password': 0}).to_list(100)
        return {"users": users, "count": len(users), "total": await db.users.count_documents({})}
    except Exception as e:
        return {"error": str(e), "type": type(e).__name__}

# Message Ingestion
@api_router.post("/messages/ingest", response_model=Message)
async def ingest_message(msg_data: MessageCreate, current_user: User = Depends(get_current_user)):
    if db is None:
        raise HTTPException(status_code=503, detail="Database connection failed")
    
    try:
        conv = await db.conversations.find_one({'id': msg_data.conversation_id}, {'_id': 0})
        if not conv:
            raise HTTPException(status_code=404, detail="Conversation not found")
        
        message = Message(
            conversation_id=msg_data.conversation_id,
            sender_type=msg_data.sender_type,
            sender_name=msg_data.sender_name,
            content=msg_data.content,
            channel=msg_data.channel
        )
        
        msg_doc = message.model_dump()
        msg_doc['timestamp'] = msg_doc['timestamp'].isoformat()
        await db.messages.insert_one(msg_doc)
        
        if msg_data.sender_type == "customer":
            analysis = await analyze_message_with_ai(msg_data.content)
            
            update_data = {
                'last_message_at': datetime.now(timezone.utc).isoformat(),
                'sentiment': analysis.sentiment,
                'intent': analysis.intent,
                'priority': analysis.priority,
                'unread_count': (conv.get('unread_count', 0) + 1)
            }
            
            if analysis.confidence > 0.8 and analysis.suggested_response:
                auto_msg = Message(
                    conversation_id=msg_data.conversation_id,
                    sender_type="ai",
                    sender_name="AI Assistant",
                    content=analysis.suggested_response,
                    channel=msg_data.channel
                )
                auto_doc = auto_msg.model_dump()
                auto_doc['timestamp'] = auto_doc['timestamp'].isoformat()
                await db.messages.insert_one(auto_doc)
            
            await db.conversations.update_one(
                {'id': msg_data.conversation_id},
                {'$set': update_data}
            )
        
        # Broadcast new message to all connected WebSocket clients
        await manager.broadcast({
            "type": "new_message",
            "conversation_id": msg_data.conversation_id,
            "message": msg_doc,
            "timestamp": datetime.now(timezone.utc).isoformat()
        })
        
        return message
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error ingesting message: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error ingesting message: {str(e)}")

# Conversations
@api_router.post("/conversations", response_model=Conversation)
async def create_conversation(customer_name: str, customer_contact: str, channel: str, current_user: User = Depends(get_current_user)):
    conversation = Conversation(
        customer_name=customer_name,
        customer_contact=customer_contact,
        channel=channel
    )
    
    conv_doc = conversation.model_dump()
    conv_doc['last_message_at'] = conv_doc['last_message_at'].isoformat()
    conv_doc['created_at'] = conv_doc['created_at'].isoformat()
    
    await db.conversations.insert_one(conv_doc)
    return conversation

@api_router.post("/conversations/filter", response_model=List[Conversation])
async def get_conversations(filters: ConversationFilter, current_user: User = Depends(get_current_user)):
    query = {}
    if filters.channel:
        query['channel'] = filters.channel
    if filters.status:
        query['status'] = filters.status
    if filters.priority:
        query['priority'] = filters.priority
    if filters.sentiment:
        query['sentiment'] = filters.sentiment
    if filters.search:
        query['$or'] = [
            {'customer_name': {'$regex': filters.search, '$options': 'i'}},
            {'customer_contact': {'$regex': filters.search, '$options': 'i'}}
        ]
    
    conversations = await db.conversations.find(query, {'_id': 0}).sort('last_message_at', -1).to_list(100)
    
    for conv in conversations:
        if isinstance(conv.get('last_message_at'), str):
            conv['last_message_at'] = datetime.fromisoformat(conv['last_message_at'])
        if isinstance(conv.get('created_at'), str):
            conv['created_at'] = datetime.fromisoformat(conv['created_at'])
    
    return conversations

@api_router.get("/conversations/{conversation_id}", response_model=Conversation)
async def get_conversation(conversation_id: str, current_user: User = Depends(get_current_user)):
    conv = await db.conversations.find_one({'id': conversation_id}, {'_id': 0})
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
    
    if isinstance(conv.get('last_message_at'), str):
        conv['last_message_at'] = datetime.fromisoformat(conv['last_message_at'])
    if isinstance(conv.get('created_at'), str):
        conv['created_at'] = datetime.fromisoformat(conv['created_at'])
    
    return Conversation(**conv)

@api_router.get("/conversations/{conversation_id}/messages", response_model=List[Message])
async def get_conversation_messages(conversation_id: str, current_user: User = Depends(get_current_user)):
    messages = await db.messages.find({'conversation_id': conversation_id}, {'_id': 0}).sort('timestamp', 1).to_list(1000)
    
    for msg in messages:
        if isinstance(msg.get('timestamp'), str):
            msg['timestamp'] = datetime.fromisoformat(msg['timestamp'])
    
    return messages

# @api_router.post("/conversations/{conversation_id}/respond")
# async def agent_respond(conversation_id: str, agent_response: AgentResponse, current_user: User = Depends(get_current_user)):
#     # Fetch conversation
#     conv = await db.conversations.find_one({'id': conversation_id}, {'_id': 0})
#     if not conv:
#         raise HTTPException(status_code=404, detail="Conversation not found")
    
#     # Create agent message
#     message = Message(
#         conversation_id=conversation_id,
#         sender_type="agent",
#         sender_name=current_user.name,
#         content=agent_response.content,
#         channel=conv.get('channel', 'email')
#     )
    
#     # Insert message
#     msg_doc = message.model_dump()
#     msg_doc['timestamp'] = msg_doc['timestamp'].isoformat()
#     await db.messages.insert_one(msg_doc)
    
#     # Update conversation
#     await db.conversations.update_one(
#         {'id': conversation_id},
#         {'$set': {
#             'last_message_at': datetime.now(timezone.utc).isoformat(),
#             'unread_count': 0,
#             'status': 'waiting'
#         }}
#     )
    
#     return {"success": True, "message_id": message.id}

import requests

@api_router.post("/conversations/{conversation_id}/respond")
async def agent_respond(conversation_id: str, agent_response: AgentResponse, current_user: User = Depends(get_current_user)):

    # Fetch conversation
    conv = await db.conversations.find_one({'id': conversation_id}, {'_id': 0})
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")

    # Create agent message
    message = Message(
        conversation_id=conversation_id,
        sender_type="agent",
        sender_name=current_user.name,
        content=agent_response.content,
        channel=conv.get('channel', 'email')
    )

    # Insert message into MongoDB
    msg_doc = message.model_dump()
    msg_doc['timestamp'] = msg_doc['timestamp'].isoformat()
    await db.messages.insert_one(msg_doc)

    # Update conversation
    await db.conversations.update_one(
        {'id': conversation_id},
        {'$set': {
            'last_message_at': datetime.now(timezone.utc).isoformat(),
            'unread_count': 0,
            'status': 'waiting'
        }}
    )

    # SEND MESSAGE BASED ON CHANNEL
    try:

        # TELEGRAM
        if conv["channel"] == "telegram":

            integration = await db.integrations.find_one({
                "user_id": current_user.id,
                "service": "telegram"
            })

            if integration:
                token = integration["token"]
                chat_id = conv["customer_contact"]

                requests.post(
                    f"https://api.telegram.org/bot{token}/sendMessage",
                    json={
                        "chat_id": chat_id,
                        "text": agent_response.content
                    }
                )

        # SLACK
        if conv["channel"] == "slack":

            integration = await db.integrations.find_one({
                "user_id": current_user.id,
                "service": "slack"
            })

            if integration:
                token = integration["token"]

                requests.post(
                    "https://slack.com/api/chat.postMessage",
                    headers={
                        "Authorization": f"Bearer {token}",
                        "Content-Type": "application/json"
                    },
                    json={
                        "channel": conv["customer_contact"],
                        "text": agent_response.content
                    }
                )

    except Exception as e:
        logger.error(f"Message sending error: {str(e)}")

    # Broadcast agent message to all connected WebSocket clients
    await manager.broadcast({
        "type": "new_message",
        "conversation_id": conversation_id,
        "message": msg_doc,
        "timestamp": datetime.now(timezone.utc).isoformat()
    })

    return {"success": True, "message_id": message.id}

@api_router.get("/stats")
async def get_stats(current_user: User = Depends(get_current_user)):
    """Get dashboard statistics"""
    try:
        if db is None:
            logger.error("Database not connected for stats")
            raise HTTPException(status_code=503, detail="Database connection failed")
        
        logger.debug(f"Fetching stats for user: {current_user.email}")
        total_conversations = await db.conversations.count_documents({})
        open_conversations = await db.conversations.count_documents({'status': 'open'})
        total_messages = await db.messages.count_documents({})
        
        pipeline = [
            {'$group': {'_id': None, 'total_unread': {'$sum': '$unread_count'}}}
        ]
        unread_result = await db.conversations.aggregate(pipeline).to_list(1)
        total_unread = unread_result[0]['total_unread'] if unread_result else 0
        
        logger.info(f"Stats retrieved for {current_user.email}: {total_conversations} conversations")
        return {
            'total_conversations': total_conversations,
            'open_conversations': open_conversations,
            'total_messages': total_messages,
            'unread_messages': total_unread
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching stats: {type(e).__name__}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error fetching stats: {str(e)}")

# Telegram Integration
@api_router.post("/integrations/telegram/connect")
async def connect_telegram(
    request: TelegramToken,
    current_user: User = Depends(get_current_user)
):
    try:
        import requests
        
        token = request.token
        if not token:
            raise HTTPException(status_code=400, detail="Token is required")
        
        # Validate token with Telegram
        response = requests.get(
            f"https://api.telegram.org/bot{token}/getMe"
        )
        
        if response.status_code != 200:
            raise HTTPException(status_code=400, detail="Invalid Telegram token")
        
        bot_info = response.json()
        if not bot_info.get('ok'):
            raise HTTPException(status_code=400, detail="Telegram API error")
        
        # Store integration in database
        integration = {
            'user_id': current_user.id,
            'service': 'telegram',
            'token': token,
            'bot_id': bot_info['result']['id'],
            'bot_username': bot_info['result']['username'],
            'created_at': datetime.now(timezone.utc).isoformat(),
            'status': 'connected'
        }
        
        await db.integrations.update_one(
            {'user_id': current_user.id, 'service': 'telegram'},
            {'$set': integration},
            upsert=True
        )
        
        return {
            'success': True,
            'message': 'Telegram connected successfully',
            'bot_username': bot_info['result']['username']
        }
    except Exception as e:
        logger.error(f"Telegram connection error: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))

# Slack Integration
@api_router.post("/integrations/slack/connect")
async def connect_slack(
    request: SlackToken,
    current_user: User = Depends(get_current_user)
):
    try:
        import requests
        
        token = request.token
        if not token:
            raise HTTPException(status_code=400, detail="Token is required")
        
        # Validate token with Slack API
        headers = {'Authorization': f'Bearer {token}'}
        response = requests.get('https://slack.com/api/auth.test', headers=headers)
        
        if response.status_code != 200:
            raise HTTPException(status_code=400, detail="Invalid Slack token")
        
        bot_info = response.json()
        if not bot_info.get('ok'):
            raise HTTPException(status_code=400, detail=f"Slack API error: {bot_info.get('error', 'Unknown error')}")
        
        # Store integration in database
        integration = {
            'user_id': current_user.id,
            'service': 'slack',
            'token': token,
            'bot_id': bot_info.get('bot_id'),
            'user_id_slack': bot_info.get('user_id'),
            'team_id': bot_info.get('team_id'),
            'team_name': bot_info.get('team'),
            'created_at': datetime.now(timezone.utc).isoformat(),
            'status': 'connected'
        }
        
        await db.integrations.update_one(
            {'user_id': current_user.id, 'service': 'slack'},
            {'$set': integration},
            upsert=True
        )
        
        return {
            'success': True,
            'message': 'Slack connected successfully',
            'team_name': bot_info.get('team')
        }
    except Exception as e:
        logger.error(f"Slack connection error: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))

# Get User Integrations
@api_router.get("/integrations/user")
async def get_user_integrations(current_user: User = Depends(get_current_user)):
    integrations = await db.integrations.find(
        {'user_id': current_user.id},
        {'_id': 0, 'token': 0}  # Exclude sensitive data
    ).to_list(100)
    
    return {
        'integrations': integrations
    }

# Gmail OAuth Integration
@api_router.get("/integrations/gmail/authorize")
async def gmail_authorize(current_user: User = Depends(get_current_user)):
    """Initiate Gmail OAuth flow"""
    import urllib.parse
    
    client_id = os.environ.get('GOOGLE_CLIENT_ID')
    redirect_uri = os.environ.get('GOOGLE_REDIRECT_URI')
    
    if not client_id or not redirect_uri:
        raise HTTPException(status_code=400, detail="Google OAuth not configured")
    
    scope = 'https://www.googleapis.com/auth/gmail.send'
    auth_url = f"https://accounts.google.com/o/oauth2/v2/auth?client_id={client_id}&redirect_uri={redirect_uri}&response_type=code&scope={scope}&state={current_user.id}"
    
    return {'authorization_url': auth_url}

@api_router.post("/integrations/gmail/callback")
async def gmail_callback(
    code: str,
    state: str,
    current_user: User = Depends(get_current_user)
):
    """Handle Gmail OAuth callback"""
    try:
        import requests
        
        client_id = os.environ.get('GOOGLE_CLIENT_ID')
        client_secret = os.environ.get('GOOGLE_CLIENT_SECRET')
        redirect_uri = os.environ.get('GOOGLE_REDIRECT_URI')
        
        # Exchange code for tokens
        token_url = 'https://oauth2.googleapis.com/token'
        token_data = {
            'code': code,
            'client_id': client_id,
            'client_secret': client_secret,
            'redirect_uri': redirect_uri,
            'grant_type': 'authorization_code'
        }
        
        response = requests.post(token_url, data=token_data)
        if response.status_code != 200:
            raise HTTPException(status_code=400, detail="Failed to get access token")
        
        tokens = response.json()
        
        # Store integration in database
        integration = {
            'user_id': current_user.id,
            'service': 'gmail',
            'access_token': tokens.get('access_token'),
            'refresh_token': tokens.get('refresh_token'),
            'token_type': tokens.get('token_type'),
            'expires_in': tokens.get('expires_in'),
            'created_at': datetime.now(timezone.utc).isoformat(),
            'status': 'connected'
        }
        
        await db.integrations.update_one(
            {'user_id': current_user.id, 'service': 'gmail'},
            {'$set': integration},
            upsert=True
        )
        
        return {
            'success': True,
            'message': 'Gmail connected successfully'
        }
    except Exception as e:
        logger.error(f"Gmail OAuth error: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))

import requests

# @api_router.get("/telegram/poll")
# async def poll_telegram():

#     integration = await db.integrations.find_one({"service": "telegram"})
#     if not integration:
#         return {"message": "Telegram not connected"}

#     token = integration["token"]

#     response = requests.get(
#         f"https://api.telegram.org/bot{token}/getUpdates"
#     )

#     updates = response.json()["result"]

#     for update in updates:

#         if "message" not in update:
#             continue

#         chat_id = str(update["message"]["chat"]["id"])
#         text = update["message"].get("text", "")
#         name = update["message"]["from"]["first_name"]

#         conv = await db.conversations.find_one({
#             "customer_contact": chat_id
#         })

#         if not conv:

#             conv_id = str(uuid.uuid4())

#             conversation = {
#                 "id": conv_id,
#                 "customer_name": name,
#                 "customer_contact": chat_id,
#                 "channel": "telegram",
#                 "status": "open",
#                 "priority": "medium",
#                 "sentiment": "neutral",
#                 "intent": "general",
#                 "created_at": datetime.now(timezone.utc).isoformat(),
#                 "last_message_at": datetime.now(timezone.utc).isoformat(),
#                 "unread_count": 1
#             }

#             await db.conversations.insert_one(conversation)

#         else:
#             conv_id = conv["id"]

#         msg = {
#             "id": str(uuid.uuid4()),
#             "conversation_id": conv_id,
#             "sender_type": "customer",
#             "sender_name": name,
#             "content": text,
#             "channel": "telegram",
#             "timestamp": datetime.now(timezone.utc).isoformat()
#         }

#         await db.messages.insert_one(msg)

#     return {"updates_processed": len(updates)}

import requests

last_update_id = None

# @api_router.get("/telegram/poll")
# async def poll_telegram():

#     global last_update_id

#     integration = await db.integrations.find_one({"service": "telegram"})
#     if not integration:
#         return {"message": "Telegram not connected"}

#     token = integration["token"]

#     url = f"https://api.telegram.org/bot{token}/getUpdates"

#     if last_update_id:
#         url += f"?offset={last_update_id + 1}"

#     response = requests.get(url)
#     updates = response.json()["result"]

#     for update in updates:

#         last_update_id = update["update_id"]

#         if "message" not in update:
#             continue

#         chat_id = str(update["message"]["chat"]["id"])
#         text = update["message"].get("text", "")
#         name = update["message"]["from"]["first_name"]

#         conv = await db.conversations.find_one({
#             "customer_contact": chat_id
#         })

#         if not conv:

#             conv_id = str(uuid.uuid4())

#             conversation = {
#                 "id": conv_id,
#                 "customer_name": name,
#                 "customer_contact": chat_id,
#                 "channel": "telegram",
#                 "status": "open",
#                 "priority": "medium",
#                 "sentiment": "neutral",
#                 "intent": "general",
#                 "created_at": datetime.now(timezone.utc).isoformat(),
#                 "last_message_at": datetime.now(timezone.utc).isoformat(),
#                 "unread_count": 1
#             }

#             await db.conversations.insert_one(conversation)

#         else:
#             conv_id = conv["id"]

#         msg = {
#             "id": str(uuid.uuid4()),
#             "conversation_id": conv_id,
#             "sender_type": "customer",
#             "sender_name": name,
#             "content": text,
#             "channel": "telegram",
#             "timestamp": datetime.now(timezone.utc).isoformat()
#         }

#         await db.messages.insert_one(msg)

# # UPDATE CONVERSATION SO DASHBOARD REFRESHES
#         await db.conversations.update_one(
#             {"id": conv_id},
#             {
#                 "$set": {
#                     "last_message_at": datetime.now(timezone.utc).isoformat()
#                 },
#                 "$inc": {"unread_count": 1}
#             }
#         )
#     return {"updates_processed": len(updates)}

last_update_id = 0

@api_router.get("/telegram/poll")
async def poll_telegram():

    global last_update_id

    integration = await db.integrations.find_one({"service": "telegram"})
    if not integration:
        return {"message": "Telegram not connected"}

    token = integration["token"]

    url = f"https://api.telegram.org/bot{token}/getUpdates?limit=100&timeout=0&offset={last_update_id}"

    response = requests.get(url)
    data = response.json()

    if not data.get("ok"):
        return {"error": "Telegram API error"}

    updates = data["result"]

    processed = 0

    for update in updates:

        # advance offset immediately
        last_update_id = update["update_id"] + 1

        if "message" not in update:
            continue

        chat_id = str(update["message"]["chat"]["id"])
        text = update["message"].get("text", "")
        name = update["message"]["from"]["first_name"]

        conv = await db.conversations.find_one({"customer_contact": chat_id})

        if not conv:
            conv_id = str(uuid.uuid4())

            conversation = {
                "id": conv_id,
                "customer_name": name,
                "customer_contact": chat_id,
                "channel": "telegram",
                "status": "open",
                "priority": "medium",
                "sentiment": "neutral",
                "intent": "general",
                "created_at": datetime.now(timezone.utc).isoformat(),
                "last_message_at": datetime.now(timezone.utc).isoformat(),
                "unread_count": 1
            }

            await db.conversations.insert_one(conversation)

        else:
            conv_id = conv["id"]

        msg = {
            "id": str(uuid.uuid4()),
            "conversation_id": conv_id,
            "sender_type": "customer",
            "sender_name": name,
            "content": text,
            "channel": "telegram",
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

        await db.messages.insert_one(msg)

        await db.conversations.update_one(
            {"id": conv_id},
            {
                "$set": {"last_message_at": datetime.now(timezone.utc).isoformat()},
                "$inc": {"unread_count": 1}
            }
        )

        # Broadcast new message to all connected WebSocket clients
        await manager.broadcast({
            "type": "new_message",
            "conversation_id": conv_id,
            "message": msg,
            "timestamp": datetime.now(timezone.utc).isoformat()
        })

        # Process auto-reply for customer messages
        from services.auto_reply_service import auto_reply_service
        await auto_reply_service.process_auto_reply(
            conversation_id=conv_id,
            message_content=text,
            sender_type="customer",
            channel="telegram",
            customer_contact=chat_id
        )

        processed += 1

    return {"updates_processed": processed}

# ============================================================================
# WebSocket Endpoint
# ============================================================================
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """
    WebSocket endpoint for real-time message updates.
    Accepts connections and broadcasts new messages to all connected clients.
    """
    await manager.connect(websocket)
    try:
        while True:
            # Keep connection alive and listen for any incoming data
            data = await websocket.receive_text()
            # Optional: handle incoming messages if needed
            logger.debug(f"WebSocket received: {data}")
    except WebSocketDisconnect:
        manager.disconnect(websocket)
        logger.info("WebSocket client disconnected gracefully")
    except Exception as e:
        logger.error(f"WebSocket error: {str(e)}")
        manager.disconnect(websocket)

# INCLUDE ROUTER
app.include_router(api_router)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ============================================================================
# Background Telegram Polling Service
# ============================================================================
async def telegram_polling_service():
    """Background service to continuously poll Telegram messages."""
    while True:
        try:
            logger.info("Running Telegram polling service...")
            await poll_telegram()
            await asyncio.sleep(5)  # Poll every 5 seconds
        except Exception as e:
            logger.error(f"Telegram polling service error: {str(e)}")
            await asyncio.sleep(10)  # Wait longer on error

@app.on_event("startup")
async def start_background_services():
    """Start background services on application startup."""
    logger.info("Starting background services...")
    
    # Initialize auto-reply service with WebSocket manager
    from services.auto_reply_service import initialize_auto_reply_service
    initialize_auto_reply_service(manager)
    
    asyncio.create_task(telegram_polling_service())
    logger.info("Background services started")

@app.on_event("shutdown")
async def shutdown_db_client():
    if client:
        client.close()

if __name__ == "__main__":
    import uvicorn
    print("Starting Convo Sphere Backend...")
    uvicorn.run(app, host="127.0.0.1", port=8000, log_level="info")