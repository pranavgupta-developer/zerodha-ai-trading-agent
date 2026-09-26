import logging
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.broker.kite_adapter import BrokerAdapter
from tests.test_kill_switch import test_daily_loss_kill_switch

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def main():
    request_token = "qCrtQQqnzI2rZ2vti7xTQSkySfqwaYge"
    broker = BrokerAdapter()
    try:
        session = broker.generate_session(request_token)
        access_token = session["access_token"]
        logger.info(f"Successfully obtained access_token.")
        
        original_init = BrokerAdapter.__init__
        def patched_init(self, *args, **kwargs):
            original_init(self, *args, **kwargs)
            self.set_access_token(access_token)
            
        BrokerAdapter.__init__ = patched_init
        
        test_daily_loss_kill_switch()
    except Exception as e:
        logger.error(f"Error: {e}")

if __name__ == "__main__":
    main()
