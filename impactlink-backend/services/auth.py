# backend/services/auth.py
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from firebase_admin import auth

# This tells FastAPI to look for an "Authorization: Bearer <token>" header in the incoming request
security = HTTPBearer()

def verify_token(credentials: HTTPAuthorizationCredentials = Depends(security)) -> str:
    """
    Decodes the Firebase JWT. 
    If valid, returns the user's UID.
    If invalid or missing, throws a 401 Unauthorized error.
    """
    token = credentials.credentials
    try:
        # The Admin SDK verifies the token with Google's servers
        decoded_token = auth.verify_id_token(token)
        
        # Return the Firebase UID so your endpoint knows exactly who is making the request
        return decoded_token["uid"]
    except Exception as e:
        # If the token is expired, fake, or missing, kick them out
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )