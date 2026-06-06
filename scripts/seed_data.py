import sys
sys.path.append('/app/backend')

import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
from datetime import datetime, timezone, timedelta
import uuid
import os
from dotenv import load_dotenv
from pathlib import Path

ROOT_DIR = Path('/app/backend')
load_dotenv(ROOT_DIR / '.env')

mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

async def seed_data():
    print("Seeding sample data...")
    
    # Sample conversations
    conversations = [
        {
            'id': str(uuid.uuid4()),
            'customer_name': 'John Doe',
            'customer_contact': 'john@example.com',
            'channel': 'email',
            'status': 'open',
            'priority': 'high',
            'sentiment': 'negative',
            'intent': 'complaint',
            'unread_count': 2,
            'last_message_at': (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat(),
            'created_at': (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
        },
        {
            'id': str(uuid.uuid4()),
            'customer_name': 'Sarah Wilson',
            'customer_contact': '+1234567890',
            'channel': 'whatsapp',
            'status': 'open',
            'priority': 'medium',
            'sentiment': 'neutral',
            'intent': 'question',
            'unread_count': 1,
            'last_message_at': (datetime.now(timezone.utc) - timedelta(minutes=15)).isoformat(),
            'created_at': (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        },
        {
            'id': str(uuid.uuid4()),
            'customer_name': 'Mike Johnson',
            'customer_contact': '@mikej',
            'channel': 'slack',
            'status': 'waiting',
            'priority': 'low',
            'sentiment': 'positive',
            'intent': 'feedback',
            'unread_count': 0,
            'last_message_at': (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat(),
            'created_at': (datetime.now(timezone.utc) - timedelta(hours=5)).isoformat()
        },
        {
            'id': str(uuid.uuid4()),
            'customer_name': 'Emma Davis',
            'customer_contact': '@emmad',
            'channel': 'telegram',
            'status': 'open',
            'priority': 'high',
            'sentiment': 'neutral',
            'intent': 'request',
            'unread_count': 3,
            'last_message_at': (datetime.now(timezone.utc) - timedelta(minutes=2)).isoformat(),
            'created_at': (datetime.now(timezone.utc) - timedelta(minutes=30)).isoformat()
        }
    ]
    
    # Clear existing data
    await db.conversations.delete_many({})
    await db.messages.delete_many({})
    
    # Insert conversations
    await db.conversations.insert_many(conversations)
    print(f"✓ Created {len(conversations)} conversations")
    
    # Sample messages for each conversation
    for conv in conversations:
        messages = [
            {
                'id': str(uuid.uuid4()),
                'conversation_id': conv['id'],
                'sender_type': 'customer',
                'sender_name': conv['customer_name'],
                'content': 'Hello, I need help with my account.',
                'channel': conv['channel'],
                'timestamp': (datetime.now(timezone.utc) - timedelta(minutes=20)).isoformat(),
                'metadata': {}
            },
            {
                'id': str(uuid.uuid4()),
                'conversation_id': conv['id'],
                'sender_type': 'ai',
                'sender_name': 'AI Assistant',
                'content': 'Hello! I\'d be happy to help you with your account. Can you please provide more details about the issue you\'re experiencing?',
                'channel': conv['channel'],
                'timestamp': (datetime.now(timezone.utc) - timedelta(minutes=19)).isoformat(),
                'metadata': {}
            },
            {
                'id': str(uuid.uuid4()),
                'conversation_id': conv['id'],
                'sender_type': 'customer',
                'sender_name': conv['customer_name'],
                'content': 'I\'m unable to log in to my account. It keeps saying invalid credentials.',
                'channel': conv['channel'],
                'timestamp': (datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat(),
                'metadata': {}
            }
        ]
        await db.messages.insert_many(messages)
    
    print(f"✓ Created sample messages for all conversations")
    print("Seeding completed successfully!")

if __name__ == "__main__":
    asyncio.run(seed_data())
