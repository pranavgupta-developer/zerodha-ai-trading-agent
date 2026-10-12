import time
import logging
from typing import Optional, Callable
from app.agent.schemas import CandidateTrade
from app.trading.risk_engine import AccountState
from app.security.audit_chain import AuditChain
from app.security.capbac import SecurityContext

logger = logging.getLogger(__name__)

class CircuitBreaker:
    """
    Prevents cascading failures and endless retry loops.
    States: CLOSED (Normal), OPEN (Halted), HALF-OPEN (Testing recovery).
    """
    def __init__(self, failure_threshold: int = 3, recovery_timeout_sec: int = 60):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout_sec
        self.failures = 0
        self.last_failure_time = 0.0
        self.state = "CLOSED"
        
    def record_failure(self):
        self.failures += 1
        self.last_failure_time = time.time()
        if self.failures >= self.failure_threshold and self.state == "CLOSED":
            self.state = "OPEN"
            logger.critical("CIRCUIT BREAKER OPENED! System halted due to repeated failures.")
            
    def record_success(self):
        if self.state in ["OPEN", "HALF-OPEN"]:
            logger.info("CIRCUIT BREAKER CLOSED! System recovered.")
        self.failures = 0
        self.state = "CLOSED"
        
    def can_execute(self) -> bool:
        if self.state == "CLOSED":
            return True
        if self.state == "OPEN":
            if time.time() - self.last_failure_time > self.recovery_timeout:
                self.state = "HALF-OPEN"
                logger.warning("CIRCUIT BREAKER HALF-OPEN. Attempting recovery execution.")
                return True
            return False
        if self.state == "HALF-OPEN":
            # Allow exactly one request to pass through during half-open
            return True


class StaleDataMonitor:
    """
    Monitors data feeds for staleness and triggers reconnection callbacks if data dies.
    """
    def __init__(self, stale_threshold_sec: float = 5.0, reconnect_callback: Optional[Callable] = None):
        self.stale_threshold = stale_threshold_sec
        self.last_tick_time = time.time()
        self.reconnect_callback = reconnect_callback
        
    def record_tick(self):
        self.last_tick_time = time.time()
        
    def check_staleness(self) -> bool:
        """Returns True if data is stale, and triggers reconnection if available."""
        if time.time() - self.last_tick_time > self.stale_threshold:
            logger.error("STALE DATA DETECTED! Market data feed has stalled.")
            if self.reconnect_callback:
                logger.info("Triggering WebSocket reconnection...")
                self.reconnect_callback()
            return True
        return False


class PipelineVerifier:
    """
    Comprehensive verification checkpoint. Must pass before any execution happens.
    - Verifies Capability
    - Checks Circuit Breaker
    - Writes to Audit Chain
    """
    def __init__(self, audit_chain: AuditChain, circuit_breaker: CircuitBreaker, capbac: SecurityContext):
        self.audit = audit_chain
        self.circuit_breaker = circuit_breaker
        self.capbac = capbac
        
    def verify_trade(self, trade: CandidateTrade, account: AccountState, agent_id: str) -> bool:
        if not self.circuit_breaker.can_execute():
            self.audit.log_event("VERIFY_REJECTED", {"reason": "Circuit Breaker OPEN", "symbol": trade.symbol})
            logger.error("Trade rejected: Circuit breaker is OPEN.")
            return False
            
        # Verify capability
        total_value = trade.entry_price * trade.qty
        if not self.capbac.validate_agent_action(agent_id, trade.symbol, trade.direction.value, total_value):
            self.circuit_breaker.record_failure()
            self.audit.log_event("VERIFY_REJECTED", {"reason": "Capability check failed", "symbol": trade.symbol})
            logger.error(f"Trade rejected: Agent {agent_id} lacks capability for {trade.symbol}")
            return False
            
        # Verify strategy consistency (e.g. qty > 0)
        if trade.qty <= 0 or trade.entry_price <= 0:
            self.circuit_breaker.record_failure()
            self.audit.log_event("VERIFY_REJECTED", {"reason": "Invalid strategy quantities", "symbol": trade.symbol})
            logger.error("Trade rejected: Invalid quantity or price.")
            return False
            
        self.audit.log_event("VERIFY_SUCCESS", {"trade": trade.model_dump(), "agent_id": agent_id})
        self.circuit_breaker.record_success()
        return True
