import asyncio
from motor.motor_asyncio import AsyncIOMotorClient

async def check_telegram_data():
    client = AsyncIOMotorClient('mongodb://localhost:27017')
    db = client.convo_sphere
    
    try:
        # Check Telegram conversations
        telegram_convs = await db.conversations.find({'channel': 'telegram'}).to_list(10)
        print(f'Found {len(telegram_convs)} Telegram conversations')
        
        for conv in telegram_convs:
            print(f'Conversation ID: {conv.get("id")}')
            print(f'Customer Contact: {conv.get("customer_contact")}')
            print(f'Channel: {conv.get("channel")}')
            print(f'Status: {conv.get("status")}')
            print('---')
        
        # Check Telegram messages
        telegram_msgs = await db.messages.find({'channel': 'telegram'}).to_list(10)
        print(f'Found {len(telegram_msgs)} Telegram messages')
        
        for msg in telegram_msgs:
            print(f'Message ID: {msg.get("id")}')
            print(f'Conversation ID: {msg.get("conversation_id")}')
            print(f'Content: {msg.get("content")}')
            print(f'Sender: {msg.get("sender_name")}')
            print('---')
        
        # Check integrations
        integrations = await db.integrations.find({'service': 'telegram'}).to_list(10)
        print(f'Found {len(integrations)} Telegram integrations')
        
        for integration in integrations:
            print(f'User ID: {integration.get("user_id")}')
            print(f'Bot Username: {integration.get("bot_username")}')
            print(f'Token exists: {bool(integration.get("token"))}')
            print('---')
    
    finally:
        client.close()

if __name__ == "__main__":
    asyncio.run(check_telegram_data())
