import requests

async def test_chat_id_formats():
    # Get the token from database
    import asyncio
    from motor.motor_asyncio import AsyncIOMotorClient
    
    client = AsyncIOMotorClient('mongodb://localhost:27017')
    db = client.convo_sphere
    
    try:
        integration = await db.integrations.find_one({'service': 'telegram'})
        token = integration['token']
        
        # Test different chat_id formats
        chat_formats = [
            "+917906828982",    # Current stored format
            "917906828982",     # Without +
            "-917906828982",    # With - (for some cases)
        ]
        
        for chat_id in chat_formats:
            url = f"https://api.telegram.org/bot{token}/sendMessage"
            payload = {
                "chat_id": chat_id,
                "text": f"Testing format: {chat_id}"
            }
            
            print(f'Testing chat_id: {chat_id}')
            response = requests.post(url, json=payload)
            print(f'Status: {response.status_code}')
            print(f'Response: {response.text}')
            print('---')
    
    finally:
        client.close()

if __name__ == "__main__":
    import asyncio
    asyncio.run(test_chat_id_formats())
