import requests
import asyncio
from motor.motor_asyncio import AsyncIOMotorClient

async def debug_telegram_updates():
    client = AsyncIOMotorClient('mongodb://localhost:27017')
    db = client.convo_sphere
    
    try:
        # Get Telegram integration
        integration = await db.integrations.find_one({'service': 'telegram'})
        if not integration:
            print('No Telegram integration found')
            return
        
        token = integration['token']
        
        # Get recent updates
        url = f"https://api.telegram.org/bot{token}/getUpdates?limit=5"
        response = requests.get(url)
        
        if response.status_code == 200:
            data = response.json()
            if data.get('ok'):
                updates = data.get('result', [])
                print(f'Found {len(updates)} recent updates:')
                
                for update in updates:
                    if 'message' in update:
                        message = update['message']
                        chat_info = message.get('chat', {})
                        print(f'Update ID: {update.get("update_id")}')
                        print(f'Chat ID: {chat_info.get("id")} (type: {type(chat_info.get("id"))})')
                        print(f'Chat Type: {chat_info.get("type")}')
                        print(f'From: {message.get("from", {}).get("first_name")} {message.get("from", {}).get("last_name", "")}')
                        print(f'Text: {message.get("text", "")}')
                        print(f'Raw chat object: {chat_info}')
                        print('---')
            else:
                print(f'API Error: {data}')
        else:
            print(f'HTTP Error: {response.status_code} - {response.text}')
    
    finally:
        client.close()

if __name__ == "__main__":
    asyncio.run(debug_telegram_updates())
