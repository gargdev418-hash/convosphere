import asyncio
import requests
from motor.motor_asyncio import AsyncIOMotorClient

async def test_telegram_send():
    client = AsyncIOMotorClient('mongodb://localhost:27017')
    db = client.convo_sphere
    
    try:
        # Get Telegram integration
        integration = await db.integrations.find_one({'service': 'telegram'})
        if not integration:
            print('No Telegram integration found')
            return
        
        token = integration['token']
        print(f'Using token: {token[:10]}...')
        
        # Get a Telegram conversation
        conv = await db.conversations.find_one({'channel': 'telegram'})
        if not conv:
            print('No Telegram conversation found')
            return
        
        chat_id = conv['customer_contact']
        print(f'Using chat_id: {chat_id}')
        
        # Test sending a message
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        payload = {
            "chat_id": chat_id,
            "text": "Test message from Convo Sphere diagnostic"
        }
        
        print(f'Sending to: {url}')
        print(f'Payload: {payload}')
        
        response = requests.post(url, json=payload)
        print(f'Status Code: {response.status_code}')
        print(f'Response: {response.text}')
        
        if response.status_code == 200:
            data = response.json()
            if data.get('ok'):
                print('SUCCESS: Message sent successfully!')
            else:
                print(f'ERROR: Telegram API returned error: {data}')
        else:
            print(f'ERROR: HTTP {response.status_code} - {response.text}')
    
    finally:
        client.close()

if __name__ == "__main__":
    asyncio.run(test_telegram_send())
