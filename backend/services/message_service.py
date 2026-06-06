import logging
from typing import List, Optional, Dict, Any
from datetime import datetime, timezone
from utils.mongo_serializer import prepare_api_response, serialize_mongo_doc
from models import Message, MessageCreate, AIAnalysis

logger = logging.getLogger(__name__)

class MessageService:
    """
    Service for handling message operations with proper serialization.
    """
    
    def __init__(self, database):
        self.db = database
    
    async def create_message(
        self,
        conversation_id: str,
        content: str,
        sender_name: str,
        sender_type: str = "customer",
        channel: str = "email",
        metadata: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """
        Create a new message with proper serialization.
        """
        try:
            message = Message(
                conversation_id=conversation_id,
                sender_type=sender_type,
                sender_name=sender_name,
                content=content,
                channel=channel,
                metadata=metadata or {}
            )
            
            msg_doc = message.model_dump()
            msg_doc['timestamp'] = msg_doc['timestamp'].isoformat()
            
            await self.db.messages.insert_one(msg_doc)
            
            logger.info(f"Created message {message.id} for conversation {conversation_id}")
            return prepare_api_response(msg_doc)
            
        except Exception as e:
            logger.error(f"Error creating message: {str(e)}")
            raise
    
    async def get_conversation_messages(
        self,
        conversation_id: str,
        limit: int = 1000
    ) -> List[Dict[str, Any]]:
        """
        Get all messages for a conversation with proper serialization.
        """
        try:
            messages = await self.db.messages.find(
                {'conversation_id': conversation_id}, 
                {'_id': 0}
            ).sort('timestamp', 1).to_list(limit)
            
            return prepare_api_response(messages)
            
        except Exception as e:
            logger.error(f"Error fetching conversation messages: {str(e)}")
            raise
    
    async def analyze_and_create_message(
        self,
        conversation_id: str,
        content: str,
        sender_name: str,
        sender_type: str = "customer",
        channel: str = "email",
        metadata: Optional[Dict] = None,
        conversation_history: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Create message with AI analysis and handle auto-responses.
        """
        try:
            # Create the message
            message_data = await self.create_message(
                conversation_id=conversation_id,
                content=content,
                sender_name=sender_name,
                sender_type=sender_type,
                channel=channel,
                metadata=metadata
            )
            
            # If it's a customer message, analyze with AI
            if sender_type == "customer":
                from server import analyze_message_with_ai
                analysis = await analyze_message_with_ai(content, conversation_history)
                
                # Update conversation with AI analysis
                update_data = {
                    'last_message_at': datetime.now(timezone.utc).isoformat(),
                    'sentiment': analysis.sentiment,
                    'intent': analysis.intent,
                    'priority': analysis.priority,
                    'unread_count': 1  # Will be incremented at conversation level
                }
                
                await self.db.conversations.update_one(
                    {'id': conversation_id},
                    {'$set': update_data, '$inc': {'unread_count': 1}}
                )
                
                # Create auto-response if confidence is high
                if analysis.confidence > 0.8 and analysis.suggested_response:
                    auto_message = await self.create_message(
                        conversation_id=conversation_id,
                        content=analysis.suggested_response,
                        sender_name="AI Assistant",
                        sender_type="ai",
                        channel=channel,
                        metadata={
                            'auto_reply': True,
                            'confidence': analysis.confidence,
                            'original_message_id': message_data['id']
                        }
                    )
                    
                    return {
                        'message': message_data,
                        'analysis': prepare_api_response(analysis.model_dump()),
                        'auto_reply': auto_message
                    }
                
                return {
                    'message': message_data,
                    'analysis': prepare_api_response(analysis.model_dump()),
                    'auto_reply': None
                }
            
            return {'message': message_data}
            
        except Exception as e:
            logger.error(f"Error in analyze_and_create_message: {str(e)}")
            raise
    
    async def create_agent_response(
        self,
        conversation_id: str,
        content: str,
        agent_name: str,
        channel: str = "email"
    ) -> Dict[str, Any]:
        """
        Create an agent response and update conversation.
        """
        try:
            # Create agent response
            message_data = await self.create_message(
                conversation_id=conversation_id,
                content=content,
                sender_name=agent_name,
                sender_type="agent",
                channel=channel
            )
            
            # Update conversation
            await self.db.conversations.update_one(
                {'id': conversation_id},
                {'$set': {
                    'last_message_at': datetime.now(timezone.utc).isoformat(),
                    'unread_count': 0,
                    'status': 'waiting'
                }}
            )
            
            logger.info(f"Agent responded to conversation {conversation_id}")
            return message_data
            
        except Exception as e:
            logger.error(f"Error creating agent response: {str(e)}")
            raise

# Global message service instance will be created with database parameter

# Create a factory function to get message service instance
def get_message_service(database):
    """Get a message service instance with database connection."""
    return MessageService(database)
