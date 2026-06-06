"""
Test script for the Auto-Reply Service
"""

import asyncio
import sys
import os

# Add the backend directory to the path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from services.auto_reply_service import auto_reply_service

async def test_auto_reply():
    """Test the auto-reply service with different message types."""
    
    print("Testing Auto-Reply Service")
    print("=" * 50)
    
    test_cases = [
        ("Hi there", "Greeting"),
        ("Hello! I need help", "Greeting + Help"),
        ("Can you help me with my account?", "Help request"),
        ("What are your prices?", "Pricing inquiry"),
        ("Where are you located?", "Contact inquiry"),
        ("Thank you for your help", "Thank you"),
        ("Goodbye", "Goodbye"),
        ("Random message about something", "Default case"),
        ("", "Empty message"),
        ("HELP ME NOW", "Uppercase help"),
    ]
    
    for message, description in test_cases:
        print(f"\nTest: {description}")
        print(f"Input: '{message}'")
        
        reply = auto_reply_service.generate_auto_reply(message)
        print(f"Reply: '{reply}'")
        print("-" * 30)
    
    print("\n" + "=" * 50)
    print("Auto-Reply Service Test Complete")
    print(f"Service Enabled: {auto_reply_service.enabled}")

if __name__ == "__main__":
    asyncio.run(test_auto_reply())
