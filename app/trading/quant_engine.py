import pandas as pd
import numpy as np
from typing import Dict, Any, List

class QuantEngine:
    """
    Quantitative Research Engine for calculating risk/return metrics and ranking assets.
    """
    def __init__(self, risk_free_rate: float = 0.05, trading_days: int = 252):
        self.rf = risk_free_rate
        self.trading_days = trading_days

    def calculate_returns(self, prices: pd.Series) -> pd.DataFrame:
        """Calculates daily and cumulative returns."""
        daily_returns = prices.pct_change().fillna(0)
        cumulative_returns = (1 + daily_returns).cumprod() - 1
        return pd.DataFrame({
            'daily_returns': daily_returns,
            'cumulative_returns': cumulative_returns
        })

    def calculate_volatility(self, daily_returns: pd.Series) -> float:
        """Calculates annualized volatility."""
        return daily_returns.std() * np.sqrt(self.trading_days)

    def calculate_momentum(self, prices: pd.Series, period: int = 20) -> float:
        """Calculates rate of change (ROC) momentum over a specific period."""
        if len(prices) < period + 1:
            return 0.0
        return (prices.iloc[-1] / prices.iloc[-period - 1]) - 1

    def calculate_correlation_covariance(self, asset_returns: pd.Series, benchmark_returns: pd.Series) -> Dict[str, float]:
        """Calculates correlation and covariance between asset and benchmark."""
        # Align series to ensure same length
        aligned = pd.concat([asset_returns, benchmark_returns], axis=1).dropna()
        if len(aligned) < 2:
            return {"correlation": 0.0, "covariance": 0.0}
            
        corr = aligned.iloc[:, 0].corr(aligned.iloc[:, 1])
        cov = aligned.iloc[:, 0].cov(aligned.iloc[:, 1])
        return {"correlation": float(corr), "covariance": float(cov)}

    def calculate_beta(self, asset_returns: pd.Series, benchmark_returns: pd.Series) -> float:
        """Calculates Beta of asset relative to benchmark."""
        aligned = pd.concat([asset_returns, benchmark_returns], axis=1).dropna()
        if len(aligned) < 2:
            return 1.0
            
        cov = aligned.iloc[:, 0].cov(aligned.iloc[:, 1])
        var_benchmark = aligned.iloc[:, 1].var()
        
        if var_benchmark == 0:
            return 1.0
        return float(cov / var_benchmark)

    def calculate_drawdown(self, cumulative_returns: pd.Series) -> Dict[str, Any]:
        """Calculates current and maximum drawdown."""
        # cumulative_returns + 1 is the equity curve
        equity_curve = cumulative_returns + 1
        rolling_max = equity_curve.cummax()
        drawdowns = (equity_curve / rolling_max) - 1
        
        return {
            "current_drawdown": float(drawdowns.iloc[-1]) if not drawdowns.empty else 0.0,
            "max_drawdown": float(drawdowns.min()) if not drawdowns.empty else 0.0,
            "drawdown_series": drawdowns
        }

    def calculate_sharpe(self, daily_returns: pd.Series) -> float:
        """Calculates Annualized Sharpe Ratio."""
        if daily_returns.empty or daily_returns.std() == 0:
            return 0.0
            
        ann_return = daily_returns.mean() * self.trading_days
        ann_vol = self.calculate_volatility(daily_returns)
        
        return float((ann_return - self.rf) / ann_vol)

    def calculate_sortino(self, daily_returns: pd.Series) -> float:
        """Calculates Annualized Sortino Ratio."""
        if daily_returns.empty:
            return 0.0
            
        ann_return = daily_returns.mean() * self.trading_days
        downside_returns = daily_returns[daily_returns < 0]
        
        if downside_returns.empty or downside_returns.std() == 0:
            return 0.0 # Infinite or undefined
            
        downside_vol = downside_returns.std() * np.sqrt(self.trading_days)
        return float((ann_return - self.rf) / downside_vol)

    def build_stock_ranking(self, prices_df: pd.DataFrame, benchmark_prices: pd.Series = None) -> pd.DataFrame:
        """
        Ranks stocks based on a composite score of Sharpe, Momentum, and Max Drawdown.
        prices_df: DataFrame where columns are tickers and rows are dates/prices.
        benchmark_prices: Optional benchmark for Beta calculation.
        """
        metrics = []
        
        if benchmark_prices is not None:
            bench_returns = self.calculate_returns(benchmark_prices)['daily_returns']
            
        for ticker in prices_df.columns:
            series = prices_df[ticker].dropna()
            if len(series) < 2:
                continue
                
            returns_data = self.calculate_returns(series)
            daily_rets = returns_data['daily_returns']
            cum_rets = returns_data['cumulative_returns']
            
            sharpe = self.calculate_sharpe(daily_rets)
            sortino = self.calculate_sortino(daily_rets)
            vol = self.calculate_volatility(daily_rets)
            mom = self.calculate_momentum(series, period=min(20, len(series)-1))
            dd = self.calculate_drawdown(cum_rets)['max_drawdown']
            
            row = {
                "ticker": ticker,
                "sharpe": sharpe,
                "sortino": sortino,
                "volatility": vol,
                "momentum_20": mom,
                "max_drawdown": dd,
            }
            
            if benchmark_prices is not None:
                row["beta"] = self.calculate_beta(daily_rets, bench_returns)
                
            metrics.append(row)
            
        if not metrics:
            return pd.DataFrame()
            
        df = pd.DataFrame(metrics).set_index("ticker")
        
        # Simple Ranking Logic
        # Higher Sharpe is good, Higher Momentum is good, Lower (closer to 0) Drawdown is good
        df_z = (df - df.mean()) / df.std().replace(0, 1) # prevent div/0
        
        # Drawdown is a negative number. Larger (closer to 0) is better.
        df['composite_score'] = df_z['sharpe'] + df_z['momentum_20'] + df_z['max_drawdown']
        
        return df.sort_values(by='composite_score', ascending=False)
