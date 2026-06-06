# ConvoSphere - Implementation Guide

## New Features Implemented

### 1. AI Message Analysis ✅
- **Location**: `backend/services/ai_service.py`
- **Features**:
  - Sentiment analysis (positive, negative, neutral)
  - Intent detection (inquiry, complaint, support_request, sales, feedback, general)
  - Priority classification (high, medium, low)
  - Spam detection
  - Auto-response suggestions
- **Integration**: Automatically analyzes all incoming messages
- **Fallback**: Keyword-based analysis when AI service fails

### 2. Real-Time Messaging ✅
- **WebSocket Endpoint**: `ws://localhost:8000/ws`
- **Features**:
  - Live message broadcasting
  - Automatic reconnection
  - Connection status indicators
  - Custom event handling
- **Frontend Hooks**:
  - `useWebSocket()` - Core WebSocket management
  - `useWebSocketContext()` - React context for WebSocket state
  - `useRealTimeConversations()` - Real-time conversation updates
  - `useRealTimeMessages()` - Real-time message updates

### 3. WhatsApp Business API Integration ✅
- **Webhook Endpoint**: `/api/whatsapp/webhook`
- **Features**:
  - Incoming message processing
  - Automatic conversation creation
  - AI-powered auto-replies
  - Message broadcasting via WebSocket
- **Connection**: `/api/integrations/whatsapp/connect`

### 4. Gmail OAuth & Email Ingestion ✅
- **OAuth Flow**: Complete Gmail OAuth implementation
- **Features**:
  - Secure token storage
  - Automatic email fetching
  - Email-to-conversation conversion
  - Unread email processing
  - AI analysis of email content
  - Auto-reply functionality
- **Endpoints**:
  - `/api/integrations/gmail/authorize` - Start OAuth flow
  - `/api/integrations/gmail/callback` - Handle OAuth callback
  - `/api/gmail/sync` - Manual email sync

## Environment Variables Required

Add these to your `backend/.env` file:

```env
# OpenAI Configuration
OPENAI_API_KEY=your_openai_api_key_here
OPENAI_MODEL=gpt-3.5-turbo

# Google OAuth Configuration
GOOGLE_CLIENT_ID=your_google_client_id_here
GOOGLE_CLIENT_SECRET=your_google_client_secret_here
GOOGLE_REDIRECT_URI=http://localhost:8000/api/integrations/gmail/callback

# WhatsApp Business API Configuration
WHATSAPP_VERIFY_TOKEN=convo-sphere-verify-token

# Existing variables
MONGO_URL=mongodb://localhost:27017
DB_NAME=convo_sphere
JWT_SECRET=your_jwt_secret_here
```

## Installation & Setup

### Backend Setup

1. **Install Dependencies**:
```bash
cd backend
pip install -r requirements.txt
```

2. **Set Environment Variables**:
   - Copy `.env.example` to `.env` (if exists)
   - Add all required environment variables from above

3. **Start Backend Server**:
```bash
python server.py
```

### Frontend Setup

1. **Install Dependencies**:
```bash
cd frontend
npm install
```

2. **Start Development Server**:
```bash
npm start
```

## Integration Setup Guide

### WhatsApp Business API

1. **Create WhatsApp Business Account**:
   - Go to [Meta for Developers](https://developers.facebook.com/)
   - Create a new app with WhatsApp Business API
   - Get your Access Token and Phone Number ID

2. **Configure Webhook**:
   - Set webhook URL: `https://your-domain.com/api/whatsapp/webhook`
   - Verify webhook with your verify token

3. **Connect in App**:
   - Go to Integrations page
   - Select WhatsApp
   - Enter Access Token, Phone Number ID, and Webhook URL

### Gmail Integration

1. **Create Google Cloud Project**:
   - Go to [Google Cloud Console](https://console.cloud.google.com/)
   - Create new project
   - Enable Gmail API

2. **Create OAuth Credentials**:
   - Go to Credentials → Create Credentials → OAuth 2.0 Client ID
   - Select Web application
   - Add authorized redirect URI: `http://localhost:8000/api/integrations/gmail/callback`
   - Copy Client ID and Client Secret

3. **Connect in App**:
   - Go to Integrations page
   - Select Gmail
   - Click "Connect Gmail" and complete OAuth flow

### OpenAI Integration

1. **Get OpenAI API Key**:
   - Go to [OpenAI Platform](https://platform.openai.com/)
   - Create API key

2. **Add to Environment**:
   - Add `OPENAI_API_KEY` to your `.env` file

## Usage Examples

### Using Real-Time Features in Components

```jsx
import { useWebSocketContext } from '../contexts/WebSocketContext';
import { useRealTimeConversations } from '../hooks/useRealTimeConversations';

function ConversationList() {
  const { isConnected, newMessageCount } = useWebSocketContext();
  const { conversations, loading, error, refreshConversations } = useRealTimeConversations();

  return (
    <div>
      <div className="flex items-center gap-2 mb-4">
        <span>Connection: {isConnected ? 'Connected' : 'Disconnected'}</span>
        {newMessageCount > 0 && (
          <span>{newMessageCount} new messages</span>
        )}
        <button onClick={refreshConversations}>Refresh</button>
      </div>
      
      {loading ? (
        <div>Loading...</div>
      ) : error ? (
        <div>Error: {error}</div>
      ) : (
        conversations.map(conv => (
          <div key={conv.id}>{conv.customer_name}</div>
        ))
      )}
    </div>
  );
}
```

### WebSocket Event Handling

```jsx
import { useEffect } from 'react';

function MyComponent() {
  useEffect(() => {
    const handleNewMessage = (event) => {
      const { conversation_id, message } = event.detail;
      console.log('New message:', message);
      // Handle new message (show notification, update UI, etc.)
    };

    window.addEventListener('newMessage', handleNewMessage);
    
    return () => {
      window.removeEventListener('newMessage', handleNewMessage);
    };
  }, []);

  return <div>My Component</div>;
}
```

## Testing the Features

### 1. AI Analysis
- Send a test message through any channel
- Check the conversation for updated sentiment, intent, and priority
- Verify auto-responses for high-confidence analysis

### 2. Real-Time Updates
- Open the app in two browser windows
- Send a message in one window
- Verify the other window updates automatically

### 3. WhatsApp Integration
- Send a message to your WhatsApp Business number
- Verify it appears in the conversations
- Check for AI auto-replies if enabled

### 4. Gmail Integration
- Connect your Gmail account
- Send a test email to your connected address
- Verify it appears as a conversation
- Check for AI analysis and auto-replies

## Troubleshooting

### WebSocket Connection Issues
- Ensure backend is running on port 8000
- Check for firewall issues
- Verify JWT token is valid

### Gmail OAuth Issues
- Verify redirect URI matches exactly
- Check that Gmail API is enabled
- Ensure OAuth consent screen is configured

### WhatsApp Webhook Issues
- Verify webhook URL is accessible
- Check that verify token matches
- Ensure webhook is subscribed to messages field

### AI Analysis Issues
- Check OpenAI API key is valid
- Verify sufficient API credits
- Check network connectivity to OpenAI

## File Structure

```
backend/
├── services/
│   ├── ai_service.py          # AI message analysis
│   └── gmail_service.py       # Gmail API integration
├── server.py                  # Main FastAPI server with all endpoints
└── requirements.txt           # Updated dependencies

frontend/
├── src/
│   ├── hooks/
│   │   ├── useWebSocket.js           # WebSocket management
│   │   ├── useRealTimeConversations.js  # Real-time conversations
│   │   └── useRealTimeMessages.js       # Real-time messages
│   ├── contexts/
│   │   └── WebSocketContext.js     # WebSocket React context
│   ├── components/
│   │   └── RealTimeIndicator.js    # Connection status component
│   └── App.js                   # Updated with WebSocket provider
```

## API Endpoints Summary

### New Endpoints Added

#### AI Analysis
- Integrated into existing `/api/messages/ingest` endpoint

#### WhatsApp
- `POST /api/whatsapp/webhook` - Receive WhatsApp messages
- `GET /api/whatsapp/webhook` - Verify webhook
- `POST /api/integrations/whatsapp/connect` - Connect WhatsApp

#### Gmail
- `GET /api/integrations/gmail/authorize` - Start OAuth flow
- `POST /api/integrations/gmail/callback` - Handle OAuth callback
- `POST /api/gmail/sync` - Manual email sync

#### WebSocket
- `WS /ws` - Real-time WebSocket connection

### Existing Endpoints Enhanced
- `/api/messages/ingest` - Now includes AI analysis
- `/api/conversations/{id}/respond` - Enhanced with WhatsApp sending
- All message endpoints now broadcast via WebSocket

## Security Considerations

1. **API Keys**: Store all API keys in environment variables
2. **Tokens**: Encrypt sensitive tokens in database
3. **Webhooks**: Verify webhook signatures when possible
4. **CORS**: Configure proper CORS origins
5. **Rate Limiting**: Consider implementing rate limits for external APIs

## Performance Considerations

1. **AI Analysis**: Cache results for similar messages
2. **WebSocket**: Implement connection pooling for high traffic
3. **Email Sync**: Use pagination for large email inboxes
4. **Database**: Add indexes for conversation and message queries

## Future Enhancements

1. **Multi-language AI analysis**
2. **Advanced sentiment analysis with emotion detection**
3. **File attachment support for WhatsApp and email**
4. **Message templates and canned responses**
5. **Analytics dashboard for AI insights**
6. **Integration with more messaging platforms**
