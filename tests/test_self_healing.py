import pytest
import os
import time
from app.core.self_healing import CircuitBreaker, StaleDataMonitor, PipelineVerifier
from app.security.audit_chain import AuditChain
from app.security.capbac import SecurityContext, Capability, ActionType
from app.agent.schemas import CandidateTrade
from app.trading.signals import SignalDirection
from app.trading.risk_engine import AccountState

def test_audit_chain():
    filepath = "test_audit.jsonl"
    if os.path.exists(filepath):
        os.remove(filepath)
        
    chain = AuditChain(filepath)
    hash1 = chain.log_event("TEST_EVENT", {"key": "value1"})
    hash2 = chain.log_event("TEST_EVENT", {"key": "value2"})
    
    assert chain.verify_chain() == True
    
    # Tamper with the file
    with open(filepath, 'r+') as f:
        content = f.read()
        f.seek(0)
        f.write(content.replace("value1", "value1_tampered"))
        f.truncate()
        
    assert chain.verify_chain() == False
    os.remove(filepath)

def test_circuit_breaker():
    cb = CircuitBreaker(failure_threshold=2, recovery_timeout_sec=1)
    
    assert cb.can_execute() == True
    cb.record_failure()
    assert cb.can_execute() == True
    cb.record_failure() # Hits threshold
    
    assert cb.can_execute() == False # OPEN
    
    time.sleep(1.1)
    
    assert cb.can_execute() == True # HALF-OPEN
    cb.record_success()
    assert cb.can_execute() == True # CLOSED

def test_stale_data_monitor():
    reconnect_triggered = False
    def callback():
        nonlocal reconnect_triggered
        reconnect_triggered = True
        
    monitor = StaleDataMonitor(stale_threshold_sec=0.5, reconnect_callback=callback)
    
    monitor.record_tick()
    assert not monitor.check_staleness()
    
    time.sleep(0.6)
    assert monitor.check_staleness()
    assert reconnect_triggered

def test_pipeline_verifier():
    filepath = "test_verifier_audit.jsonl"
    if os.path.exists(filepath):
        os.remove(filepath)
        
    audit = AuditChain(filepath)
    cb = CircuitBreaker()
    capbac = SecurityContext()
    
    # Add capability for agent
    capbac.issue_capability(
        agent_id="agent_1",
        session_id="session_1",
        action=ActionType.BUY,
        allowed_symbols=["TCS"],
        max_value=5000,
        ttl_seconds=3600
    )
    
    verifier = PipelineVerifier(audit, cb, capbac)
    account = AccountState(available_margin=100000, open_positions={})
    
    # Valid trade
    trade_valid = CandidateTrade(
        symbol="TCS", direction=SignalDirection.BUY, qty=10, entry_price=100,
        stop_loss=90, take_target=110, confidence_score=0.9, reasoning="", approval_required=False
    )
    
    assert verifier.verify_trade(trade_valid, account, "agent_1") == True
    
    # Invalid trade (exceeds capbac max value)
    trade_invalid = CandidateTrade(
        symbol="TCS", direction=SignalDirection.BUY, qty=100, entry_price=100,
        stop_loss=90, take_target=110, confidence_score=0.9, reasoning="", approval_required=False
    )
    
    assert verifier.verify_trade(trade_invalid, account, "agent_1") == False
    
    # Verify audit contains both success and reject
    with open(filepath, 'r') as f:
        lines = f.readlines()
        assert "VERIFY_SUCCESS" in lines[0]
        assert "VERIFY_REJECTED" in lines[1]
        
    os.remove(filepath)
