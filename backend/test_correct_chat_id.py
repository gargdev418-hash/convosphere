import requests
import asyncio
from motor.motor_asyncio import AsyncIOMotorClient

async def test_correct_chat_id():
    client = AsyncIOMotorClient('mongodb://localhost:27017')
    db = client.convo_sphere
    
    try:
        # Get Telegram integration
        integration = await db.integrations.find_one({'service': 'telegram'})
        token = integration['token']
        
        # Test with the correct chat_id from getUpdates
        correct_chat_id = "6280199115"
        
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        payload = {
            "chat_id": correct_chat_id,
            "text": "Test message with correct chat_id format"
        }
        
        print(f'Testing with correct chat_id: {correct_chat_id}')
        response = requests.post(url, json=payload)
        print(f'Status Code: {response.status_code}')
        print(f'Response: {response.text}')
        
        if response.status_code == 200:
            data = response.json()
            if data.get('ok'):
                print('SUCCESS: Message sent with correct chat_id!')
                
                # Now update the database with the correct chat_id
                result = await db.conversations.update_many(
                    {'channel': 'telegram'},
                    {'$set': {'customer_contact': correct_chat_id}}
                )
                print(f'Updated {result.modified_count} conversations with correct chat_id')
            else:
                print(f'API Error: {data}')
        else:
            print(f'HTTP Error: {response.status_code} - {response.text}')
    
    finally:
        client.close()

if __name__ == "__main__":
    asyncio.run(test_correct_chat_id())
