import hashlib
import json
import time
import os
import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)

class AuditChain:
    """
    Tamper-evident hash-chain audit log.
    Every event is hashed together with the previous event's hash, forming an immutable chain.
    """
    def __init__(self, filepath: str = "audit.jsonl"):
        self.filepath = filepath
        self.last_hash = "0000000000000000000000000000000000000000000000000000000000000000"
        self._load_tail()
        
    def _load_tail(self):
        if not os.path.exists(self.filepath):
            return
        # Find the last hash to resume chain
        try:
            with open(self.filepath, 'r') as f:
                lines = f.readlines()
                if lines:
                    last_record = json.loads(lines[-1].strip())
                    self.last_hash = last_record["hash"]
        except Exception as e:
            logger.error(f"Failed to load audit chain tail: {e}")

    def log_event(self, event_type: str, data: Dict[str, Any]) -> str:
        event = {
            "timestamp": time.time(),
            "type": event_type,
            "data": data,
            "previous_hash": self.last_hash
        }
        
        # Consistent serialization for hashing
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

    def verify_chain(self) -> bool:
        """Verifies the integrity of the entire audit chain."""
        if not os.path.exists(self.filepath):
            return True
            
        current_prev_hash = "0000000000000000000000000000000000000000000000000000000000000000"
        
        with open(self.filepath, 'r') as f:
            for line_no, line in enumerate(f):
                try:
                    record = json.loads(line.strip())
                    event = record["event"]
                    recorded_hash = record["hash"]
                    
                    if event["previous_hash"] != current_prev_hash:
                        logger.error(f"Audit chain broken at line {line_no}: Invalid previous_hash.")
                        return False
                        
                    event_string = json.dumps(event, sort_keys=True)
                    calculated_hash = hashlib.sha256(event_string.encode('utf-8')).hexdigest()
                    
                    if calculated_hash != recorded_hash:
                        logger.error(f"Audit chain tampered at line {line_no}: Hash mismatch.")
                        return False
                        
                    current_prev_hash = calculated_hash
                except Exception as e:
                    logger.error(f"Error parsing audit chain at line {line_no}: {e}")
                    return False
                    
        logger.info("Audit chain integrity verified successfully.")
        return True
