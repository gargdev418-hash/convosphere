import requests
import asyncio
from motor.motor_asyncio import AsyncIOMotorClient

async def test_telegram_polling():
    client = AsyncIOMotorClient('mongodb://localhost:27017')
    db = client.convo_sphere
    
    try:
        print("Testing Telegram polling endpoint...")
        
        # Call the polling endpoint
        response = requests.get('http://localhost:8000/api/telegram/poll')
        
        print(f"Status Code: {response.status_code}")
        print(f"Response: {response.text}")
        
        if response.status_code == 200:
            data = response.json()
            print(f"Updates processed: {data.get('updates_processed', 0)}")
            
            # Check if new messages were added to database
            msg_count_before = await db.messages.count_documents({'channel': 'telegram'})
            print(f"Telegram messages in database: {msg_count_before}")
            
            # Call polling again
            response2 = requests.get('http://localhost:8000/api/telegram/poll')
            print(f"Second call - Status: {response2.status_code}")
            print(f"Second call - Response: {response2.text}")
            
            # Check message count again
            msg_count_after = await db.messages.count_documents({'channel': 'telegram'})
            print(f"Telegram messages after second poll: {msg_count_after}")
            
        else:
            print(f"Error calling polling endpoint: {response.status_code}")
    
    finally:
        client.close()

if __name__ == "__main__":
    asyncio.run(test_telegram_polling())
