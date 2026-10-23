import logging
from typing import Optional
from fastapi import APIRouter, HTTPException
from fastapi.responses import RedirectResponse
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Authentication"])


class TokenSubmissionPayload(BaseModel):
    access_token: str


@router.get("/api/v1/auth/login")
def login(redirect: bool = False):
    """
    Returns Zerodha Kite login URL or redirects user to broker login.
    """
    from app.main import broker
    try:
        url = broker.get_login_url()
        if redirect:
            return RedirectResponse(url=url)
        return {"login_url": url}
    except Exception as e:
        logger.error(f"Failed to generate login URL: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/v1/auth/token")
def set_auth_token(payload: TokenSubmissionPayload):
    """
    Directly sets Kite Connect access token and initializes ticker.
    """
    from app.main import broker, log_audit_event, start_ticker, notify_state_changed
    token = payload.access_token.strip()
    if not token:
        raise HTTPException(status_code=400, detail="Access token cannot be empty")
        
    try:
        broker.set_access_token(token)
        broker._is_auth_cached = True
        log_audit_event("AUTH_EVENT", "token_set", "SYSTEM", "SUCCESS", "Zerodha access token set manually")
        start_ticker()
        notify_state_changed()
        return {
            "status": "success",
            "message": "Zerodha access token updated successfully",
            "authenticated": broker.is_authenticated()
        }
    except Exception as e:
        logger.error(f"Failed to set access token: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/v1/auth/callback")
def auth_callback(
    request_token: str,
    action: Optional[str] = None,
    type: Optional[str] = None,
    status: Optional[str] = None
):
    """
    OAuth callback from Zerodha Kite after successful user login.
    """
    from app.main import broker, log_audit_event, start_ticker, notify_state_changed
    if status == "cancelled":
        log_audit_event("AUTH_EVENT", "auth_cancel", "SYSTEM", "CANCEL", "User cancelled Zerodha login")
        return RedirectResponse(url="/?auth=cancelled")
        
    try:
        session = broker.generate_session(request_token=request_token)
        log_audit_event("AUTH_EVENT", "auth_success", "SYSTEM", "SUCCESS", f"Zerodha session established: {session.get('user_id', 'unknown')}")
        start_ticker()
        notify_state_changed()
        return RedirectResponse(url="/?auth=success")
    except Exception as e:
        logger.error(f"Authentication callback failed: {e}")
        log_audit_event("AUTH_EVENT", "auth_fail", "SYSTEM", "FAILED", str(e))
        return RedirectResponse(url=f"/?auth=error&msg={str(e)}")


@router.get("/api/auth/kite/callback")
def kite_auth_callback(
    request_token: str,
    action: Optional[str] = None,
    type: Optional[str] = None,
    status: Optional[str] = None
):
    """Legacy route alias for Zerodha OAuth callback."""
    return auth_callback(request_token=request_token, action=action, type=type, status=status)
