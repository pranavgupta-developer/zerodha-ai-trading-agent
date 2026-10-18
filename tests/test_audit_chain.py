import pytest
import os
import json
import threading
from app.security.audit_chain import AuditChain, GENESIS_HASH

@pytest.fixture
def chain(tmp_path):
    log_file = str(tmp_path / "test_audit.jsonl")
    return AuditChain(filepath=log_file)

def test_audit_chain_valid_sequence(chain):
    h1 = chain.log_event("ORDER_EVENT", {"symbol": "RELIANCE", "qty": 10, "action": "BUY"})
    h2 = chain.log_event("RISK_DECISION", {"symbol": "RELIANCE", "status": "APPROVED"})
    h3 = chain.log_event("POSITION_EXIT", {"symbol": "RELIANCE", "pnl": 500.0})

    assert h1 != GENESIS_HASH
    assert h2 != h1
    assert h3 != h2
    assert chain.last_hash == h3

    report = chain.verify_chain_detailed()
    assert report["is_valid"] is True
    assert report["total_events"] == 3
    assert report["tampered_at_line"] is None
    assert chain.verify_chain() is True

def test_audit_chain_detects_data_tampering(chain):
    chain.log_event("EVENT_1", {"msg": "Initial 1"})
    chain.log_event("EVENT_2", {"msg": "Initial 2"})
    chain.log_event("EVENT_3", {"msg": "Initial 3"})

    # Tamper with event 2 in the file
    with open(chain.filepath, "r") as f:
        lines = f.readlines()

    record_1 = json.loads(lines[1])
    record_1["event"]["data"]["msg"] = "HACKED_TAMPERED_DATA"
    lines[1] = json.dumps(record_1) + "\n"

    with open(chain.filepath, "w") as f:
        f.writelines(lines)

    report = chain.verify_chain_detailed()
    assert report["is_valid"] is False
    assert report["tampered_at_line"] == 1
    assert "Hash recalculation mismatch" in report["message"]
    assert chain.verify_chain() is False

def test_audit_chain_detects_broken_link(chain):
    chain.log_event("EVENT_1", {"val": 100})
    chain.log_event("EVENT_2", {"val": 200})
    chain.log_event("EVENT_3", {"val": 300})

    # Break previous_hash in event 3
    with open(chain.filepath, "r") as f:
        lines = f.readlines()

    record_2 = json.loads(lines[2])
    record_2["event"]["previous_hash"] = "ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff"
    # recalculate its hash so internal content matches, but link to predecessor is broken
    event_str = json.dumps(record_2["event"], sort_keys=True)
    import hashlib
    record_2["hash"] = hashlib.sha256(event_str.encode("utf-8")).hexdigest()
    lines[2] = json.dumps(record_2) + "\n"

    with open(chain.filepath, "w") as f:
        f.writelines(lines)

    report = chain.verify_chain_detailed()
    assert report["is_valid"] is False
    assert report["tampered_at_line"] == 2
    assert "Broken link" in report["message"]

def test_audit_chain_resumption_after_restart(tmp_path):
    log_file = str(tmp_path / "resume_audit.jsonl")
    chain1 = AuditChain(filepath=log_file)
    chain1.log_event("INIT", {"status": "start"})
    last_h1 = chain1.log_event("TRADE", {"qty": 5})

    # Create new instance (simulating app restart)
    chain2 = AuditChain(filepath=log_file)
    assert chain2.last_hash == last_h1

    last_h2 = chain2.log_event("POST_RESTART", {"status": "resumed"})
    assert last_h2 != last_h1

    report = chain2.verify_chain_detailed()
    assert report["is_valid"] is True
    assert report["total_events"] == 3

def test_audit_chain_concurrency(tmp_path):
    log_file = str(tmp_path / "concurrent_audit.jsonl")
    chain = AuditChain(filepath=log_file)

    def worker(worker_id):
        for i in range(20):
            chain.log_event("CONCURRENT_EVENT", {"worker": worker_id, "step": i})

    threads = [threading.Thread(target=worker, args=(w,)) for w in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    report = chain.verify_chain_detailed()
    assert report["is_valid"] is True
    assert report["total_events"] == 100

def test_audit_chain_get_recent_records(chain):
    for i in range(10):
        chain.log_event("INDEXED_EVENT", {"idx": i})

    records = chain.get_recent_records(limit=3)
    assert len(records) == 3
    assert records[-1]["event"]["data"]["idx"] == 9
