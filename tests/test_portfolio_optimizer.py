import pytest
import numpy as np
import pandas as pd
from app.trading.portfolio_optimizer import PortfolioOptimizer

def test_portfolio_optimizer():
    # Setup some fake price data for 3 assets
    np.random.seed(42)
    dates = pd.date_range('2023-01-01', periods=200)
    
    # Asset A: High return, high vol
    ret_a = np.random.normal(0.001, 0.02, 200)
    # Asset B: Low return, low vol
    ret_b = np.random.normal(0.0002, 0.005, 200)
    # Asset C: Negative return
    ret_c = np.random.normal(-0.001, 0.015, 200)
    
    price_a = 100 * np.exp(np.cumsum(ret_a))
    price_b = 50 * np.exp(np.cumsum(ret_b))
    price_c = 200 * np.exp(np.cumsum(ret_c))
    
    prices_df = pd.DataFrame({
        'A': price_a,
        'B': price_b,
        'C': price_c
    }, index=dates)
    
    optimizer = PortfolioOptimizer(
        max_position_weight=0.4,
        max_portfolio_exposure=1.0,
        transaction_cost_rate=0.001
    )
    
    current_weights = {'A': 0.1, 'B': 0.8, 'C': 0.1}
    
    target_alloc = optimizer.optimize(current_weights, prices_df)
    
    # Check constraints
    assert sum(target_alloc.values()) <= 1.0001 # slight float tolerance
    for sym, weight in target_alloc.items():
        assert weight <= 0.4001
        assert weight >= 0.0
        
    # Asset C should have 0 weight ideally because of negative return
    assert target_alloc['C'] < 0.01

def test_empty_dataframe():
    optimizer = PortfolioOptimizer()
    df = pd.DataFrame()
    target = optimizer.optimize({'A': 0.5}, df)
    assert target == {}

def test_calculate_expected_returns():
    optimizer = PortfolioOptimizer()
    ret_df = pd.DataFrame({
        'A': [0.01, 0.01, 0.01],
        'B': [-0.01, -0.01, -0.01]
    })
    expected = optimizer.calculate_expected_returns(ret_df)
    assert expected['A'] == pytest.approx(0.01 * 252)
    assert expected['B'] == pytest.approx(-0.01 * 252)

def test_portfolio_optimizer_sector_constraints():
    np.random.seed(42)
    dates = pd.date_range('2023-01-01', periods=150)
    
    # Both A and B have positive returns and are in the same sector 'TECH'
    ret_a = np.random.normal(0.002, 0.01, 150)
    ret_b = np.random.normal(0.002, 0.01, 150)
    # C is in 'FIN'
    ret_c = np.random.normal(0.001, 0.01, 150)
    
    prices_df = pd.DataFrame({
        'A': 100 * np.exp(np.cumsum(ret_a)),
        'B': 100 * np.exp(np.cumsum(ret_b)),
        'C': 100 * np.exp(np.cumsum(ret_c))
    }, index=dates)
    
    sector_map = {'A': 'TECH', 'B': 'TECH', 'C': 'FIN'}
    
    # Max sector weight = 0.30
    optimizer = PortfolioOptimizer(
        max_position_weight=0.5,
        max_portfolio_exposure=1.0,
        max_sector_weight=0.30,
        sector_mapping=sector_map
    )
    
    current_weights = {'A': 0.1, 'B': 0.1, 'C': 0.1}
    target = optimizer.optimize(current_weights, prices_df)
    
    # The sum of weights for TECH (A + B) must be <= 0.3005
    tech_sum = target['A'] + target['B']
    assert tech_sum <= 0.3005

