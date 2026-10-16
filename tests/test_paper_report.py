import pytest
from app.trading.paper_report import PaperTradingJournal

@pytest.fixture
def journal(tmp_path):
    storage_file = str(tmp_path / "test_paper_journal.json")
    return PaperTradingJournal(initial_capital=500000.0, storage_path=storage_file)

def test_empty_journal_metrics(journal):
    metrics = journal.calculate_metrics()
    assert metrics["active_trading_days"] == 0
    assert metrics["initial_capital"] == 500000.0
    assert metrics["current_capital"] == 500000.0
    assert metrics["total_net_pnl"] == 0.0
    assert metrics["validation_verdict"] == "INSUFFICIENT_DATA"

def test_record_single_day(journal):
    snap = journal.record_daily_snapshot(
        starting_margin=500000.0,
        ending_margin=503500.0,
        realized_pnl=4000.0,
        unrealized_pnl=-500.0,
        total_trades=10,
        win_trades=7,
        loss_trades=3,
        date_str="2026-10-14"
    )

    assert snap.date_str == "2026-10-14"
    assert snap.realized_pnl == 4000.0
    assert snap.net_pnl == 3500.0
    assert snap.win_rate == 70.0
    assert snap.brokerage_fees == 10 * 35.0  # ₹350
    assert snap.net_after_fees == 3500.0 - 350.0

def test_multi_day_validation_verdict_passed(journal):
    # Simulate 3 successful trading days
    journal.record_daily_snapshot(
        starting_margin=500000.0, ending_margin=502000.0, realized_pnl=2500.0,
        total_trades=6, win_trades=4, loss_trades=2, date_str="2026-10-12"
    )
    journal.record_daily_snapshot(
        starting_margin=502000.0, ending_margin=505000.0, realized_pnl=3500.0,
        total_trades=8, win_trades=5, loss_trades=3, date_str="2026-10-13"
    )
    journal.record_daily_snapshot(
        starting_margin=505000.0, ending_margin=508000.0, realized_pnl=3500.0,
        total_trades=6, win_trades=4, loss_trades=2, date_str="2026-10-14"
    )

    metrics = journal.calculate_metrics()
    assert metrics["days_completed"] == 3
    assert metrics["total_net_pnl"] > 0
    assert metrics["max_drawdown_pct"] <= 5.0
    assert metrics["win_rate_overall"] >= 50.0
    assert metrics["validation_verdict"] == "PASSED"

    report_md = journal.generate_markdown_report()
    assert "# 📊 3–7 Day Paper-Trading Validation Report" in report_md
    assert "PASSED" in report_md
    assert "2026-10-12" in report_md
