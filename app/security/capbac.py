from pydantic import BaseModel, Field
from typing import List, Optional, Dict
from datetime import datetime, timedelta, timezone
import uuid
import logging

logger = logging.getLogger(__name__)

class ActionType:
    BUY = "BUY"
    SELL = "SELL"
    CANCEL = "CANCEL"

class Capability(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    agent_id: str
    session_id: str
    action: str  # ActionType
    allowed_symbols: List[str] = ["*"]
    max_value_per_order: float
    max_total_value: float
    expires_at: datetime
    revoked: bool = False
    
    def is_valid(self, symbol: str, action: str, order_value: float) -> bool:
        if self.revoked:
            logger.warning(f"Capability {self.id} is revoked.")
            return False
            
        if datetime.now(timezone.utc) > self.expires_at:
            logger.warning(f"Capability {self.id} is expired.")
            return False
            
        if action != self.action and self.action != "*":
            logger.warning(f"Action {action} not allowed by capability {self.id}.")
            return False
            
        if symbol not in self.allowed_symbols and "*" not in self.allowed_symbols:
            logger.warning(f"Symbol {symbol} not allowed by capability {self.id}.")
            return False
            
        if order_value > self.max_value_per_order:
            logger.warning(f"Order value {order_value} exceeds capability limit {self.max_value_per_order}.")
            return False
            
        return True

class SecurityContext:
    """Manages identities and capability registry."""
    def __init__(self):
        self.capabilities: Dict[str, Capability] = {}
        self.audit_logs = []
        
    def issue_capability(self, agent_id: str, session_id: str, action: str, 
                         allowed_symbols: List[str], max_value: float, 
                         ttl_seconds: int = 3600) -> Capability:
                         
        cap = Capability(
            agent_id=agent_id,
            session_id=session_id,
            action=action,
            allowed_symbols=allowed_symbols,
            max_value_per_order=max_value,
            max_total_value=max_value * 5,
            expires_at=datetime.now(timezone.utc) + timedelta(seconds=ttl_seconds)
        )
        self.capabilities[cap.id] = cap
        logger.info(f"Issued Capability {cap.id} to Agent {agent_id} for {action} on {allowed_symbols}")
        return cap
        
    def revoke_capability(self, cap_id: str):
        if cap_id in self.capabilities:
            self.capabilities[cap_id].revoked = True
            logger.info(f"Revoked capability {cap_id}")
            
    def validate_action(self, cap_id: str, symbol: str, action: str, order_value: float) -> bool:
        """Validates if an action is permitted by a specific capability."""
        if cap_id not in self.capabilities:
            logger.error(f"Capability {cap_id} not found.")
            return False
            
        cap = self.capabilities[cap_id]
        
        # Log to audit
        audit_entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "agent_id": cap.agent_id,
            "session_id": cap.session_id,
            "cap_id": cap_id,
            "symbol": symbol,
            "action": action,
            "order_value": order_value
        }
        
        is_valid = cap.is_valid(symbol, action, order_value)
        audit_entry["status"] = "APPROVED" if is_valid else "DENIED"
        
        self.audit_logs.append(audit_entry)
        
        if not is_valid:
            logger.error(f"SECURITY ALERT: Unauthorized action attempted by Agent {cap.agent_id}. Cap ID: {cap_id}")
            
        return is_valid

    def validate_agent_action(self, agent_id: str, symbol: str, action: str, order_value: float) -> bool:
        """Validates if an action is permitted by ANY capability held by the agent."""
        for cap_id, cap in self.capabilities.items():
            if cap.agent_id == agent_id and cap.is_valid(symbol, action, order_value):
                return True
        logger.error(f"SECURITY ALERT: Unauthorized action attempted by Agent {agent_id}. No valid capabilities found.")
        return False

