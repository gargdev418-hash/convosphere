"""
Universal Auto-Reply Service for Convo Sphere
Handles automatic responses for all supported channels
"""

import logging
from typing import Optional
import os

logger = logging.getLogger(__name__)

# Configuration
AUTO_REPLY_ENABLED = os.environ.get('AUTO_REPLY_ENABLED', 'true').lower() == 'true'

class AutoReplyService:
    """Service for generating and sending automatic replies across all channels."""
    
    def __init__(self, websocket_manager=None):
        self.enabled = AUTO_REPLY_ENABLED
        self.websocket_manager = websocket_manager
        logger.info(f"AutoReplyService initialized - Enabled: {self.enabled}")
    
    def generate_auto_reply(self, message_text: str) -> Optional[str]:
        """
        Generate an automatic reply based on message content.
        
        Args:
            message_text: The incoming message text
            
        Returns:
            Generated reply text or None if no reply should be sent
        """
        if not self.enabled:
            logger.debug("Auto-reply is disabled")
            return None
        
        if not message_text:
            return None
        
        text = message_text.lower().strip()
        
        # Greeting patterns
        if any(greeting in text for greeting in ['hi', 'hello', 'hey', 'good morning', 'good afternoon', 'good evening']):
            return "Hello! How can I help you today?"
        
        # Help requests
        if any(help_word in text for help_word in ['help', 'support', 'assist', 'issue', 'problem']):
            return "Our support team will assist you shortly. Please describe your issue in detail."
        
        # Information requests
        if any(info_word in text for info_word in ['info', 'information', 'details', 'about', 'what is']):
            return "I'd be happy to provide information. Could you please specify what you'd like to know?"
        
        # Pricing/Cost inquiries
        if any(price_word in text for price_word in ['price', 'cost', 'pricing', 'how much', 'fee', 'charge']):
            return "For pricing information, please visit our website or contact our sales team at sales@convosphere.com"
        
        # Contact/Location inquiries
        if any(contact_word in text for contact_word in ['contact', 'location', 'address', 'where', 'phone']):
            return "You can reach us at support@convosphere.com or call us at 1-800-CONVO-SPHERE"
        
        # Thank you responses
        if any(thanks_word in text for thanks_word in ['thank', 'thanks', 'appreciate', 'great', 'awesome']):
            return "You're welcome! We're here to help. Is there anything else you need?"
        
        # Goodbye patterns
        if any(goodbye_word in text for goodbye_word in ['bye', 'goodbye', 'see you', 'later', 'farewell']):
            return "Thank you for contacting us! Have a great day!"
        
        # Default response for unrecognized messages
        return "Thank you for contacting Convo Sphere. Our team will review your message and respond shortly."
    
    async def process_auto_reply(self, conversation_id: str, message_content: str, 
                                 sender_type: str, channel: str, customer_contact: str) -> bool:
        """
        Process auto-reply for an incoming message.
        
        Args:
            conversation_id: ID of the conversation
            message_content: Content of the incoming message
            sender_type: Type of sender ('customer', 'agent', 'ai')
            channel: Communication channel
            customer_contact: Customer contact information
            
        Returns:
            True if auto-reply was sent, False otherwise
        """
        try:
            # Only auto-reply to customer messages
            if sender_type != 'customer':
                logger.debug(f"Skipping auto-reply for non-customer message: {sender_type}")
                return False
            
            # Generate auto-reply
            reply_text = self.generate_auto_reply(message_content)
            if not reply_text:
                logger.debug("No auto-reply generated")
                return False
            
            logger.info(f"Generated auto-reply for conversation {conversation_id}: {reply_text[:50]}...")
            
            # Create auto-reply message document for database
            from datetime import datetime, timezone
            import uuid
            
            auto_reply_msg = {
                "id": str(uuid.uuid4()),
                "conversation_id": conversation_id,
                "sender_type": "ai",
                "sender_name": "Auto Bot",
                "content": reply_text,
                "channel": channel,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
            
            # Save auto-reply message in MongoDB
            try:
                from motor.motor_asyncio import AsyncIOMotorClient
                import os
                
                client = AsyncIOMotorClient(os.environ.get('MONGO_URL', 'mongodb://localhost:27017'))
                db = client[os.environ.get('DB_NAME', 'convo_sphere')]
                
                await db.messages.insert_one(auto_reply_msg)
                logger.info(f"Auto-reply message saved to MongoDB: {auto_reply_msg['id']}")
                
                # Update conversation with new message timestamp
                await db.conversations.update_one(
                    {"id": conversation_id},
                    {
                        "$set": {"last_message_at": auto_reply_msg['timestamp']},
                        "$inc": {"unread_count": 0}  # Don't increment unread for auto-replies
                    }
                )
                
                # Broadcast auto-reply to dashboard via WebSocket
                if self.websocket_manager:
                    try:
                        await self.websocket_manager.broadcast({
                            "type": "new_message",
                            "conversation_id": conversation_id,
                            "message": auto_reply_msg,
                            "timestamp": auto_reply_msg['timestamp']
                        })
                        logger.info(f"Auto-reply broadcasted to dashboard")
                    except Exception as e:
                        logger.error(f"Failed to broadcast auto-reply: {str(e)}")
                else:
                    logger.warning("WebSocket manager not available - auto-reply not broadcasted")
                
                client.close()
                
            except Exception as e:
                logger.error(f"Failed to save auto-reply to database: {str(e)}")
            
            # Send reply through appropriate channel
            success = await self._send_reply_via_channel(channel, customer_contact, reply_text)
            
            if success:
                logger.info(f"Auto-reply sent successfully via {channel}")
                return True
            else:
                logger.error(f"Failed to send auto-reply via {channel}")
                return False
                
        except Exception as e:
            logger.error(f"Error processing auto-reply: {str(e)}")
            return False
    
    async def _send_reply_via_channel(self, channel: str, contact: str, message: str) -> bool:
        """
        Send reply through the appropriate channel.
        
        Args:
            channel: Communication channel
            contact: Customer contact information
            message: Message to send
            
        Returns:
            True if successful, False otherwise
        """
        try:
            if channel == 'telegram':
                return await self._send_telegram_reply(contact, message)
            elif channel == 'whatsapp':
                return await self._send_whatsapp_reply(contact, message)
            elif channel == 'email':
                return await self._send_email_reply(contact, message)
            elif channel == 'slack':
                return await self._send_slack_reply(contact, message)
            else:
                logger.warning(f"Unsupported channel for auto-reply: {channel}")
                return False
                
        except Exception as e:
            logger.error(f"Error sending reply via {channel}: {str(e)}")
            return False
    
    async def _send_telegram_reply(self, chat_id: str, message: str) -> bool:
        """Send reply via Telegram."""
        try:
            import requests
            
            # Get Telegram integration from database
            from motor.motor_asyncio import AsyncIOMotorClient
            import os
            
            client = AsyncIOMotorClient(os.environ.get('MONGO_URL', 'mongodb://localhost:27017'))
            db = client[os.environ.get('DB_NAME', 'convo_sphere')]
            
            integration = await db.integrations.find_one({'service': 'telegram'})
            if not integration:
                logger.error("Telegram integration not found")
                return False
            
            token = integration['token']
            url = f"https://api.telegram.org/bot{token}/sendMessage"
            
            payload = {
                "chat_id": chat_id,
                "text": message
            }
            
            response = requests.post(url, json=payload)
            
            if response.status_code == 200:
                data = response.json()
                if data.get('ok'):
                    logger.info(f"Telegram auto-reply sent to chat_id: {chat_id}")
                    return True
                else:
                    logger.error(f"Telegram API error: {data}")
                    return False
            else:
                logger.error(f"Telegram HTTP error: {response.status_code}")
                return False
                
        except Exception as e:
            logger.error(f"Error sending Telegram reply: {str(e)}")
            return False
    
    async def _send_whatsapp_reply(self, contact: str, message: str) -> bool:
        """Send reply via WhatsApp."""
        try:
            import requests
            
            # Get WhatsApp integration from database
            from motor.motor_asyncio import AsyncIOMotorClient
            import os
            
            client = AsyncIOMotorClient(os.environ.get('MONGO_URL', 'mongodb://localhost:27017'))
            db = client[os.environ.get('DB_NAME', 'convo_sphere')]
            
            integration = await db.integrations.find_one({'service': 'whatsapp'})
            if not integration:
                logger.error("WhatsApp integration not found")
                return False
            
            access_token = integration['access_token']
            phone_number_id = integration['phone_number_id']
            
            url = f"https://graph.facebook.com/v18.0/{phone_number_id}/messages"
            
            headers = {
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json"
            }
            
            payload = {
                "messaging_product": "whatsapp",
                "to": contact,
                "text": {
                    "body": message
                }
            }
            
            response = requests.post(url, headers=headers, json=payload)
            
            if response.status_code == 200:
                data = response.json()
                if data.get('error') is None:
                    logger.info(f"WhatsApp auto-reply sent to: {contact}")
                    return True
                else:
                    logger.error(f"WhatsApp API error: {data}")
                    return False
            else:
                logger.error(f"WhatsApp HTTP error: {response.status_code}")
                return False
                
        except Exception as e:
            logger.error(f"Error sending WhatsApp reply: {str(e)}")
            return False
    
    async def _send_email_reply(self, email: str, message: str) -> bool:
        """Send reply via Email."""
        try:
            # This would integrate with Gmail service or SMTP
            # For now, log the action
            logger.info(f"Email auto-reply would be sent to: {email}")
            logger.info(f"Email content: {message}")
            # TODO: Implement actual email sending
            return True
            
        except Exception as e:
            logger.error(f"Error sending email reply: {str(e)}")
            return False
    
    async def _send_slack_reply(self, contact: str, message: str) -> bool:
        """Send reply via Slack."""
        try:
            import requests
            
            # Get Slack integration from database
            from motor.motor_asyncio import AsyncIOMotorClient
            import os
            
            client = AsyncIOMotorClient(os.environ.get('MONGO_URL', 'mongodb://localhost:27017'))
            db = client[os.environ.get('DB_NAME', 'convo_sphere')]
            
            integration = await db.integrations.find_one({'service': 'slack'})
            if not integration:
                logger.error("Slack integration not found")
                return False
            
            token = integration['token']
            
            url = "https://slack.com/api/chat.postMessage"
            
            headers = {
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json"
            }
            
            payload = {
                "channel": contact,
                "text": message
            }
            
            response = requests.post(url, headers=headers, json=payload)
            
            if response.status_code == 200:
                data = response.json()
                if data.get('ok'):
                    logger.info(f"Slack auto-reply sent to channel: {contact}")
                    return True
                else:
                    logger.error(f"Slack API error: {data}")
                    return False
            else:
                logger.error(f"Slack HTTP error: {response.status_code}")
                return False
                
        except Exception as e:
            logger.error(f"Error sending Slack reply: {str(e)}")
            return False

# Create singleton instance (will be initialized with manager later)
auto_reply_service = AutoReplyService()

def initialize_auto_reply_service(websocket_manager):
    """Initialize the auto-reply service with WebSocket manager."""
    global auto_reply_service
    auto_reply_service = AutoReplyService(websocket_manager)
    logger.info("AutoReplyService initialized with WebSocket manager")
