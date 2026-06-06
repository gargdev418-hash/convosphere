import logging
from fastapi import APIRouter, HTTPException, Depends, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from models import (
    User, UserCreate, UserLogin, TokenResponse
)
from server import (
    hash_password, verify_password, create_token, get_current_user, db
)
from utils.mongo_serializer import prepare_api_response

logger = logging.getLogger(__name__)
security = HTTPBearer(auto_error=False)

def setup_auth_routes(api_router: APIRouter):
    """
    Setup authentication routes.
    """
    
    @api_router.post("/auth/register", response_model=TokenResponse)
    async def register(user_data: UserCreate):
        """Register a new user."""
        try:
            if db is None:
                raise HTTPException(status_code=503, detail="Database connection unavailable")
            
            existing = await db.users.find_one({'email': user_data.email}, {'_id': 0})
            if existing:
                raise HTTPException(status_code=400, detail="Email already registered")
            
            user = User(email=user_data.email, name=user_data.name)
            user_doc = user.model_dump()
            user_doc['password'] = hash_password(user_data.password)
            
            await db.users.insert_one(user_doc)
            token = create_token(user.id)
            
            logger.info(f"User registered: {user.email}")
            return prepare_api_response(TokenResponse(token=token, user=user))
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Registration error: {str(e)}")
            raise HTTPException(status_code=500, detail=f"Registration error: {str(e)}")

    @api_router.post("/auth/login", response_model=TokenResponse)
    async def login(credentials: UserLogin):
        """Login user and return JWT token."""
        try:
            if db is None:
                raise HTTPException(status_code=503, detail="Database connection unavailable")
            
            user_doc = await db.users.find_one({'email': credentials.email}, {'_id': 0})
            if not user_doc:
                logger.warning(f"Login attempt - user not found: {credentials.email}")
                raise HTTPException(status_code=401, detail="Invalid credentials")
            
            password_valid = verify_password(credentials.password, user_doc['password'])
            if not password_valid:
                logger.warning(f"Login attempt - invalid password for: {credentials.email}")
                raise HTTPException(status_code=401, detail="Invalid credentials")
            
            # Convert datetime string if needed
            if isinstance(user_doc['created_at'], str):
                pass  # already a string, no conversion needed
            elif isinstance(user_doc['created_at'], datetime):
                user_doc['created_at'] = user_doc['created_at'].isoformat()
            
            # Create user object and token
            user = User(**{k: v for k, v in user_doc.items() if k != 'password'})
            token = create_token(user.id)
            
            logger.info(f"Successful login: {credentials.email}")
            return prepare_api_response(TokenResponse(token=token, user=user))
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Login error for {credentials.email}: {str(e)}")
            raise HTTPException(status_code=500, detail=f"Login error: {str(e)}")

    @api_router.get("/auth/me", response_model=User)
    async def get_me(current_user: User = Depends(get_current_user)):
        """Get current user information."""
        return prepare_api_response(current_user)

    @api_router.post("/auth/logout")
    async def logout(current_user: User = Depends(get_current_user)):
        """Logout endpoint - client should remove token from localStorage."""
        logger.info(f"User logged out: {current_user.email}")
        return {"message": "Logged out successfully"}

    @api_router.get("/auth/debug/users")
    async def debug_users():
        """DEBUG ONLY - List all users in database."""
        try:
            if db is None:
                return {"error": "Database not connected"}
            
            users = await db.users.find({}, {'_id': 0, 'password': 0}).to_list(100)
            return prepare_api_response({
                "users": users, 
                "count": len(users), 
                "total": await db.users.count_documents({})
            })
        except Exception as e:
            return {"error": str(e), "type": type(e).__name__}
    
    logger.info("Auth routes configured")
