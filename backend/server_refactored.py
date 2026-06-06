from fastapi import FastAPI, APIRouter
from fastapi.security import HTTPBearer
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import logging
from pathlib import Path
from pydantic import BaseModel, Field, ConfigDict, EmailStr
from typing import List, Optional, Literal
import uuid
from datetime import datetime, timezone, timedelta
import jwt
import bcrypt

# Import new modules
from services.ai_service import ai_service
from services.gmail_service import gmail_service
from services.message_service import get_message_service
from websocket.manager import connection_manager
from utils.mongo_serializer import prepare_api_response, prepare_websocket_message
from websocket.websocket_routes import setup_websocket_routes
from routes.auth import setup_auth_routes
from routes.conversations import setup_conversation_routes
from routes.integrations import setup_integration_routes
from models import *

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

# MongoDB Connection
mongo_url = os.environ.get('MONGO_URL', 'mongodb://localhost:27017')
try:
    client = AsyncIOMotorClient(mongo_url, serverSelectionTimeoutMS=1000)
    db = client[os.environ.get('DB_NAME', 'test_database')]
except Exception as e:
    print(f"Warning: MongoDB connection failed - {e}")
    client = None
    db = None

# FastAPI App Setup
app = FastAPI()
api_router = APIRouter(prefix="/api")

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get('CORS_ORIGINS', '*').split(','),
    allow_methods=["*"],
    allow_headers=["*"],
)

# Configuration
JWT_SECRET = os.environ.get('JWT_SECRET', 'convo-sphere-secret-key-2025')
JWT_ALGORITHM = os.environ.get('JWT_ALGORITHM', 'HS256')

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Security
security = HTTPBearer(auto_error=False)

# Models are now imported from models.py for better organization

# Helper Functions (keeping existing for backward compatibility)
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

# AI Analysis Function (keeping for backward compatibility)
async def analyze_message_with_ai(content: str, conversation_history: List[str] = None) -> AIAnalysis:
    """Analyze message using AI service"""
    try:
        from services.ai_service import ai_service
        return await ai_service.analyze_message(content, conversation_history)
    except Exception as e:
        logger.error(f"AI analysis error: {str(e)}")
        # Fallback analysis
        return AIAnalysis(
            intent="general",
            sentiment="neutral",
            priority="medium",
            is_spam=False,
            confidence=0.5,
            suggested_response="Thank you for reaching out. An agent will assist you shortly."
        )

# Message Ingestion (enhanced with proper serialization)
@api_router.post("/messages/ingest", response_model=Message)
async def ingest_message(msg_data: MessageCreate, current_user: User = Depends(get_current_user)):
    """Ingest a new message with AI analysis and WebSocket broadcast."""
    if db is None:
        raise HTTPException(status_code=503, detail="Database connection failed")
    
    try:
        # Get conversation for context
        conv = await db.conversations.find_one({'id': msg_data.conversation_id}, {'_id': 0})
        if not conv:
            raise HTTPException(status_code=404, detail="Conversation not found")
        
        # Initialize message service with database
        msg_service = get_message_service(db)
        
        # Create message with AI analysis
        result = await msg_service.analyze_and_create_message(
            conversation_id=msg_data.conversation_id,
            content=msg_data.content,
            sender_name=msg_data.sender_name,
            sender_type=msg_data.sender_type,
            channel=msg_data.channel
        )
        
        # Broadcast new message to all connected WebSocket clients
        await connection_manager.broadcast({
            "type": "new_message",
            "conversation_id": msg_data.conversation_id,
            "message": result['message'],
            "timestamp": datetime.now(timezone.utc).isoformat()
        })
        
        return prepare_api_response(Message(**result['message']))
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error ingesting message: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error ingesting message: {str(e)}")

# Stats endpoint
@api_router.get("/stats")
async def get_stats():
    """Get dashboard statistics."""
    try:
        if db is None:
            logger.error("Database not connected for stats")
            raise HTTPException(status_code=503, detail="Database connection failed")
        
        total_conversations = await db.conversations.count_documents({})
        open_conversations = await db.conversations.count_documents({'status': 'open'})
        total_messages = await db.messages.count_documents({})
        
        pipeline = [
            {'$group': {'_id': None, 'total_unread': {'$sum': '$unread_count'}}}
        ]
        unread_result = await db.conversations.aggregate(pipeline).to_list(1)
        total_unread = unread_result[0]['total_unread'] if unread_result else 0
        
        logger.info(f"Stats retrieved: {total_conversations} conversations")
        return prepare_api_response({
            'total_conversations': total_conversations,
            'open_conversations': open_conversations,
            'total_messages': total_messages,
            'unread_messages': total_unread
        })
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching stats: {type(e).__name__}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error fetching stats: {str(e)}")

# WhatsApp Webhook (enhanced with proper error handling)
@api_router.post("/whatsapp/webhook")
async def whatsapp_webhook(webhook_data: dict):
    """Handle WhatsApp Business API webhook messages."""
    try:
        from services.message_service import message_service
        from websocket.manager import connection_manager
        
        logger.info(f"WhatsApp webhook received: {webhook_data}")
        
        # Verify this is a WhatsApp message
        if webhook_data.get('object') != 'whatsapp_business_account':
            return {"status": "ignored", "reason": "Not a WhatsApp Business message"}
        
        entries = webhook_data.get('entry', [])
        processed_messages = 0
        
        for entry in entries:
            changes = entry.get('changes', [])
            for change in changes:
                if change.get('field') == 'messages':
                    messages = change.get('value', {}).get('messages', [])
                    
                    for message in messages:
                        if message.get('type') == 'text':
                            # Process WhatsApp message
                            from_number = message.get('from')
                            text_content = message.get('text', {}).get('body', '')
                            message_id = message.get('id')
                            timestamp = int(message.get('timestamp', 0))
                            
                            # Extract customer info
                            contact_info = change.get('value', {}).get('contacts', [{}])[0]
                            customer_name = contact_info.get('profile', {}).get('name', from_number)
                            
                            # Find or create conversation
                            conv = await db.conversations.find_one({
                                'customer_contact': from_number,
                                'channel': 'whatsapp'
                            })
                            
                            if not conv:
                                # Create new conversation
                                conv_id = str(uuid.uuid4())
                                analysis = await analyze_message_with_ai(text_content)
                                
                                conversation = {
                                    'id': conv_id,
                                    'customer_name': customer_name,
                                    'customer_contact': from_number,
                                    'channel': 'whatsapp',
                                    'status': 'open',
                                    'priority': analysis.priority,
                                    'sentiment': analysis.sentiment,
                                    'intent': analysis.intent,
                                    'created_at': datetime.now(timezone.utc).isoformat(),
                                    'last_message_at': datetime.fromtimestamp(timestamp, timezone.utc).isoformat(),
                                    'unread_count': 1
                                }
                                
                                await db.conversations.insert_one(conversation)
                            else:
                                conv_id = conv['id']
                                
                                # Update existing conversation
                                analysis = await analyze_message_with_ai(text_content)
                                await db.conversations.update_one(
                                    {'id': conv_id},
                                    {
                                        '$set': {
                                            'last_message_at': datetime.fromtimestamp(timestamp, timezone.utc).isoformat(),
                                            'priority': analysis.priority,
                                            'sentiment': analysis.sentiment,
                                            'intent': analysis.intent
                                        },
                                        '$inc': {'unread_count': 1}
                                    }
                                )
                            
                            # Create message record
                            msg = {
                                'id': str(uuid.uuid4()),
                                'conversation_id': conv_id,
                                'sender_type': 'customer',
                                'sender_name': customer_name,
                                'content': text_content,
                                'channel': 'whatsapp',
                                'timestamp': datetime.fromtimestamp(timestamp, timezone.utc).isoformat(),
                                'metadata': {
                                    'whatsapp_message_id': message_id,
                                    'from_number': from_number
                                }
                            }
                            
                            await db.messages.insert_one(msg)
                            
                            # Broadcast new message to WebSocket clients
                            await connection_manager.broadcast({
                                "type": "new_message",
                                "conversation_id": conv_id,
                                "message": prepare_api_response(msg),
                                "timestamp": datetime.now(timezone.utc).isoformat()
                            })
                            
                            processed_messages += 1
        
        logger.info(f"Processed {processed_messages} WhatsApp messages")
        return prepare_api_response({"status": "success", "processed": processed_messages})
        
    except Exception as e:
        logger.error(f"WhatsApp webhook error: {str(e)}")
        return {"status": "error", "message": str(e)}

# WhatsApp Webhook Verification
@api_router.get("/whatsapp/webhook")
async def whatsapp_webhook_verify(
    hub_mode: str = None,
    hub_challenge: str = None,
    hub_verify_token: str = None
):
    """Verify WhatsApp webhook endpoint."""
    try:
        verify_token = os.environ.get('WHATSAPP_VERIFY_TOKEN', 'convo-sphere-verify-token')
        
        if hub_mode == 'subscribe' and hub_verify_token == verify_token:
            logger.info("WhatsApp webhook verified successfully")
            return Response(content=hub_challenge, status_code=200)
        else:
            logger.warning(f"WhatsApp webhook verification failed: {hub_verify_token}")
            return {"status": "error", "message": "Verification failed"}
            
    except Exception as e:
        logger.error(f"WhatsApp webhook verification error: {str(e)}")
        return {"status": "error", "message": str(e)}

# Telegram Polling (enhanced with proper error handling)
@api_router.get("/telegram/poll")
async def poll_telegram():
    """Poll for new Telegram messages."""
    try:
        from services.message_service import message_service
        from websocket.manager import connection_manager
        
        global last_update_id
        if 'last_update_id' not in globals():
            last_update_id = 0

        integration = await db.integrations.find_one({"service": "telegram"})
        if not integration:
            return prepare_api_response({"message": "Telegram not connected"})

        token = integration["token"]
        url = f"https://api.telegram.org/bot{token}/getUpdates?limit=100&timeout=0&offset={last_update_id}"

        response = requests.get(url)
        data = response.json()

        if not data.get("ok"):
            return prepare_api_response({"error": "Telegram API error"})

        updates = data["result"]
        processed = 0

        for update in updates:
            # Advance offset immediately
            last_update_id = update["update_id"] + 1

            if "message" not in update:
                continue

            chat_id = str(update["message"]["chat"]["id"])
            text = update["message"].get("text", "")
            name = update["message"]["from"]["first_name"]

            conv = await db.conversations.find_one({"customer_contact": chat_id})

            if not conv:
                conv_id = str(uuid.uuid4())
                analysis = await analyze_message_with_ai(text)

                conversation = {
                    "id": conv_id,
                    "customer_name": name,
                    "customer_contact": chat_id,
                    "channel": "telegram",
                    "status": "open",
                    "priority": analysis.priority,
                    "sentiment": analysis.sentiment,
                    "intent": analysis.intent,
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

            # Broadcast new message
            await connection_manager.broadcast({
                "type": "new_message",
                "conversation_id": conv_id,
                "message": prepare_api_response(msg),
                "timestamp": datetime.now(timezone.utc).isoformat()
            })

            # Update conversation
            await db.conversations.update_one(
                {"id": conv_id},
                {
                    "$set": {"last_message_at": datetime.now(timezone.utc).isoformat()},
                    "$inc": {"unread_count": 1}
                }
            )

            processed += 1

        return prepare_api_response({"updates_processed": processed})
        
    except Exception as e:
        logger.error(f"Telegram polling error: {str(e)}")
        return prepare_api_response({"error": str(e)})

# Setup all routes
def setup_routes():
    """Setup all API routes."""
    setup_auth_routes(api_router)
    setup_conversation_routes(api_router)
    setup_integration_routes(api_router)
    setup_websocket_routes(app)
    
    # Include router
    app.include_router(api_router)
    
    logger.info("All routes configured successfully")

# Health check
@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return prepare_api_response({
        "status": "healthy",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "database": "connected" if db else "disconnected"
    })

# Setup routes on startup
setup_routes()

# Shutdown handler
@app.on_event("shutdown")
async def shutdown_db_client():
    if client:
        client.close()
        logger.info("Database connection closed")

if __name__ == "__main__":
    import uvicorn
    print("Starting Convo Sphere Backend (Refactored)...")
    uvicorn.run(app, host="127.0.0.1", port=8000, log_level="info")
