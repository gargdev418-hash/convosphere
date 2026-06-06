import logging
from fastapi import APIRouter, HTTPException, Depends
from models import (
    User, Conversation, ConversationFilter, AgentResponse
)
from server import (
    get_current_user, db
)
from services.message_service import message_service
from websocket.manager import connection_manager
from utils.mongo_serializer import prepare_api_response
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

def setup_conversation_routes(api_router: APIRouter):
    """
    Setup conversation routes.
    """
    
    @api_router.post("/conversations", response_model=Conversation)
    async def create_conversation(
        customer_name: str, 
        customer_contact: str, 
        channel: str, 
        current_user: User = Depends(get_current_user)
    ):
        """Create a new conversation."""
        try:
            if db is None:
                raise HTTPException(status_code=503, detail="Database connection failed")
            
            conversation = Conversation(
                customer_name=customer_name,
                customer_contact=customer_contact,
                channel=channel
            )
            
            conv_doc = conversation.model_dump()
            conv_doc['last_message_at'] = conv_doc['last_message_at'].isoformat()
            conv_doc['created_at'] = conv_doc['created_at'].isoformat()
            
            await db.conversations.insert_one(conv_doc)
            
            logger.info(f"Created conversation for {customer_name}")
            return prepare_api_response(conversation)
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error creating conversation: {str(e)}")
            raise HTTPException(status_code=500, detail=f"Error creating conversation: {str(e)}")

    @api_router.post("/conversations/filter", response_model=list[Conversation])
    async def get_conversations(
        filters: ConversationFilter, 
        current_user: User = Depends(get_current_user)
    ):
        """Get conversations with optional filtering."""
        try:
            if db is None:
                raise HTTPException(status_code=503, detail="Database connection failed")
            
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
            
            conversations = await db.conversations.find(
                query, 
                {'_id': 0}
            ).sort('last_message_at', -1).to_list(100)
            
            # Convert datetime fields
            for conv in conversations:
                if isinstance(conv.get('last_message_at'), str):
                    conv['last_message_at'] = datetime.fromisoformat(conv['last_message_at'])
                if isinstance(conv.get('created_at'), str):
                    conv['created_at'] = datetime.fromisoformat(conv['created_at'])
            
            return prepare_api_response(conversations)
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error fetching conversations: {str(e)}")
            raise HTTPException(status_code=500, detail=f"Error fetching conversations: {str(e)}")

    @api_router.get("/conversations/{conversation_id}", response_model=Conversation)
    async def get_conversation(
        conversation_id: str, 
        current_user: User = Depends(get_current_user)
    ):
        """Get a specific conversation by ID."""
        try:
            if db is None:
                raise HTTPException(status_code=503, detail="Database connection failed")
            
            conv = await db.conversations.find_one(
                {'id': conversation_id}, 
                {'_id': 0}
            )
            
            if not conv:
                raise HTTPException(status_code=404, detail="Conversation not found")
            
            # Convert datetime fields
            if isinstance(conv.get('last_message_at'), str):
                conv['last_message_at'] = datetime.fromisoformat(conv['last_message_at'])
            if isinstance(conv.get('created_at'), str):
                conv['created_at'] = datetime.fromisoformat(conv['created_at'])
            
            return prepare_api_response(Conversation(**conv))
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error fetching conversation: {str(e)}")
            raise HTTPException(status_code=500, detail=f"Error fetching conversation: {str(e)}")

    @api_router.get("/conversations/{conversation_id}/messages")
    async def get_conversation_messages(
        conversation_id: str, 
        current_user: User = Depends(get_current_user)
    ):
        """Get all messages for a conversation."""
        try:
            if db is None:
                raise HTTPException(status_code=503, detail="Database connection failed")
            
            messages = await message_service.get_conversation_messages(conversation_id)
            
            # Convert datetime fields
            for msg in messages:
                if isinstance(msg.get('timestamp'), str):
                    msg['timestamp'] = datetime.fromisoformat(msg['timestamp'])
            
            return prepare_api_response(messages)
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error fetching conversation messages: {str(e)}")
            raise HTTPException(status_code=500, detail=f"Error fetching messages: {str(e)}")

    @api_router.post("/conversations/{conversation_id}/respond")
    async def agent_respond(
        conversation_id: str, 
        agent_response: AgentResponse, 
        current_user: User = Depends(get_current_user)
    ):
        """Respond to a conversation as an agent."""
        try:
            if db is None:
                raise HTTPException(status_code=503, detail="Database connection failed")
            
            # Fetch conversation to get channel info
            conv = await db.conversations.find_one({'id': conversation_id}, {'_id': 0})
            if not conv:
                raise HTTPException(status_code=404, detail="Conversation not found")

            # Create agent response
            message_data = await message_service.create_agent_response(
                conversation_id=conversation_id,
                content=agent_response.content,
                agent_name=current_user.name,
                channel=conv.get('channel', 'email')
            )
            
            # Send message based on channel (existing logic)
            await _send_message_by_channel(conv, agent_response.content, current_user)
            
            # Broadcast to WebSocket clients
            await connection_manager.broadcast({
                "type": "new_message",
                "conversation_id": conversation_id,
                "message": message_data,
                "timestamp": datetime.now(timezone.utc).isoformat()
            })
            
            logger.info(f"Agent responded to conversation {conversation_id}")
            return prepare_api_response({
                "success": True, 
                "message_id": message_data['id']
            })
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error responding to conversation: {str(e)}")
            raise HTTPException(status_code=500, detail=f"Error responding to conversation: {str(e)}")

    async def _send_message_by_channel(conversation: dict, content: str, current_user: User):
        """Send message through the appropriate channel."""
        try:
            import requests
            
            # TELEGRAM
            if conversation["channel"] == "telegram":
                integration = await db.integrations.find_one({
                    "user_id": current_user.id,
                    "service": "telegram"
                })

                if integration:
                    token = integration["token"]
                    chat_id = conversation["customer_contact"]

                    requests.post(
                        f"https://api.telegram.org/bot{token}/sendMessage",
                        json={
                            "chat_id": chat_id,
                            "text": content
                        }
                    )

            # SLACK
            elif conversation["channel"] == "slack":
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
                            "channel": conversation["customer_contact"],
                            "text": content
                        }
                    )
                    
        except Exception as e:
            logger.error(f"Message sending error: {str(e)}")

    logger.info("Conversation routes configured")
