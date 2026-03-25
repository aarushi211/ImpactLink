# backend/services/auth.py
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from firebase_admin import auth
import logging
import time

# Use the standard uvicorn error logger
logger = logging.getLogger("uvicorn.error")

# This tells FastAPI to look for an "Authorization: Bearer <token>" header in the incoming request
security = HTTPBearer()

def verify_token(credentials: HTTPAuthorizationCredentials = Depends(security)) -> str:
    """
    Decodes the Firebase JWT. 
    If valid, returns the user's UID.
    If invalid or missing, throws a 401 Unauthorized error.
    Includes a 1.5s retry for minor clock skew (e.g. Docker vs Host drift).
    """
    token = credentials.credentials
    
    auth_attempts = 0
    max_attempts = 2
    
    while auth_attempts < max_attempts:
        try:
            # The Admin SDK verifies the token with Google's servers
            decoded_token = auth.verify_id_token(token)
            
            # Return the Firebase UID so your endpoint knows exactly who is making the request
            return decoded_token["uid"]
        except Exception as e:
            error_str = str(e)
            # Check for common clock skew error: "Token used too early"
            if "too early" in error_str.lower() and auth_attempts == 0:
                logger.warning("Clock skew detected (Token used too early). Retrying in 1.5s...")
                time.sleep(1.5)
                auth_attempts += 1
                continue
            
            # Log the actual error to help debugging
            logger.warning("Token verification failed: %s", error_str)
            
            # If the token is truly invalid/expired, kick them out
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"Invalid authentication credentials: {error_str}",
                headers={"WWW-Authenticate": "Bearer"},
            )