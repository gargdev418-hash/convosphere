import requests
import sys
import json
from datetime import datetime

class ConvoSphereAPITester:
    def __init__(self, base_url="http://localhost:8000/api"):
        self.base_url = base_url
        self.token = None
        self.user_id = None
        self.tests_run = 0
        self.tests_passed = 0
        self.conversation_id = None

    def run_test(self, name, method, endpoint, expected_status, data=None, headers=None):
        """Run a single API test"""
        url = f"{self.base_url}/{endpoint}"
        test_headers = {'Content-Type': 'application/json'}
        
        if self.token:
            test_headers['Authorization'] = f'Bearer {self.token}'
        
        if headers:
            test_headers.update(headers)

        self.tests_run += 1
        print(f"\n🔍 Testing {name}...")
        print(f"   URL: {url}")
        
        try:
            if method == 'GET':
                response = requests.get(url, headers=test_headers, timeout=30)
            elif method == 'POST':
                response = requests.post(url, json=data, headers=test_headers, timeout=30)
            elif method == 'PUT':
                response = requests.put(url, json=data, headers=test_headers, timeout=30)
            elif method == 'DELETE':
                response = requests.delete(url, headers=test_headers, timeout=30)

            print(f"   Status: {response.status_code}")
            
            success = response.status_code == expected_status
            if success:
                self.tests_passed += 1
                print(f"✅ Passed - Status: {response.status_code}")
                try:
                    response_data = response.json()
                    print(f"   Response: {json.dumps(response_data, indent=2)[:200]}...")
                    return True, response_data
                except:
                    return True, {}
            else:
                print(f"❌ Failed - Expected {expected_status}, got {response.status_code}")
                try:
                    error_data = response.json()
                    print(f"   Error: {error_data}")
                except:
                    print(f"   Error: {response.text}")
                return False, {}

        except Exception as e:
            print(f"❌ Failed - Error: {str(e)}")
            return False, {}

    def test_register(self):
        """Test user registration"""
        timestamp = datetime.now().strftime('%H%M%S')
        test_data = {
            "email": f"test_user_{timestamp}@example.com",
            "password": "TestPass123!",
            "name": f"Test User {timestamp}"
        }
        
        success, response = self.run_test(
            "User Registration",
            "POST",
            "auth/register",
            200,
            data=test_data
        )
        
        if success and 'token' in response:
            self.token = response['token']
            self.user_id = response['user']['id']
            print(f"   Token obtained: {self.token[:20]}...")
            return True
        return False

    def test_login(self):
        """Test user login with existing credentials"""
        # Try to login with the registered user
        if not self.token:
            print("❌ No token from registration, cannot test login")
            return False
            
        # For now, we'll use the token from registration
        # In a real scenario, we'd test login separately
        return True

    def test_get_me(self):
        """Test getting current user info"""
        success, response = self.run_test(
            "Get Current User",
            "GET",
            "auth/me",
            200
        )
        return success

    def test_create_conversation(self):
        """Test creating a new conversation"""
        success, response = self.run_test(
            "Create Conversation",
            "POST",
            "conversations?customer_name=John Doe&customer_contact=john@example.com&channel=email",
            200
        )
        
        if success and 'id' in response:
            self.conversation_id = response['id']
            print(f"   Conversation ID: {self.conversation_id}")
            return True
        return False

    def test_get_conversations_filter(self):
        """Test getting conversations with filters"""
        filter_data = {
            "channel": None,
            "status": None,
            "priority": None,
            "sentiment": None,
            "search": None
        }
        
        success, response = self.run_test(
            "Get Conversations (Filter)",
            "POST",
            "conversations/filter",
            200,
            data=filter_data
        )
        return success

    def test_get_conversations_filter_by_channel(self):
        """Test filtering conversations by channel"""
        filter_data = {
            "channel": "email",
            "status": None,
            "priority": None,
            "sentiment": None,
            "search": None
        }
        
        success, response = self.run_test(
            "Filter Conversations by Email Channel",
            "POST",
            "conversations/filter",
            200,
            data=filter_data
        )
        return success

    def test_get_conversation_details(self):
        """Test getting specific conversation details"""
        if not self.conversation_id:
            print("❌ No conversation ID available")
            return False
            
        success, response = self.run_test(
            "Get Conversation Details",
            "GET",
            f"conversations/{self.conversation_id}",
            200
        )
        return success

    def test_ingest_customer_message(self):
        """Test ingesting a customer message with AI analysis"""
        if not self.conversation_id:
            print("❌ No conversation ID available")
            return False
            
        message_data = {
            "conversation_id": self.conversation_id,
            "content": "Hi, I'm having trouble with my order. It hasn't arrived yet and I'm really frustrated!",
            "sender_name": "John Doe",
            "sender_type": "customer",
            "channel": "email"
        }
        
        success, response = self.run_test(
            "Ingest Customer Message (AI Analysis)",
            "POST",
            "messages/ingest",
            200,
            data=message_data
        )
        
        if success:
            print("   🤖 AI should analyze this message for intent, sentiment, and priority")
            print("   🤖 High confidence messages should trigger auto-response")
        
        return success

    def test_get_conversation_messages(self):
        """Test getting messages for a conversation"""
        if not self.conversation_id:
            print("❌ No conversation ID available")
            return False
            
        success, response = self.run_test(
            "Get Conversation Messages",
            "GET",
            f"conversations/{self.conversation_id}/messages",
            200
        )
        
        if success and isinstance(response, list):
            print(f"   Found {len(response)} messages")
            for msg in response:
                print(f"   - {msg.get('sender_type', 'unknown')}: {msg.get('content', '')[:50]}...")
        
        return success

    def test_agent_response(self):
        """Test agent responding to conversation"""
        if not self.conversation_id:
            print("❌ No conversation ID available")
            return False
            
        response_data = {
            "conversation_id": self.conversation_id,
            "content": "Hi John, I apologize for the delay. Let me check your order status right away and get back to you with an update."
        }
        
        success, response = self.run_test(
            "Agent Response",
            "POST",
            f"conversations/{self.conversation_id}/respond",
            200,
            data=response_data
        )
        return success

    def test_stats(self):
        """Test getting dashboard statistics"""
        success, response = self.run_test(
            "Get Dashboard Stats",
            "GET",
            "stats",
            200
        )
        
        if success:
            print(f"   Total Conversations: {response.get('total_conversations', 'N/A')}")
            print(f"   Open Conversations: {response.get('open_conversations', 'N/A')}")
            print(f"   Total Messages: {response.get('total_messages', 'N/A')}")
            print(f"   Unread Messages: {response.get('unread_messages', 'N/A')}")
        
        return success

    def test_additional_channels(self):
        """Test creating conversations for different channels"""
        channels = ["whatsapp", "slack", "telegram"]
        results = []
        
        for channel in channels:
            success, response = self.run_test(
                f"Create {channel.title()} Conversation",
                "POST",
                f"conversations?customer_name=Test User&customer_contact=test@example.com&channel={channel}",
                200
            )
            results.append(success)
        
        return all(results)

def main():
    print("🚀 Starting Convo Sphere API Testing...")
    print("=" * 60)
    
    tester = ConvoSphereAPITester()
    
    # Test sequence
    tests = [
        ("User Registration", tester.test_register),
        ("User Authentication Check", tester.test_get_me),
        ("Create Conversation", tester.test_create_conversation),
        ("Get All Conversations", tester.test_get_conversations_filter),
        ("Filter by Channel", tester.test_get_conversations_filter_by_channel),
        ("Get Conversation Details", tester.test_get_conversation_details),
        ("Ingest Customer Message (AI)", tester.test_ingest_customer_message),
        ("Get Conversation Messages", tester.test_get_conversation_messages),
        ("Agent Response", tester.test_agent_response),
        ("Dashboard Statistics", tester.test_stats),
        ("Multi-Channel Support", tester.test_additional_channels),
    ]
    
    print(f"\n📋 Running {len(tests)} test suites...")
    
    for test_name, test_func in tests:
        print(f"\n{'='*20} {test_name} {'='*20}")
        try:
            test_func()
        except Exception as e:
            print(f"❌ Test suite failed with error: {str(e)}")
    
    # Final results
    print(f"\n{'='*60}")
    print(f"📊 FINAL RESULTS")
    print(f"{'='*60}")
    print(f"Tests Run: {tester.tests_run}")
    print(f"Tests Passed: {tester.tests_passed}")
    print(f"Tests Failed: {tester.tests_run - tester.tests_passed}")
    print(f"Success Rate: {(tester.tests_passed/tester.tests_run*100):.1f}%" if tester.tests_run > 0 else "No tests run")
    
    if tester.tests_passed == tester.tests_run:
        print("🎉 ALL TESTS PASSED!")
        return 0
    else:
        print("⚠️  SOME TESTS FAILED - Check logs above")
        return 1

if __name__ == "__main__":
    sys.exit(main())