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
