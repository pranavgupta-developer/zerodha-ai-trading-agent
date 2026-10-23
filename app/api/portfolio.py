import logging
from typing import Optional
from fastapi import APIRouter, HTTPException
import pandas as pd
import numpy as np

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Portfolio"])


@router.get("/api/v1/portfolio")
def get_portfolio():
    """
    Returns full portfolio payload: live positions, holdings, account stats, and watchlist.
    """
    from app.main import build_portfolio_payload, sync_live_market_prices
    sync_live_market_prices()
    return build_portfolio_payload()


@router.get("/api/v1/portfolio/optimize")
async def optimize_portfolio_weights(
    max_exposure: float = 1.0,
    max_position_weight: float = 0.25,
    max_sector_weight: float = 0.35
):
    """
    Runs Markowitz Mean-Variance Portfolio Optimization on active market assets.
    Maximizes risk-adjusted Sharpe Ratio penalized for transaction costs under sector concentration constraints.
    """
    import app.main as m
    import asyncio
    import yfinance as yf
    from app.core.config import settings

    try:
        symbols = [s.strip().replace(".NS", "") for s in settings.TRADING_SYMBOLS.split(",") if s.strip()]
        if not symbols:
            symbols = ["RELIANCE", "TCS", "INFY", "HDFCBANK", "ICICIBANK"]

        # Fetch real daily prices for these symbols
        yf_tickers = [f"{s}.NS" for s in symbols]
        batch_df = await asyncio.to_thread(
            yf.download,
            tickers=yf_tickers,
            period="6mo",
            interval="1d",
            group_by="ticker",
            progress=False
        )

        price_series = {}
        for s in symbols:
            yf_sym = f"{s}.NS"
            s_df = batch_df if len(symbols) == 1 else (batch_df[yf_sym] if yf_sym in batch_df else None)
            if s_df is not None and not s_df.empty and 'Close' in s_df:
                vals = s_df['Close'].dropna().values.flatten()
                if len(vals) >= 20:
                    price_series[s] = vals

        min_len = min((len(v) for v in price_series.values()), default=0) if price_series else 0
        if min_len < 20 or len(price_series) < 2:
            raise HTTPException(status_code=400, detail="Insufficient historical price data across assets to optimize.")

        aligned_prices = pd.DataFrame({s: price_series[s][-min_len:] for s in price_series})

        # Calculate current weights based on open positions
        active_pos = m.position_manager.get_all_tracked()
        effective_margin = m.global_available_margin if m.global_available_margin > 0 else 500000.0
        current_weights = {
            s: round((active_pos[s].entry_price * active_pos[s].quantity) / effective_margin, 4)
            if s in active_pos and active_pos[s].is_active else 0.0
            for s in symbols
        }

        # Sector mapping for Indian market equities
        sector_mapping = {
            "RELIANCE": "Energy",
            "TCS": "Technology",
            "INFY": "Technology",
            "HDFCBANK": "Financials",
            "ICICIBANK": "Financials",
            "TATASTEEL": "Metals",
            "SBIN": "Financials",
            "BHARTIARTL": "Telecom",
            "ITC": "Consumer Goods",
            "KOTAKBANK": "Financials",
            "LT": "Capital Goods",
            "AXISBANK": "Financials",
            "MARUTI": "Automobile",
            "BAJFINANCE": "Financials",
            "WIPRO": "Technology",
            "HCLTECH": "Technology",
            "ASIANPAINT": "Consumer Goods",
            "SUNPHARMA": "Healthcare",
            "TITAN": "Consumer Goods",
            "ADANIENT": "Metals"
        }

        # Run Markowitz Optimizer
        from app.trading.portfolio_optimizer import PortfolioOptimizer
        optimizer = PortfolioOptimizer(
            max_position_weight=max_position_weight,
            max_portfolio_exposure=max_exposure,
            max_sector_weight=max_sector_weight,
            sector_mapping=sector_mapping
        )

        optimized_weights = optimizer.optimize(
            current_weights=current_weights,
            prices_df=aligned_prices,
            sector_mapping=sector_mapping,
            max_sector_weight=max_sector_weight
        )

        # Expected metrics
        returns_df = aligned_prices.pct_change().dropna()
        exp_returns = optimizer.calculate_expected_returns(returns_df)
        cov_matrix = optimizer.build_covariance_matrix(returns_df)
        w_arr = np.array([optimized_weights.get(s, 0.0) for s in aligned_prices.columns])
        port_ret = float(np.dot(w_arr, exp_returns.values))
        port_vol = float(np.sqrt(np.dot(w_arr.T, np.dot(cov_matrix.values, w_arr))))
        sharpe = round((port_ret - 0.05) / port_vol, 3) if port_vol > 0 else 0.0

        return {
            "status": "success",
            "method": "Markowitz Mean-Variance with Sector & Turnover Constraints",
            "optimized_weights": optimized_weights,
            "current_weights": current_weights,
            "expected_annual_return_pct": round(port_ret * 100, 2),
            "expected_annual_volatility_pct": round(port_vol * 100, 2),
            "optimized_sharpe_ratio": sharpe,
            "rebalancing_suggestions": [
                {
                    "symbol": s,
                    "current_weight": current_weights.get(s, 0.0),
                    "target_weight": optimized_weights.get(s, 0.0),
                    "action": "INCREASE" if optimized_weights.get(s, 0.0) > current_weights.get(s, 0.0) else "DECREASE"
                }
                for s in symbols if abs(optimized_weights.get(s, 0.0) - current_weights.get(s, 0.0)) > 0.01
            ]
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Portfolio optimization failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))
