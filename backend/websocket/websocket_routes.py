import logging
from fastapi import WebSocket, WebSocketDisconnect, Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from .manager import connection_manager
from models import User
from server import get_current_user, db

logger = logging.getLogger(__name__)
security = HTTPBearer(auto_error=False)

async def get_websocket_user(
    credentials: HTTPAuthorizationCredentials = Depends(security)
) -> User:
    """
    Authenticate WebSocket connection using JWT token from query params or headers.
    """
    try:
        # Try to get token from query params first (common for WebSockets)
        from fastapi import Query
        token = None
        
        # This will be handled in the websocket endpoint itself
        return None
        
    except Exception as e:
        logger.error(f"WebSocket authentication error: {str(e)}")
        raise HTTPException(status_code=401, detail="Authentication failed")

async def websocket_endpoint(websocket: WebSocket, token: str = None):
    """
    Main WebSocket endpoint for real-time communication.
    """
    try:
        # Authenticate the connection
        user = None
        if token:
            try:
                import jwt
                from datetime import datetime, timezone, timedelta
                from server import JWT_SECRET, JWT_ALGORITHM, db
                
                payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
                user_id = payload.get('user_id')
                
                if db and user_id:
                    user_doc = await db.users.find_one({'id': user_id}, {'_id': 0})
                    if user_doc:
                        from server import User
                        user = User(**{k: v for k, v in user_doc.items() if k != 'password'})
                        
            except Exception as e:
                logger.warning(f"WebSocket authentication failed: {str(e)}")
        
        # Connect the WebSocket
        connection_success = await connection_manager.connect(
            websocket, 
            connection_id=user.id if user else None
        )
        
        if not connection_success:
            await websocket.close(code=1011, reason="Connection failed")
            return
        
        logger.info(f"WebSocket connection established for user: {user.email if user else 'anonymous'}")
        
        try:
            # Keep connection alive and handle incoming messages
            while True:
                try:
                    # Receive message from client
                    data = await websocket.receive_json()
                    
                    # Handle different message types
                    message_type = data.get('type')
                    
                    if message_type == 'subscribe_conversation':
                        conversation_id = data.get('conversation_id')
                        if conversation_id:
                            await connection_manager.subscribe_to_conversation(
                                websocket, 
                                conversation_id
                            )
                    
                    elif message_type == 'ping':
                        # Respond to ping with pong
                        await websocket.send_json({'type': 'pong'})
                    
                    elif message_type == 'get_connection_info':
                        info = connection_manager.get_connection_info()
                        await websocket.send_json({
                            'type': 'connection_info',
                            'data': info
                        })
                    
                    else:
                        logger.debug(f"Received WebSocket message: {data}")
                        
                except WebSocketDisconnect:
                    logger.info("WebSocket client disconnected gracefully")
                    break
                    
                except Exception as e:
                    logger.error(f"Error processing WebSocket message: {str(e)}")
                    # Continue processing other messages
                    
        except WebSocketDisconnect:
            logger.info("WebSocket connection closed by client")
            
        except Exception as e:
            logger.error(f"WebSocket connection error: {str(e)}")
            
        finally:
            # Ensure cleanup
            connection_manager.disconnect(websocket)
            
    except WebSocketDisconnect:
        logger.info("WebSocket disconnected during handshake")
        
    except Exception as e:
        logger.error(f"WebSocket endpoint error: {str(e)}")
        try:
            await websocket.close(code=1011, reason="Internal server error")
        except:
            pass

def setup_websocket_routes(app):
    """
    Setup WebSocket routes for the FastAPI app.
    """
    app.websocket("/ws")(websocket_endpoint)
    logger.info("WebSocket routes configured")
