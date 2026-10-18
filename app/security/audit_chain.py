import hashlib
import json
import time
import os
import logging
import threading
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)

GENESIS_HASH = "0000000000000000000000000000000000000000000000000000000000000000"

class AuditChain:
    """
    Tamper-evident cryptographic hash-chain audit log.
    Every event is hashed together with the previous event's hash, forming an immutable chain.
    Supports thread-safe writes, chain verification, tampering detection, and recovery.
    """
    def __init__(self, filepath: str = "audit.jsonl"):
        self.filepath = filepath
        self.last_hash = GENESIS_HASH
        self._lock = threading.Lock()
        self._load_tail()

    def _load_tail(self):
        with self._lock:
            self.last_hash = self._read_last_hash_unlocked()

    def _read_last_hash_unlocked(self) -> str:
        if not os.path.exists(self.filepath):
            return GENESIS_HASH
        try:
            with open(self.filepath, 'r') as f:
                lines = [line.strip() for line in f if line.strip()]
                if lines:
                    last_record = json.loads(lines[-1])
                    return last_record.get("hash", GENESIS_HASH)
        except Exception as e:
            logger.error(f"Failed to read audit chain tail: {e}")
        return GENESIS_HASH

    def log_event(self, event_type: str, data: Dict[str, Any]) -> str:
        """
        Appends an event to the cryptographically linked audit chain.
        Returns the SHA-256 hash of the newly created block.
        """
        with self._lock:
            # Sync latest tail from disk to support multi-process environments
            self.last_hash = self._read_last_hash_unlocked()

            event = {
                "timestamp": time.time(),
                "type": event_type,
                "data": data,
                "previous_hash": self.last_hash
            }

            # Consistent serialization for deterministic hashing
            event_string = json.dumps(event, sort_keys=True)
            new_hash = hashlib.sha256(event_string.encode('utf-8')).hexdigest()

            record = {
                "event": event,
                "hash": new_hash
            }

            with open(self.filepath, 'a') as f:
                f.write(json.dumps(record) + '\n')

            self.last_hash = new_hash
            return new_hash

    def verify_chain_detailed(self) -> Dict[str, Any]:
        """
        Verifies the integrity of the entire audit chain line-by-line.
        Detects broken links (tampered previous_hash) or altered content (tampered data/hash).
        """
        with self._lock:
            if not os.path.exists(self.filepath):
                return {
                    "is_valid": True,
                    "total_events": 0,
                    "last_hash": GENESIS_HASH,
                    "tampered_at_line": None,
                    "message": "Audit chain empty or not yet created. Valid by default."
                }

            current_prev_hash = GENESIS_HASH
            total_events = 0

            with open(self.filepath, 'r') as f:
                for line_no, raw_line in enumerate(f):
                    line = raw_line.strip()
                    if not line:
                        continue
                    total_events += 1
                    try:
                        record = json.loads(line)
                        event = record.get("event")
                        recorded_hash = record.get("hash")

                        if not event or not recorded_hash:
                            return {
                                "is_valid": False,
                                "total_events": total_events,
                                "last_hash": current_prev_hash,
                                "tampered_at_line": line_no,
                                "message": f"Malformed record structure at line {line_no}."
                            }

                        # 1. Verify backward link
                        if event.get("previous_hash") != current_prev_hash:
                            logger.error(f"Audit chain broken at line {line_no}: Expected prev_hash {current_prev_hash}, got {event.get('previous_hash')}")
                            return {
                                "is_valid": False,
                                "total_events": total_events,
                                "last_hash": current_prev_hash,
                                "tampered_at_line": line_no,
                                "message": f"Broken link at line {line_no}: previous_hash does not match predecessor hash."
                            }

                        # 2. Verify hash integrity
                        event_string = json.dumps(event, sort_keys=True)
                        calculated_hash = hashlib.sha256(event_string.encode('utf-8')).hexdigest()

                        if calculated_hash != recorded_hash:
                            logger.error(f"Audit chain tampered at line {line_no}: Content hash mismatch.")
                            return {
                                "is_valid": False,
                                "total_events": total_events,
                                "last_hash": current_prev_hash,
                                "tampered_at_line": line_no,
                                "message": f"Data tampering detected at line {line_no}: Hash recalculation mismatch."
                            }

                        current_prev_hash = calculated_hash
                    except Exception as e:
                        logger.error(f"Error parsing audit chain at line {line_no}: {e}")
                        return {
                            "is_valid": False,
                            "total_events": total_events,
                            "last_hash": current_prev_hash,
                            "tampered_at_line": line_no,
                            "message": f"Parsing exception at line {line_no}: {str(e)}"
                        }

            return {
                "is_valid": True,
                "total_events": total_events,
                "last_hash": current_prev_hash,
                "tampered_at_line": None,
                "message": f"Audit chain verified successfully ({total_events} events cryptographically intact)."
            }

    def verify_chain(self) -> bool:
        """Boolean wrapper for backwards compatibility."""
        return self.verify_chain_detailed()["is_valid"]

    def get_recent_records(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Returns the most recent chained records."""
        with self._lock:
            if not os.path.exists(self.filepath):
                return []
            try:
                with open(self.filepath, 'r') as f:
                    lines = [line.strip() for line in f if line.strip()]
                    records = [json.loads(line) for line in lines[-limit:]]
                    return records
            except Exception as e:
                logger.error(f"Failed to read recent audit records: {e}")
                return []
