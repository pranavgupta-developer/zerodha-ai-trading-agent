import pytest
import pandas as pd
import numpy as np
from app.trading.quant_engine import QuantEngine

@pytest.fixture
def quant_engine():
    return QuantEngine(risk_free_rate=0.05, trading_days=252)

@pytest.fixture
def sample_prices():
    return pd.Series([100, 101, 102, 99, 105, 110, 108, 112, 115, 111])

@pytest.fixture
def sample_benchmark():
    return pd.Series([1000, 1005, 1010, 990, 1020, 1030, 1025, 1040, 1050, 1045])

def test_calculate_returns(quant_engine, sample_prices):
    returns_df = quant_engine.calculate_returns(sample_prices)
    assert 'daily_returns' in returns_df.columns
    assert 'cumulative_returns' in returns_df.columns
    
    # 100 to 101 is 1% return
    assert np.isclose(returns_df['daily_returns'].iloc[1], 0.01)
    assert np.isclose(returns_df['cumulative_returns'].iloc[1], 0.01)

def test_calculate_volatility(quant_engine, sample_prices):
    returns = quant_engine.calculate_returns(sample_prices)['daily_returns']
    vol = quant_engine.calculate_volatility(returns)
    assert isinstance(vol, float)
    assert vol > 0

def test_calculate_momentum(quant_engine, sample_prices):
    mom = quant_engine.calculate_momentum(sample_prices, period=5)
    # period=5 compares index 9 (111) with index 4 (105)
    # 111 / 105 - 1 = 0.05714...
    assert np.isclose(mom, (111/105) - 1)

def test_calculate_correlation_beta(quant_engine, sample_prices, sample_benchmark):
    asset_returns = quant_engine.calculate_returns(sample_prices)['daily_returns']
    bench_returns = quant_engine.calculate_returns(sample_benchmark)['daily_returns']
    
    corr_cov = quant_engine.calculate_correlation_covariance(asset_returns, bench_returns)
    assert 'correlation' in corr_cov
    assert 'covariance' in corr_cov
    
    beta = quant_engine.calculate_beta(asset_returns, bench_returns)
    assert isinstance(beta, float)

def test_calculate_drawdown(quant_engine, sample_prices):
    cum_returns = quant_engine.calculate_returns(sample_prices)['cumulative_returns']
    dd_stats = quant_engine.calculate_drawdown(cum_returns)
    
    assert 'current_drawdown' in dd_stats
    assert 'max_drawdown' in dd_stats
    assert dd_stats['max_drawdown'] <= 0

def test_calculate_sharpe_sortino(quant_engine, sample_prices):
    returns = quant_engine.calculate_returns(sample_prices)['daily_returns']
    sharpe = quant_engine.calculate_sharpe(returns)
    sortino = quant_engine.calculate_sortino(returns)
    
    assert isinstance(sharpe, float)
    assert isinstance(sortino, float)

def test_build_stock_ranking(quant_engine):
    prices_df = pd.DataFrame({
        'AAPL': [100, 101, 102, 105, 110],
        'MSFT': [200, 198, 195, 190, 185], # negative trend
        'GOOG': [150, 155, 153, 160, 165]
    })
    
    benchmark = pd.Series([1000, 1010, 1005, 1020, 1030])
    
    ranking = quant_engine.build_stock_ranking(prices_df, benchmark)
    
    assert not ranking.empty
    assert len(ranking) == 3
    assert 'composite_score' in ranking.columns
    assert 'beta' in ranking.columns
    
    # AAPL and GOOG should be ranked higher than MSFT
    assert ranking.index[0] in ['AAPL', 'GOOG']
    assert ranking.index[-1] == 'MSFT'

def test_calculate_var_cvar_historical(quant_engine):
    # Simulated daily returns with known tail
    np.random.seed(42)
    returns = pd.Series(np.random.normal(0.001, 0.02, 500))
    res_95 = quant_engine.calculate_var_cvar(returns, confidence=0.95, portfolio_value=100000.0, method="historical")
    
    assert res_95["confidence"] == 0.95
    assert res_95["method"] == "historical"
    assert res_95["var_pct"] > 0
    assert res_95["cvar_pct"] >= res_95["var_pct"]
    assert res_95["var_amount"] == pytest.approx(res_95["var_pct"] * 100000.0, rel=1e-2)
    assert res_95["cvar_amount"] >= res_95["var_amount"]

def test_calculate_var_cvar_parametric(quant_engine):
    np.random.seed(42)
    returns = pd.Series(np.random.normal(0.0005, 0.015, 500))
    res_param = quant_engine.calculate_var_cvar(returns, confidence=0.95, portfolio_value=500000.0, method="parametric")
    
    assert res_param["confidence"] == 0.95
    assert res_param["method"] == "parametric"
    assert res_param["var_pct"] > 0
    assert res_param["cvar_pct"] >= res_param["var_pct"]
    assert res_param["var_amount"] > 0

def test_calculate_var_cvar_empty_or_small(quant_engine):
    empty_series = pd.Series([], dtype=float)
    res = quant_engine.calculate_var_cvar(empty_series)
    assert res["var_pct"] == 0.0
    assert res["cvar_pct"] == 0.0

def test_calculate_portfolio_var_cvar(quant_engine):
    np.random.seed(42)
    dates = pd.date_range('2024-01-01', periods=100)
    returns_df = pd.DataFrame({
        'HDFCBANK': np.random.normal(0.0005, 0.015, 100),
        'TCS': np.random.normal(0.0008, 0.012, 100),
        'RELIANCE': np.random.normal(0.0003, 0.018, 100),
    }, index=dates)
    
    weights = {'HDFCBANK': 0.5, 'TCS': 0.3, 'RELIANCE': 0.2}
    res = quant_engine.calculate_portfolio_var_cvar(weights, returns_df, confidence=0.95, portfolio_value=1000000.0)
    
    assert res["var_pct"] > 0
    assert res["cvar_pct"] >= res["var_pct"]
    assert res["var_amount"] == pytest.approx(res["var_pct"] * 1000000.0, rel=1e-2)

