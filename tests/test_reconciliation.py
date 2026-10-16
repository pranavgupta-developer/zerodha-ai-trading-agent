import pytest
from app.broker.kite_adapter import BrokerAdapter
from app.trading.position_manager import PositionManager
from app.trading.order_manager import OrderManager, ManagedOrder, OrderState
from app.trading.signals import SignalDirection
from app.trading.reconciliation import ReconciliationEngine, DiscrepancyType

class MockBroker(BrokerAdapter):
    def __init__(self):
        self.mock_positions = {"net": []}
        self.mock_orders = []

    def get_positions(self):
        return self.mock_positions

    def get_orders(self):
        return self.mock_orders

def test_reconciliation_synced():
    broker = MockBroker()
    pm = PositionManager(broker=broker)
    om = OrderManager(broker=broker)
    engine = ReconciliationEngine(broker, pm, om)

    # Empty states match
    report = engine.run_reconciliation()
    assert report.is_synced is True
    assert report.total_discrepancies == 0
    assert report.critical_count == 0

def test_reconciliation_quantity_mismatch():
    broker = MockBroker()
    pm = PositionManager(broker=broker)
    om = OrderManager(broker=broker)
    engine = ReconciliationEngine(broker, pm, om)

    # Local tracks 10 shares of RELIANCE
    pm.register_position("RELIANCE", SignalDirection.BUY, 10, 2500.0, 2450.0, 2600.0)

    # Broker has 25 shares
    broker.mock_positions = {
        "net": [{"tradingsymbol": "RELIANCE", "quantity": 25, "average_price": 2500.0}]
    }

    report = engine.run_reconciliation(auto_sync=False)
    assert report.is_synced is False
    assert report.total_discrepancies == 1
    assert report.discrepancies[0].discrepancy_type == DiscrepancyType.QUANTITY_MISMATCH
    assert report.discrepancies[0].local_value == 10
    assert report.discrepancies[0].broker_value == 25

def test_reconciliation_ghost_position():
    broker = MockBroker()
    pm = PositionManager(broker=broker)
    om = OrderManager(broker=broker)
    engine = ReconciliationEngine(broker, pm, om)

    # Local has 0 positions, broker holds TATASTEEL
    broker.mock_positions = {
        "net": [{"tradingsymbol": "TATASTEEL", "quantity": 100, "average_price": 150.0}]
    }

    report = engine.run_reconciliation(auto_sync=False)
    assert report.is_synced is False
    assert any(d.discrepancy_type == DiscrepancyType.GHOST_POSITION for d in report.discrepancies)

def test_reconciliation_missing_position():
    broker = MockBroker()
    pm = PositionManager(broker=broker)
    om = OrderManager(broker=broker)
    engine = ReconciliationEngine(broker, pm, om)

    # Local thinks it holds INFY, but broker has none
    pm.register_position("INFY", SignalDirection.BUY, 50, 1500.0, 1450.0, 1600.0)
    broker.mock_positions = {"net": []}

    report = engine.run_reconciliation(auto_sync=False)
    assert report.is_synced is False
    assert any(d.discrepancy_type == DiscrepancyType.MISSING_POSITION for d in report.discrepancies)

def test_reconciliation_malformed_payload_quarantine():
    broker = MockBroker()
    pm = PositionManager(broker=broker)
    om = OrderManager(broker=broker)
    engine = ReconciliationEngine(broker, pm, om)

    # Bad payload: missing tradingsymbol, non-numeric quantity
    broker.mock_positions = {
        "net": [
            {"corrupt_key": 123},
            {"tradingsymbol": "", "quantity": "invalid_number"}
        ]
    }

    report = engine.run_reconciliation(auto_sync=False)
    assert len(engine.quarantined_payloads) == 2
    assert report.quarantined_count == 2

def test_reconciliation_order_status_mismatch():
    broker = MockBroker()
    pm = PositionManager(broker=broker)
    om = OrderManager(broker=broker)
    engine = ReconciliationEngine(broker, pm, om)

    # Local order is in OPEN state
    order = ManagedOrder(
        idempotency_key="key_1",
        symbol="TCS",
        direction=SignalDirection.BUY,
        qty=10,
        price=3500.0,
        state=OrderState.OPEN,
        broker_order_id="broker_order_999"
    )
    om._order_cache["key_1"] = order

    # Broker says order was REJECTED
    broker.mock_orders = [
        {"order_id": "broker_order_999", "status": "REJECTED", "tradingsymbol": "TCS"}
    ]

    report = engine.run_reconciliation(auto_sync=False)
    assert report.is_synced is False
    assert any(d.discrepancy_type == DiscrepancyType.STATUS_MISMATCH for d in report.discrepancies)

def test_reconciliation_auto_sync():
    broker = MockBroker()
    pm = PositionManager(broker=broker)
    om = OrderManager(broker=broker)
    engine = ReconciliationEngine(broker, pm, om)

    # Broker has 100 TATASTEEL
    broker.mock_positions = {
        "net": [{"tradingsymbol": "TATASTEEL", "quantity": 100, "average_price": 150.0}]
    }

    report = engine.run_reconciliation(auto_sync=True)
    assert report.auto_resolved is True
    # Now local manager should have synced TATASTEEL
    tracked = pm.get_tracked_position("TATASTEEL")
    assert tracked is not None
    assert tracked.quantity == 100
