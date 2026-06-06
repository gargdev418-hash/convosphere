import logging
import os
import uuid
from fastapi import APIRouter, HTTPException, Depends, Response
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from models import User
from server import get_current_user, db
from utils.mongo_serializer import prepare_api_response
from datetime import datetime, timezone
import requests

logger = logging.getLogger(__name__)

def setup_integration_routes(api_router: APIRouter):
    """
    Setup integration routes for external services.
    """
    
    @api_router.get("/integrations/user")
    async def get_user_integrations(current_user: User = Depends(get_current_user)):
        """Get all integrations for the current user."""
        try:
            if db is None:
                raise HTTPException(status_code=503, detail="Database connection failed")
            
            integrations = await db.integrations.find(
                {'user_id': current_user.id},
                {'_id': 0, 'token': 0}  # Exclude sensitive data
            ).to_list(100)
            
            return prepare_api_response({
                'integrations': integrations
            })
            
        except Exception as e:
            logger.error(f"Error fetching integrations: {str(e)}")
            raise HTTPException(status_code=500, detail=f"Error fetching integrations: {str(e)}")

    # Telegram Integration
    @api_router.post("/integrations/telegram/connect")
    async def connect_telegram(
        request: dict,
        current_user: User = Depends(get_current_user)
    ):
        """Connect Telegram bot integration."""
        try:
            token = request.get('token')
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
            
            # Store integration
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
            
            logger.info(f"Telegram connected for user {current_user.email}")
            return prepare_api_response({
                'success': True,
                'message': 'Telegram connected successfully',
                'bot_username': bot_info['result']['username']
            })
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Telegram connection error: {str(e)}")
            raise HTTPException(status_code=400, detail=str(e))

    # Slack Integration
    @api_router.post("/integrations/slack/connect")
    async def connect_slack(
        request: dict,
        current_user: User = Depends(get_current_user)
    ):
        """Connect Slack integration."""
        try:
            token = request.get('token')
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
            
            # Store integration
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
            
            logger.info(f"Slack connected for user {current_user.email}")
            return prepare_api_response({
                'success': True,
                'message': 'Slack connected successfully',
                'team_name': bot_info.get('team')
            })
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Slack connection error: {str(e)}")
            raise HTTPException(status_code=400, detail=str(e))

    # Gmail Integration
    @api_router.get("/integrations/gmail/authorize")
    async def gmail_authorize(current_user: User = Depends(get_current_user)):
        """Initiate Gmail OAuth flow."""
        try:
            import urllib.parse
            
            client_id = os.environ.get('GOOGLE_CLIENT_ID')
            redirect_uri = os.environ.get('GOOGLE_REDIRECT_URI')
            
            if not client_id or not redirect_uri:
                raise HTTPException(status_code=400, detail="Google OAuth not configured")
            
            scope = 'https://www.googleapis.com/auth/gmail.send'
            auth_url = f"https://accounts.google.com/o/oauth2/v2/auth?client_id={client_id}&redirect_uri={redirect_uri}&response_type=code&scope={scope}&state={current_user.id}"
            
            return prepare_api_response({'authorization_url': auth_url})
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Gmail authorization error: {str(e)}")
            raise HTTPException(status_code=400, detail=str(e))

    @api_router.post("/integrations/gmail/callback")
    async def gmail_callback(
        request: dict,
        current_user: User = Depends(get_current_user)
    ):
        """Handle Gmail OAuth callback."""
        try:
            code = request.get('code')
            state = request.get('state')
            
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
            
            # Store integration
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
            
            # Trigger initial email sync
            from services.gmail_service import gmail_service
            await _sync_gmail_emails(current_user.id)
            
            logger.info(f"Gmail connected for user {current_user.email}")
            return prepare_api_response({
                'success': True,
                'message': 'Gmail connected successfully'
            })
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Gmail OAuth error: {str(e)}")
            raise HTTPException(status_code=400, detail=str(e))

    @api_router.post("/gmail/sync")
    async def sync_gmail_emails(current_user: User = Depends(get_current_user)):
        """Manually trigger Gmail email sync."""
        try:
            from services.gmail_service import gmail_service
            emails_synced = await _sync_gmail_emails(current_user.id)
            
            return prepare_api_response({
                'success': True,
                'message': f'Synced {emails_synced} emails',
                'emails_count': emails_synced
            })
            
        except Exception as e:
            logger.error(f"Gmail sync error: {str(e)}")
            raise HTTPException(status_code=500, detail=f"Email sync failed: {str(e)}")

    # WhatsApp Integration
    @api_router.post("/integrations/whatsapp/connect")
    async def connect_whatsapp(
        request: dict,
        current_user: User = Depends(get_current_user)
    ):
        """Connect WhatsApp Business API integration."""
        try:
            access_token = request.get('access_token')
            phone_number_id = request.get('phone_number_id')
            webhook_url = request.get('webhook_url')
            
            if not all([access_token, phone_number_id, webhook_url]):
                raise HTTPException(status_code=400, detail="All fields are required")
            
            # Verify the access token
            test_url = f"https://graph.facebook.com/v18.0/me"
            headers = {'Authorization': f'Bearer {access_token}'}
            
            response = requests.get(test_url, headers=headers)
            if response.status_code != 200:
                raise HTTPException(status_code=400, detail="Invalid WhatsApp access token")
            
            # Store integration
            integration = {
                'user_id': current_user.id,
                'service': 'whatsapp',
                'access_token': access_token,
                'phone_number_id': phone_number_id,
                'webhook_url': webhook_url,
                'created_at': datetime.now(timezone.utc).isoformat(),
                'status': 'connected'
            }
            
            await db.integrations.update_one(
                {'user_id': current_user.id, 'service': 'whatsapp'},
                {'$set': integration},
                upsert=True
            )
            
            logger.info(f"WhatsApp connected for user {current_user.email}")
            return prepare_api_response({
                'success': True,
                'message': 'WhatsApp connected successfully'
            })
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"WhatsApp connection error: {str(e)}")
            raise HTTPException(status_code=400, detail=str(e))

    async def _sync_gmail_emails(user_id: str) -> int:
        """Sync emails from Gmail to conversations."""
        try:
            from services.gmail_service import gmail_service
            from services.ai_service import ai_service
            from websocket.manager import connection_manager
            
            # Fetch emails from Gmail
            emails = await gmail_service.fetch_emails(user_id, db, max_results=20)
            processed_count = 0
            
            for email_data in emails:
                # Check if email already processed
                existing_message = await db.messages.find_one({
                    'metadata.gmail_message_id': email_data['id']
                })
                
                if existing_message:
                    continue
                
                # Find or create conversation
                conv = await db.conversations.find_one({
                    'customer_contact': email_data['from_email'],
                    'channel': 'email'
                })
                
                if not conv:
                    # Create new conversation
                    conv_id = str(uuid.uuid4())
                    
                    # Analyze email content with AI
                    email_content = f"{email_data['subject']}\n\n{email_data['body']}"
                    analysis = await ai_service.analyze_message(email_content)
                    
                    conversation = {
                        'id': conv_id,
                        'customer_name': email_data['from_name'],
                        'customer_contact': email_data['from_email'],
                        'channel': 'email',
                        'status': 'open',
                        'priority': analysis.priority,
                        'sentiment': analysis.sentiment,
                        'intent': analysis.intent,
                        'created_at': datetime.now(timezone.utc).isoformat(),
                        'last_message_at': datetime.now(timezone.utc).isoformat(),
                        'unread_count': 1
                    }
                    
                    await db.conversations.insert_one(conversation)
                else:
                    conv_id = conv['id']
                    
                    # Update existing conversation
                    email_content = f"{email_data['subject']}\n\n{email_data['body']}"
                    analysis = await ai_service.analyze_message(email_content)
                    
                    await db.conversations.update_one(
                        {'id': conv_id},
                        {
                            '$set': {
                                'last_message_at': datetime.now(timezone.utc).isoformat(),
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
                    'sender_name': email_data['from_name'],
                    'content': f"Subject: {email_data['subject']}\n\n{email_data['body']}",
                    'channel': 'email',
                    'timestamp': datetime.now(timezone.utc).isoformat(),
                    'metadata': {
                        'gmail_message_id': email_data['id'],
                        'gmail_thread_id': email_data.get('thread_id'),
                        'subject': email_data['subject'],
                        'from_email': email_data['from_email'],
                        'to_email': email_data['to_email']
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
                
                # Process auto-reply for customer messages
                from services.auto_reply_service import auto_reply_service
                await auto_reply_service.process_auto_reply(
                    conversation_id=conv_id,
                    message_content=f"Subject: {email_data['subject']}\n\n{email_data['body']}",
                    sender_type="customer",
                    channel="email",
                    customer_contact=email_data['from_email']
                )
                
                # Mark email as read in Gmail
                await gmail_service.mark_email_read(user_id, db, email_data['id'])
                
                # If high confidence AI response, send auto-reply
                if analysis.confidence > 0.8 and analysis.suggested_response:
                    await gmail_service.send_email(
                        user_id, 
                        db, 
                        email_data['from_email'],
                        f"Re: {email_data['subject']}",
                        analysis.suggested_response
                    )
                    
                    # Add AI response to conversation
                    ai_msg = {
                        'id': str(uuid.uuid4()),
                        'conversation_id': conv_id,
                        'sender_type': 'ai',
                        'sender_name': 'AI Assistant',
                        'content': analysis.suggested_response,
                        'channel': 'email',
                        'timestamp': datetime.now(timezone.utc).isoformat(),
                        'metadata': {
                            'auto_reply': True,
                            'confidence': analysis.confidence,
                            'subject': f"Re: {email_data['subject']}"
                        }
                    }
                    
                    await db.messages.insert_one(ai_msg)
                    
                    # Broadcast AI response
                    await connection_manager.broadcast({
                        "type": "new_message",
                        "conversation_id": conv_id,
                        "message": prepare_api_response(ai_msg),
                        "timestamp": datetime.now(timezone.utc).isoformat()
                    })
                
                processed_count += 1
            
            logger.info(f"Synced {processed_count} Gmail emails for user {user_id}")
            return processed_count
            
        except Exception as e:
            logger.error(f"Error syncing Gmail emails: {str(e)}")
            return 0

    logger.info("Integration routes configured")
