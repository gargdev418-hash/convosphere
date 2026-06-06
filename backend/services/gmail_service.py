import os
import logging
import base64
import email
from email.header import decode_header
from typing import List, Dict, Optional
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
import requests
from datetime import datetime, timezone, timedelta

logger = logging.getLogger(__name__)

class GmailService:
    def __init__(self):
        self.scopes = ['https://www.googleapis.com/auth/gmail.readonly', 'https://www.googleapis.com/auth/gmail.send']
        self.client_id = os.environ.get('GOOGLE_CLIENT_ID')
        self.client_secret = os.environ.get('GOOGLE_CLIENT_SECRET')
        self.redirect_uri = os.environ.get('GOOGLE_REDIRECT_URI')
    
    async def get_credentials(self, user_id: str, db) -> Optional[Credentials]:
        """Get stored Gmail credentials for user"""
        try:
            integration = await db.integrations.find_one({
                'user_id': user_id,
                'service': 'gmail'
            })
            
            if not integration:
                return None
            
            token_data = {
                'token': integration.get('access_token'),
                'refresh_token': integration.get('refresh_token'),
                'token_uri': 'https://oauth2.googleapis.com/token',
                'client_id': self.client_id,
                'client_secret': self.client_secret,
                'scopes': self.scopes
            }
            
            credentials = Credentials(**token_data)
            
            # Refresh if expired
            if credentials.expired and credentials.refresh_token:
                credentials.refresh(Request())
                
                # Update stored credentials
                await db.integrations.update_one(
                    {'user_id': user_id, 'service': 'gmail'},
                    {'$set': {
                        'access_token': credentials.token,
                        'updated_at': datetime.now(timezone.utc).isoformat()
                    }}
                )
            
            return credentials
            
        except Exception as e:
            logger.error(f"Error getting Gmail credentials: {str(e)}")
            return None
    
    async def fetch_emails(self, user_id: str, db, max_results: int = 10) -> List[Dict]:
        """Fetch recent emails from Gmail"""
        try:
            credentials = await self.get_credentials(user_id, db)
            if not credentials:
                logger.warning(f"No Gmail credentials found for user {user_id}")
                return []
            
            service = build('gmail', 'v1', credentials=credentials)
            
            # Get messages from inbox
            results = service.users().messages().list(
                userId='me',
                labelIds=['INBOX'],
                maxResults=max_results,
                q='is:unread'  # Only fetch unread emails
            ).execute()
            
            messages = results.get('messages', [])
            emails = []
            
            for message in messages:
                email_data = await self._get_email_details(service, message['id'])
                if email_data:
                    emails.append(email_data)
            
            logger.info(f"Fetched {len(emails)} emails for user {user_id}")
            return emails
            
        except HttpError as e:
            logger.error(f"Gmail API error: {str(e)}")
            return []
        except Exception as e:
            logger.error(f"Error fetching emails: {str(e)}")
            return []
    
    async def _get_email_details(self, service, message_id: str) -> Optional[Dict]:
        """Get detailed email information"""
        try:
            message = service.users().messages().get(
                userId='me',
                id=message_id,
                format='full'
            ).execute()
            
            # Extract headers
            headers = message['payload']['headers']
            subject = ''
            from_email = ''
            to_email = ''
            date = ''
            
            for header in headers:
                if header['name'].lower() == 'subject':
                    subject = self._decode_header_value(header['value'])
                elif header['name'].lower() == 'from':
                    from_email = header['value']
                elif header['name'].lower() == 'to':
                    to_email = header['value']
                elif header['name'].lower() == 'date':
                    date = header['value']
            
            # Extract email body
            body = self._extract_email_body(message['payload'])
            
            # Extract sender name
            sender_name = from_email.split('<')[0].strip() if '<' in from_email else from_email
            sender_email = from_email.split('<')[1].replace('>', '').strip() if '<' in from_email else from_email
            
            return {
                'id': message_id,
                'subject': subject,
                'from_email': sender_email,
                'from_name': sender_name,
                'to_email': to_email,
                'date': date,
                'body': body,
                'snippet': message.get('snippet', ''),
                'thread_id': message.get('threadId'),
                'labels': message.get('labelIds', [])
            }
            
        except Exception as e:
            logger.error(f"Error getting email details for {message_id}: {str(e)}")
            return None
    
    def _decode_header_value(self, value: str) -> str:
        """Decode email header value"""
        try:
            decoded_parts = decode_header(value)
            decoded_value = ''
            
            for part, encoding in decoded_parts:
                if isinstance(part, bytes):
                    decoded_value += part.decode(encoding or 'utf-8', errors='ignore')
                else:
                    decoded_value += part
            
            return decoded_value
        except Exception:
            return value
    
    def _extract_email_body(self, payload: Dict) -> str:
        """Extract email body from payload"""
        try:
            if 'parts' in payload:
                # Multipart message
                for part in payload['parts']:
                    if part['mimeType'] == 'text/plain':
                        data = part['body']['data']
                        return base64.urlsafe_b64decode(data).decode('utf-8', errors='ignore')
                    elif part['mimeType'] == 'text/html' and 'parts' not in part:
                        # Fallback to HTML if no plain text
                        data = part['body']['data']
                        html_content = base64.urlsafe_b64decode(data).decode('utf-8', errors='ignore')
                        # Simple HTML to text conversion
                        import re
                        text = re.sub('<[^<]+?>', '', html_content)
                        return text.strip()
            else:
                # Single part message
                if payload['mimeType'] == 'text/plain':
                    data = payload['body']['data']
                    return base64.urlsafe_b64decode(data).decode('utf-8', errors='ignore')
                elif payload['mimeType'] == 'text/html':
                    data = payload['body']['data']
                    html_content = base64.urlsafe_b64decode(data).decode('utf-8', errors='ignore')
                    import re
                    text = re.sub('<[^<]+?>', '', html_content)
                    return text.strip()
            
            return ''
        except Exception as e:
            logger.error(f"Error extracting email body: {str(e)}")
            return ''
    
    async def mark_email_read(self, user_id: str, db, message_id: str) -> bool:
        """Mark email as read"""
        try:
            credentials = await self.get_credentials(user_id, db)
            if not credentials:
                return False
            
            service = build('gmail', 'v1', credentials=credentials)
            
            # Remove UNREAD label
            service.users().messages().modify(
                userId='me',
                id=message_id,
                body={'removeLabelIds': ['UNREAD']}
            ).execute()
            
            return True
            
        except Exception as e:
            logger.error(f"Error marking email as read: {str(e)}")
            return False
    
    async def send_email(self, user_id: str, db, to_email: str, subject: str, body: str) -> bool:
        """Send email via Gmail"""
        try:
            credentials = await self.get_credentials(user_id, db)
            if not credentials:
                return False
            
            service = build('gmail', 'v1', credentials=credentials)
            
            # Create email message
            message = email.message.EmailMessage()
            message.set_content(body)
            message['to'] = to_email
            message['subject'] = subject
            
            # Send message
            raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode()
            service.users().messages().send(
                userId='me',
                body={'raw': raw_message}
            ).execute()
            
            logger.info(f"Email sent to {to_email}")
            return True
            
        except Exception as e:
            logger.error(f"Error sending email: {str(e)}")
            return False

# Global Gmail service instance
gmail_service = GmailService()
