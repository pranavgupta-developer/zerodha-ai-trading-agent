import pytest
from app.trading.trade_ranker import TradeRanker, RankedTrade
from app.agent.schemas import CandidateTrade
from app.trading.signals import SignalDirection

@pytest.fixture
def ranker():
    return TradeRanker(max_concurrent_selections=2, min_quality_threshold=60.0)

def test_trade_ranker_empty(ranker):
    res = ranker.rank_and_select([], available_margin=100000.0)
    assert res == []

def test_trade_ranker_ranking_and_selection(ranker):
    # Candidate 1: High quality, high expected return
    c1 = CandidateTrade(
        symbol="RELIANCE",
        direction=SignalDirection.BUY,
        qty=10,
        entry_price=2500.0,
        stop_loss=2460.0,
        take_target=2580.0,
        confidence_score=0.9,
        reasoning="Strong breakout",
        quality_score=85.0,
        expected_return_pct=3.2
    )
    # Candidate 2: Moderate quality
    c2 = CandidateTrade(
        symbol="TCS",
        direction=SignalDirection.BUY,
        qty=5,
        entry_price=3500.0,
        stop_loss=3450.0,
        take_target=3600.0,
        confidence_score=0.8,
        reasoning="Moderate momentum",
        quality_score=72.0,
        expected_return_pct=2.8
    )
    # Candidate 3: Sub-threshold quality
    c3 = CandidateTrade(
        symbol="INFY",
        direction=SignalDirection.BUY,
        qty=20,
        entry_price=1500.0,
        stop_loss=1480.0,
        take_target=1520.0,
        confidence_score=0.6,
        reasoning="Weak momentum",
        quality_score=52.0,
        expected_return_pct=1.3
    )

    ranked = ranker.rank_and_select(
        candidates=[c1, c2, c3],
        available_margin=50000.0, # Enough for c1 (25k) and c2 (17.5k), total 42.5k
        volatilities={"RELIANCE": 1.2, "TCS": 1.1, "INFY": 2.0}
    )

    assert len(ranked) == 3
    # Top rank should be RELIANCE
    assert ranked[0].candidate.symbol == "RELIANCE"
    assert ranked[0].selection_verdict == "SELECTED"
    assert ranked[0].rank == 1

    # Second rank should be TCS
    assert ranked[1].candidate.symbol == "TCS"
    assert ranked[1].selection_verdict == "SELECTED"

    # Third rank should be INFY, rejected due to quality
    assert ranked[2].candidate.symbol == "INFY"
    assert ranked[2].selection_verdict == "REJECTED_QUALITY"

def test_trade_ranker_capital_limit(ranker):
    c1 = CandidateTrade(
        symbol="LT",
        direction=SignalDirection.BUY,
        qty=20,
        entry_price=3000.0, # 60k
        stop_loss=2950.0,
        take_target=3100.0,
        confidence_score=0.85,
        reasoning="Bullish",
        quality_score=80.0,
        expected_return_pct=3.3
    )
    # Available margin is only 40k, cannot afford 60k
    ranked = ranker.rank_and_select(candidates=[c1], available_margin=40000.0)
    assert len(ranked) == 1
    assert ranked[0].selection_verdict == "SKIPPED_CAPITAL"
    assert "Insufficient remaining margin" in ranked[0].reasoning
