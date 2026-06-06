"""
Test script for the complete Auto-Reply Service with MongoDB and WebSocket functionality
"""

import asyncio
import sys
import os
from datetime import datetime, timezone

# Add the backend directory to the path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from motor.motor_asyncio import AsyncIOMotorClient
from services.auto_reply_service import AutoReplyService

class MockWebSocketManager:
    """Mock WebSocket manager for testing"""
    def __init__(self):
        self.broadcasts = []
    
    async def broadcast(self, message):
        """Mock broadcast that stores messages for verification"""
        self.broadcasts.append(message)
        print(f"WebSocket Broadcast: {message['type']} - {message.get('conversation_id')}")

async def test_auto_reply_full():
    """Test the complete auto-reply flow with database and WebSocket."""
    
    print("Testing Complete Auto-Reply Service Flow")
    print("=" * 60)
    
    # Setup
    mock_manager = MockWebSocketManager()
    auto_reply_service = AutoReplyService(websocket_manager=mock_manager)
    
    # MongoDB connection
    client = AsyncIOMotorClient('mongodb://localhost:27017')
    db = client.convo_sphere
    
    # Test conversation data
    test_conversation_id = "test-conv-123"
    test_customer_contact = "test@example.com"
    test_channel = "email"
    
    try:
        # Create test conversation
        conversation = {
            "id": test_conversation_id,
            "customer_name": "Test Customer",
            "customer_contact": test_customer_contact,
            "channel": test_channel,
            "status": "open",
            "priority": "medium",
            "sentiment": "neutral",
            "intent": "general",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "last_message_at": datetime.now(timezone.utc).isoformat(),
            "unread_count": 1
        }
        
        await db.conversations.insert_one(conversation)
        print(f"Created test conversation: {test_conversation_id}")
        
        # Test customer message scenarios
        test_scenarios = [
            ("Hi there", "Greeting"),
            ("I need help with my account", "Help request"),
            ("What are your prices?", "Pricing inquiry"),
            ("Thank you for your help", "Thank you"),
            ("Random message", "Default case")
        ]
        
        for i, (message_content, description) in enumerate(test_scenarios):
            print(f"\n--- Test {i+1}: {description} ---")
            print(f"Customer message: '{message_content}'")
            
            # Process auto-reply
            success = await auto_reply_service.process_auto_reply(
                conversation_id=test_conversation_id,
                message_content=message_content,
                sender_type="customer",
                channel=test_channel,
                customer_contact=test_customer_contact
            )
            
            print(f"Auto-reply success: {success}")
            
            # Check if auto-reply was saved in database
            auto_replies = await db.messages.find({
                "conversation_id": test_conversation_id,
                "sender_type": "ai"
            }).to_list(10)
            
            if auto_replies:
                latest_reply = auto_replies[-1]
                print(f"Saved in database: {latest_reply['content'][:50]}...")
                print(f"Sender: {latest_reply['sender_name']}")
                print(f"Channel: {latest_reply['channel']}")
            else:
                print("No auto-reply found in database")
            
            # Check WebSocket broadcast
            if mock_manager.broadcasts:
                latest_broadcast = mock_manager.broadcasts[-1]
                print(f"WebSocket broadcast: {latest_broadcast['type']}")
            else:
                print("No WebSocket broadcast")
        
        # Verify final state
        print("\n" + "=" * 60)
        print("Final Verification:")
        
        all_messages = await db.messages.find({
            "conversation_id": test_conversation_id
        }).to_list(20)
        
        customer_messages = [msg for msg in all_messages if msg['sender_type'] == 'customer']
        ai_messages = [msg for msg in all_messages if msg['sender_type'] == 'ai']
        
        print(f"Total messages: {len(all_messages)}")
        print(f"Customer messages: {len(customer_messages)}")
        print(f"Auto-reply messages: {len(ai_messages)}")
        print(f"WebSocket broadcasts: {len(mock_manager.broadcasts)}")
        
        # Clean up test data
        await db.messages.delete_many({"conversation_id": test_conversation_id})
        await db.conversations.delete_many({"id": test_conversation_id})
        print(f"\nTest data cleaned up")
        
    except Exception as e:
        print(f"Test error: {str(e)}")
    
    finally:
        client.close()
    
    print("\n" + "=" * 60)
    print("Complete Auto-Reply Service Test Complete")

if __name__ == "__main__":
    asyncio.run(test_auto_reply_full())
