import numpy as np
import pandas as pd
from typing import Dict, List, Optional
from scipy.optimize import minimize
import logging

logger = logging.getLogger(__name__)

class PortfolioOptimizer:
    def __init__(
        self,
        risk_free_rate: float = 0.05,
        max_position_weight: float = 0.25,
        max_portfolio_exposure: float = 1.0,
        transaction_cost_rate: float = 0.001,
        max_sector_weight: float = 0.35,
        sector_mapping: Optional[Dict[str, str]] = None
    ):
        """
        Markowitz Portfolio Optimizer with Position and Sector Concentration Constraints.
        """
        self.risk_free_rate = risk_free_rate
        self.max_position_weight = max_position_weight
        self.max_portfolio_exposure = max_portfolio_exposure
        self.transaction_cost_rate = transaction_cost_rate
        self.max_sector_weight = max_sector_weight
        self.sector_mapping = sector_mapping or {}

    def calculate_expected_returns(self, returns_df: pd.DataFrame) -> pd.Series:
        """
        Calculates annualized expected returns from daily returns.
        """
        # Assuming 252 trading days
        return returns_df.mean() * 252

    def build_covariance_matrix(self, returns_df: pd.DataFrame) -> pd.DataFrame:
        """
        Builds annualized covariance matrix.
        """
        return returns_df.cov() * 252

    def optimize(
        self,
        current_weights: Dict[str, float],
        prices_df: pd.DataFrame,
        sector_mapping: Optional[Dict[str, str]] = None,
        max_sector_weight: Optional[float] = None
    ) -> Dict[str, float]:
        """
        Optimizes portfolio weights using Markowitz Mean-Variance Optimization.
        
        Prices_df should be a DataFrame where columns are asset symbols and values are daily prices.
        current_weights: Dictionary of {symbol: weight} representing the current portfolio.
        sector_mapping: Optional mapping of symbol -> sector name.
        max_sector_weight: Optional override for max allowable allocation per sector.
        """
        # Ensure symbols align
        symbols = list(prices_df.columns)
        returns_df = prices_df.pct_change().dropna()
        
        if returns_df.empty:
            logger.warning("Empty returns dataframe. Cannot optimize.")
            return {sym: 0.0 for sym in symbols}
            
        expected_returns = self.calculate_expected_returns(returns_df).values
        cov_matrix = self.build_covariance_matrix(returns_df).values
        
        num_assets = len(symbols)
        
        # Prepare current weights array aligned with symbols
        curr_w = np.array([current_weights.get(sym, 0.0) for sym in symbols])
        
        def objective(weights):
            # We want to maximize Sharpe Ratio -> Minimize negative Sharpe Ratio
            # We also penalize for transaction costs
            
            port_return = np.dot(weights, expected_returns)
            port_vol = np.sqrt(np.dot(weights.T, np.dot(cov_matrix, weights)))
            
            if port_vol == 0:
                return 0
                
            sharpe_ratio = (port_return - self.risk_free_rate) / port_vol
            
            # Transaction cost penalty
            turnover = np.sum(np.abs(weights - curr_w))
            total_tc = turnover * self.transaction_cost_rate
            
            # Objective: Maximize (Sharpe - TC penalty)
            return -(sharpe_ratio - total_tc)
            
        # Constraints
        # 1. Sum of weights <= max_portfolio_exposure (fully invested if == exposure)
        # We allow cash, so sum of weights <= max_portfolio_exposure
        constraints = [
            {'type': 'ineq', 'fun': lambda w: self.max_portfolio_exposure - np.sum(w)}
        ]
        
        # 2. Sector concentration constraints
        active_sector_map = sector_mapping or self.sector_mapping
        effective_max_sector = max_sector_weight if max_sector_weight is not None else self.max_sector_weight
        if active_sector_map and effective_max_sector > 0:
            sectors: Dict[str, List[int]] = {}
            for i, sym in enumerate(symbols):
                sec = active_sector_map.get(sym)
                if sec:
                    sectors.setdefault(sec, []).append(i)
            
            for sec, idx_list in sectors.items():
                if idx_list:
                    constraints.append({
                        'type': 'ineq',
                        'fun': lambda w, idx=idx_list, cap=effective_max_sector: cap - np.sum(w[idx])
                    })
        
        # Bounds for each asset
        # 0 <= weight <= max_position_weight
        bounds = tuple((0.0, self.max_position_weight) for _ in range(num_assets))
        
        # Initial guess: evenly distribute exposure
        initial_guess = np.array([self.max_portfolio_exposure / num_assets] * num_assets)
        
        result = minimize(
            objective, 
            initial_guess, 
            method='SLSQP', 
            bounds=bounds, 
            constraints=constraints,
            options={'ftol': 1e-9, 'disp': False}
        )
        
        if not result.success:
            logger.error(f"Optimization failed: {result.message}")
            # Fallback to current weights if optimization completely fails
            return current_weights
            
        optimal_weights = result.x
        
        # Clean up very small weights
        optimal_weights = np.where(optimal_weights < 0.001, 0.0, optimal_weights)
        
        target_allocation = {symbols[i]: round(float(optimal_weights[i]), 4) for i in range(num_assets)}
        logger.info(f"Generated target allocation: {target_allocation}")
        return target_allocation
