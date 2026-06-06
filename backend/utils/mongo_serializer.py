from typing import Any, Dict, List, Union
from bson import ObjectId
from datetime import datetime
import json

def serialize_mongo_doc(doc: Any) -> Any:
    """
    Convert MongoDB document to JSON-serializable format.
    Handles ObjectId, datetime, and nested structures.
    """
    if doc is None:
        return None
    
    if isinstance(doc, ObjectId):
        return str(doc)
    
    if isinstance(doc, datetime):
        return doc.isoformat()
    
    if isinstance(doc, dict):
        return {key: serialize_mongo_doc(value) for key, value in doc.items()}
    
    if isinstance(doc, list):
        return [serialize_mongo_doc(item) for item in doc]
    
    return doc

def serialize_mongo_cursor(cursor) -> List[Dict]:
    """
    Convert MongoDB cursor to JSON-serializable list.
    """
    return [serialize_mongo_doc(doc) for doc in cursor]

def safe_json_dumps(data: Any) -> str:
    """
    Safely convert data to JSON string, handling MongoDB types.
    """
    try:
        return json.dumps(serialize_mongo_doc(data))
    except (TypeError, ValueError) as e:
        # Fallback for complex objects
        return json.dumps(str(data))

def prepare_websocket_message(message: Dict) -> Dict:
    """
    Prepare message for WebSocket transmission.
    Ensures all MongoDB types are serialized.
    """
    return serialize_mongo_doc(message)

def prepare_api_response(data: Any) -> Any:
    """
    Prepare data for API response.
    Ensures all MongoDB types are serialized.
    """
    return serialize_mongo_doc(data)
