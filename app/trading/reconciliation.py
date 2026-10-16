import time
import logging
from enum import Enum
from typing import Dict, List, Optional, Any, Tuple
from pydantic import BaseModel, Field

from app.broker.kite_adapter import BrokerAdapter
from app.trading.position_manager import PositionManager
from app.trading.order_manager import OrderManager, OrderState

logger = logging.getLogger(__name__)

class DiscrepancyType(str, Enum):
    QUANTITY_MISMATCH = "QUANTITY_MISMATCH"
    STATUS_MISMATCH = "STATUS_MISMATCH"
    PRICE_MISMATCH = "PRICE_MISMATCH"
    GHOST_POSITION = "GHOST_POSITION"        # Present in broker, missing locally
    MISSING_POSITION = "MISSING_POSITION"    # Present locally, missing in broker
    ORPHAN_ORDER = "ORPHAN_ORDER"            # Order at broker but not locally tracked
    UNCONFIRMED_ORDER = "UNCONFIRMED_ORDER"  # Order placed locally but absent in broker

class Discrepancy(BaseModel):
    symbol: str
    discrepancy_type: DiscrepancyType
    severity: str = "WARNING"  # CRITICAL, WARNING, INFO
    local_value: Any
    broker_value: Any
    details: str

class QuarantinedPayload(BaseModel):
    source: str
    raw_payload: Any
    reason: str
    timestamp: float = Field(default_factory=time.time)

class ReconciliationReport(BaseModel):
    timestamp: float = Field(default_factory=time.time)
    is_synced: bool
    total_discrepancies: int
    critical_count: int
    discrepancies: List[Discrepancy]
    quarantined_count: int
    auto_resolved: bool = False

class ReconciliationEngine:
    """
    Independent Trade Verification and Reconciliation Engine.
    Continuously audits local state against Zerodha broker positions and order book,
    quarantines malformed broker API payloads, and flags any discrepancy.
    """
    def __init__(
        self,
        broker: BrokerAdapter,
        position_manager: PositionManager,
        order_manager: OrderManager
    ):
        self.broker = broker
        self.position_manager = position_manager
        self.order_manager = order_manager
        self.latest_report: Optional[ReconciliationReport] = None
        self.quarantined_payloads: List[QuarantinedPayload] = []

    def validate_position_schema(self, pos: Any) -> Tuple[bool, Optional[str]]:
        """Validates that a position payload contains mandatory fields with valid types."""
        if not isinstance(pos, dict):
            return False, f"Expected dict, got {type(pos).__name__}"
        if "tradingsymbol" not in pos or not isinstance(pos["tradingsymbol"], str) or not pos["tradingsymbol"].strip():
            return False, "Missing or invalid 'tradingsymbol'"
        if "quantity" not in pos:
            return False, "Missing 'quantity' field"
        try:
            int(pos["quantity"])
        except (ValueError, TypeError):
            return False, f"Invalid 'quantity' type: {pos['quantity']}"
        return True, None

    def validate_order_schema(self, order: Any) -> Tuple[bool, Optional[str]]:
        """Validates that an order payload contains mandatory fields with valid types."""
        if not isinstance(order, dict):
            return False, f"Expected dict, got {type(order).__name__}"
        if "order_id" not in order or not order["order_id"]:
            return False, "Missing 'order_id'"
        if "status" not in order or not isinstance(order["status"], str):
            return False, "Missing or invalid 'status'"
        return True, None

    def quarantine(self, source: str, raw_payload: Any, reason: str):
        """Quarantines malformed responses to prevent corrupting local state."""
        q = QuarantinedPayload(source=source, raw_payload=raw_payload, reason=reason)
        self.quarantined_payloads.append(q)
        if len(self.quarantined_payloads) > 100:
            self.quarantined_payloads.pop(0)
        logger.error(f"[QUARANTINE] Quarantined malformed {source} payload: {reason}. Payload: {raw_payload}")

    def reconcile_positions(self) -> Tuple[List[Discrepancy], List[Dict[str, Any]]]:
        """
        Compares local active tracked positions with live broker net positions.
        Returns detected discrepancies and valid broker positions.
        """
        discrepancies: List[Discrepancy] = []
        valid_broker_positions: List[Dict[str, Any]] = []

        try:
            pos_data = self.broker.get_positions()
            raw_net = pos_data.get("net", []) if isinstance(pos_data, dict) else []
        except Exception as e:
            logger.error(f"Failed to fetch broker positions for reconciliation: {e}")
            discrepancies.append(Discrepancy(
                symbol="ALL",
                discrepancy_type=DiscrepancyType.STATUS_MISMATCH,
                severity="CRITICAL",
                local_value="OK",
                broker_value="API_ERROR",
                details=f"Broker positions API call failed: {e}"
            ))
            return discrepancies, valid_broker_positions

        broker_position_map: Dict[str, Dict[str, Any]] = {}
        for p in raw_net:
            is_valid, err = self.validate_position_schema(p)
            if not is_valid:
                self.quarantine("positions", p, err or "Schema validation failed")
                continue

            clean_sym = str(p["tradingsymbol"]).replace(".NS", "").strip()
            qty = abs(int(p["quantity"]))
            if qty > 0:
                broker_position_map[clean_sym] = p
                valid_broker_positions.append(p)

        local_positions = self.position_manager.get_all_tracked()

        # 1. Check local positions against broker
        for sym, local_pos in local_positions.items():
            clean_sym = sym.replace(".NS", "").strip()
            if clean_sym not in broker_position_map:
                discrepancies.append(Discrepancy(
                    symbol=clean_sym,
                    discrepancy_type=DiscrepancyType.MISSING_POSITION,
                    severity="CRITICAL",
                    local_value=local_pos.quantity,
                    broker_value=0,
                    details=f"Local position {clean_sym} (qty: {local_pos.quantity}) not found in broker open positions."
                ))
            else:
                broker_p = broker_position_map[clean_sym]
                broker_qty = abs(int(broker_p["quantity"]))
                if local_pos.quantity != broker_qty:
                    discrepancies.append(Discrepancy(
                        symbol=clean_sym,
                        discrepancy_type=DiscrepancyType.QUANTITY_MISMATCH,
                        severity="CRITICAL",
                        local_value=local_pos.quantity,
                        broker_value=broker_qty,
                        details=f"Quantity mismatch for {clean_sym}: local has {local_pos.quantity}, broker has {broker_qty}."
                    ))

        # 2. Check for ghost positions (present at broker, not tracked locally)
        for clean_sym, broker_p in broker_position_map.items():
            if clean_sym not in local_positions:
                broker_qty = abs(int(broker_p["quantity"]))
                discrepancies.append(Discrepancy(
                    symbol=clean_sym,
                    discrepancy_type=DiscrepancyType.GHOST_POSITION,
                    severity="CRITICAL",
                    local_value=0,
                    broker_value=broker_qty,
                    details=f"Ghost position detected: Broker holds {broker_qty} of {clean_sym}, but local position manager is not tracking it."
                ))

        return discrepancies, valid_broker_positions

    def reconcile_orders(self) -> List[Discrepancy]:
        """
        Compares local managed order cache with broker order book.
        """
        discrepancies: List[Discrepancy] = []

        try:
            broker_orders = self.broker.get_orders()
            if not isinstance(broker_orders, list):
                broker_orders = []
        except Exception as e:
            logger.error(f"Failed to fetch broker orders for reconciliation: {e}")
            discrepancies.append(Discrepancy(
                symbol="ALL",
                discrepancy_type=DiscrepancyType.STATUS_MISMATCH,
                severity="WARNING",
                local_value="OK",
                broker_value="API_ERROR",
                details=f"Broker orders API call failed: {e}"
            ))
            return discrepancies

        broker_order_map: Dict[str, Dict[str, Any]] = {}
        for o in broker_orders:
            is_valid, err = self.validate_order_schema(o)
            if not is_valid:
                self.quarantine("orders", o, err or "Schema validation failed")
                continue
            oid = str(o["order_id"])
            broker_order_map[oid] = o

        local_orders = self.order_manager._order_cache

        # Check local orders against broker
        for ikey, local_order in local_orders.items():
            b_id = local_order.broker_order_id
            if not b_id:
                continue

            if b_id not in broker_order_map:
                # If order was created/submitted locally, it should exist in broker order book
                if local_order.state in (OrderState.SUBMITTED, OrderState.OPEN, OrderState.PARTIALLY_FILLED):
                    discrepancies.append(Discrepancy(
                        symbol=local_order.symbol,
                        discrepancy_type=DiscrepancyType.UNCONFIRMED_ORDER,
                        severity="WARNING",
                        local_value=local_order.state.value,
                        broker_value="NOT_FOUND",
                        details=f"Local active order {b_id} ({local_order.symbol}) missing from broker order book."
                    ))
            else:
                b_order = broker_order_map[b_id]
                b_status = str(b_order.get("status", "")).upper()
                
                # Check status alignment
                if b_status == "COMPLETE" and local_order.state not in (OrderState.COMPLETE, OrderState.SUBMITTED):
                    discrepancies.append(Discrepancy(
                        symbol=local_order.symbol,
                        discrepancy_type=DiscrepancyType.STATUS_MISMATCH,
                        severity="WARNING",
                        local_value=local_order.state.value,
                        broker_value=b_status,
                        details=f"Order {b_id} status mismatch: local={local_order.state.value}, broker={b_status}"
                    ))
                elif b_status == "REJECTED" and local_order.state != OrderState.REJECTED:
                    discrepancies.append(Discrepancy(
                        symbol=local_order.symbol,
                        discrepancy_type=DiscrepancyType.STATUS_MISMATCH,
                        severity="WARNING",
                        local_value=local_order.state.value,
                        broker_value=b_status,
                        details=f"Order {b_id} rejected at broker, but local state is {local_order.state.value}"
                    ))

        return discrepancies

    def run_reconciliation(self, auto_sync: bool = True) -> ReconciliationReport:
        """
        Executes a complete reconciliation run across positions and orders.
        Optionally synchronizes local position envelopes if ghost or mismatched positions exist.
        """
        logger.info("[RECONCILIATION] Starting independent trade and position audit...")
        pos_discrepancies, valid_broker_positions = self.reconcile_positions()
        order_discrepancies = self.reconcile_orders()

        all_discrepancies = pos_discrepancies + order_discrepancies
        critical_count = sum(1 for d in all_discrepancies if d.severity == "CRITICAL")
        is_synced = len(all_discrepancies) == 0

        auto_resolved = False
        if auto_sync and not is_synced and valid_broker_positions:
            logger.info("[RECONCILIATION] Auto-syncing local position envelopes with broker positions.")
            self.position_manager.sync_with_broker_positions(valid_broker_positions)
            auto_resolved = True

        report = ReconciliationReport(
            timestamp=time.time(),
            is_synced=is_synced,
            total_discrepancies=len(all_discrepancies),
            critical_count=critical_count,
            discrepancies=all_discrepancies,
            quarantined_count=len(self.quarantined_payloads),
            auto_resolved=auto_resolved
        )
        self.latest_report = report

        if not is_synced:
            logger.warning(
                f"[RECONCILIATION MISMATCH] Found {len(all_discrepancies)} discrepancies "
                f"({critical_count} critical, {len(self.quarantined_payloads)} quarantined)."
            )
        else:
            logger.info("[RECONCILIATION OK] Local state perfectly synchronized with broker state.")

        return report
