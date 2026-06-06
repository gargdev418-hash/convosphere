import logging
from typing import List, Dict, Optional, Set
from fastapi import WebSocket, WebSocketDisconnect
from utils.mongo_serializer import prepare_websocket_message

logger = logging.getLogger(__name__)

class ConnectionManager:
    """
    Enhanced WebSocket Connection Manager with error handling and safe operations.
    """
    
    def __init__(self):
        # Use set for O(1) lookups and prevent duplicates
        self.active_connections: Set[WebSocket] = set()
        # Keep track of connection metadata
        self.connection_info: Dict[WebSocket, Dict] = {}
    
    async def connect(self, websocket: WebSocket, connection_id: Optional[str] = None):
        """
        Safely connect a new WebSocket client.
        """
        try:
            await websocket.accept()
            self.active_connections.add(websocket)
            
            # Store connection metadata
            self.connection_info[websocket] = {
                'id': connection_id or str(id(websocket)),
                'connected_at': websocket.scope.get('client', ['unknown', 0])[0],
                'state': 'connected'
            }
            
            logger.info(f"WebSocket connected. Total connections: {len(self.active_connections)}")
            return True
            
        except Exception as e:
            logger.error(f"Error accepting WebSocket connection: {str(e)}")
            return False
    
    def disconnect(self, websocket: WebSocket):
        """
        Safely disconnect a WebSocket client.
        """
        try:
            # Remove from active connections (safe operation)
            self.active_connections.discard(websocket)
            
            # Remove connection info
            if websocket in self.connection_info:
                del self.connection_info[websocket]
            
            logger.info(f"WebSocket disconnected. Total connections: {len(self.active_connections)}")
            
        except Exception as e:
            logger.error(f"Error during WebSocket disconnect: {str(e)}")
    
    async def send_message(self, websocket: WebSocket, message: Dict) -> bool:
        """
        Send message to a specific WebSocket client.
        """
        try:
            if websocket in self.active_connections:
                prepared_message = prepare_websocket_message(message)
                await websocket.send_json(prepared_message)
                return True
            return False
            
        except WebSocketDisconnect:
            # Client disconnected normally
            self.disconnect(websocket)
            return False
            
        except Exception as e:
            logger.error(f"Error sending message to WebSocket: {str(e)}")
            # Remove problematic connection
            self.disconnect(websocket)
            return False
    
    async def broadcast(self, message: Dict):
        """
        Broadcast message to all connected clients.
        """
        if not self.active_connections:
            return
        
        prepared_message = prepare_websocket_message(message)
        disconnected_clients = []
        
        # Send to all connections
        for websocket in list(self.active_connections):
            try:
                await websocket.send_json(prepared_message)
            except WebSocketDisconnect:
                disconnected_clients.append(websocket)
            except Exception as e:
                logger.error(f"Error broadcasting to WebSocket: {str(e)}")
                disconnected_clients.append(websocket)
        
        # Clean up disconnected clients
        for websocket in disconnected_clients:
            self.disconnect(websocket)
    
    async def broadcast_to_conversation(self, conversation_id: str, message: Dict):
        """
        Broadcast message to clients subscribed to a specific conversation.
        """
        if not self.active_connections:
            return
        
        prepared_message = prepare_websocket_message(message)
        disconnected_clients = []
        
        for websocket in list(self.active_connections):
            try:
                # Check if client is subscribed to this conversation
                connection_info = self.connection_info.get(websocket, {})
                subscribed_conversations = connection_info.get('conversations', [])
                
                if not subscribed_conversations or conversation_id in subscribed_conversations:
                    await websocket.send_json(prepared_message)
                    
            except WebSocketDisconnect:
                disconnected_clients.append(websocket)
            except Exception as e:
                logger.error(f"Error broadcasting to conversation: {str(e)}")
                disconnected_clients.append(websocket)
        
        # Clean up disconnected clients
        for websocket in disconnected_clients:
            self.disconnect(websocket)
    
    async def subscribe_to_conversation(self, websocket: WebSocket, conversation_id: str):
        """
        Subscribe a client to a specific conversation.
        """
        if websocket in self.connection_info:
            if 'conversations' not in self.connection_info[websocket]:
                self.connection_info[websocket]['conversations'] = []
            
            if conversation_id not in self.connection_info[websocket]['conversations']:
                self.connection_info[websocket]['conversations'].append(conversation_id)
            
            logger.info(f"WebSocket subscribed to conversation {conversation_id}")
    
    def get_connection_count(self) -> int:
        """Get the number of active connections."""
        return len(self.active_connections)
    
    def get_connection_info(self) -> Dict:
        """Get information about all connections."""
        return {
            'total_connections': len(self.active_connections),
            'connections': [
                {
                    'id': info['id'],
                    'connected_at': info['connected_at'],
                    'state': info['state'],
                    'subscribed_conversations': info.get('conversations', [])
                }
                for info in self.connection_info.values()
            ]
        }
    
    async def cleanup_dead_connections(self):
        """
        Clean up dead connections that might have been missed.
        """
        dead_connections = []
        
        for websocket in list(self.active_connections):
            try:
                # Test connection with ping
                await websocket.ping()
            except Exception:
                dead_connections.append(websocket)
        
        for websocket in dead_connections:
            self.disconnect(websocket)
        
        if dead_connections:
            logger.info(f"Cleaned up {len(dead_connections)} dead connections")

# Global connection manager instance
connection_manager = ConnectionManager()
