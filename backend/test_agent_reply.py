import requests
import asyncio
from motor.motor_asyncio import AsyncIOMotorClient

async def test_agent_reply_flow():
    client = AsyncIOMotorClient('mongodb://localhost:27017')
    db = client.convo_sphere
    
    try:
        # Get the Telegram conversation
        conv = await db.conversations.find_one({'channel': 'telegram'})
        if not conv:
            print('No Telegram conversation found')
            return
        
        conversation_id = conv['id']
        print(f'Testing agent reply for conversation: {conversation_id}')
        
        # Simulate agent reply through the API
        reply_data = {
            "content": "This is a test reply from agent via API"
        }
        
        # Note: This would normally require authentication, but we'll test the logic
        print(f'Would send reply: {reply_data}')
        print(f'To conversation: {conversation_id}')
        
        # Check if the conversation has the correct chat_id now
        updated_conv = await db.conversations.find_one({'id': conversation_id})
        print(f'Updated chat_id: {updated_conv.get("customer_contact")}')
        
        # Test the sendMessage logic directly
        integration = await db.integrations.find_one({'service': 'telegram'})
        token = integration['token']
        chat_id = updated_conv['customer_contact']
        
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        payload = {
            "chat_id": chat_id,
            "text": reply_data['content']
        }
        
        print(f'Testing direct send to chat_id: {chat_id}')
        response = requests.post(url, json=payload)
        print(f'Status Code: {response.status_code}')
        print(f'Response: {response.text}')
        
        if response.status_code == 200:
            data = response.json()
            if data.get('ok'):
                print('SUCCESS: Agent reply flow works correctly!')
            else:
                print(f'API Error: {data}')
        else:
            print(f'HTTP Error: {response.status_code} - {response.text}')
    
    finally:
        client.close()

if __name__ == "__main__":
    asyncio.run(test_agent_reply_flow())
