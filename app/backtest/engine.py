import yfinance as yf
import pandas as pd
import numpy as np
import logging
from typing import Dict, List, Any
from datetime import datetime
from app.trading.strategy import EmaRsiVwapStrategy
from app.trading.ml_engine import MLEngine
from app.trading.portfolio_optimizer import PortfolioOptimizer
from app.trading.risk_engine import RiskEngine, RiskConfig, AccountState
from app.trading.signals import Signal, SignalDirection

logger = logging.getLogger(__name__)

class BacktestEngine:
    def __init__(
        self,
        symbols: List[str],
        start_date: str,
        end_date: str,
        initial_capital: float = 1000000.0,
        transaction_cost_pct: float = 0.001  # 0.1% covers brokerage, STT, slippage
    ):
        self.symbols = symbols
        self.start_date = start_date
        self.end_date = end_date
        self.initial_capital = initial_capital
        self.transaction_cost_pct = transaction_cost_pct
        
        self.strategy = EmaRsiVwapStrategy()
        self.ml_engine = MLEngine()
        self.optimizer = PortfolioOptimizer(max_position_weight=0.3, max_portfolio_exposure=1.0)
        
        risk_config = RiskConfig(
            max_order_value=initial_capital,
            max_total_exposure=initial_capital * 1.5,
            max_daily_loss_pct=0.05,
            max_drawdown_pct=0.20,
            check_market_hours=False # Disable for backtest
        )
        self.risk_engine = RiskEngine(risk_config)
        
        # State
        self.cash = initial_capital
        self.positions: Dict[str, float] = {sym: 0.0 for sym in symbols} # holdings in qty
        self.equity_curve: List[Dict[str, Any]] = []
        self.trades: List[Dict[str, Any]] = []
        self.peak_equity = initial_capital

    def load_data(self) -> Dict[str, pd.DataFrame]:
        logger.info(f"Downloading historical data for {self.symbols}...")
        data = {}
        for sym in self.symbols:
            df = yf.download(sym, start=self.start_date, end=self.end_date, progress=False)
            if not df.empty:
                # Ensure columns are simple strings, not MultiIndex
                if isinstance(df.columns, pd.MultiIndex):
                    df.columns = df.columns.get_level_values(0)
                # Rename columns for our indicators
                df = df.rename(columns={'Open': 'open', 'High': 'high', 'Low': 'low', 'Close': 'close', 'Volume': 'volume'})
                data[sym] = df
        return data

    def run(self):
        logger.info("Starting Backtest...")
        data = self.load_data()
        
        if not data:
            logger.error("No data loaded. Aborting.")
            return

        # Align all dates
        all_dates = sorted(list(set.union(*[set(df.index) for df in data.values()])))
        
        # Need some warmup period for EMA, RSI, ML
        warmup_days = 50
        if len(all_dates) < warmup_days:
            logger.error("Not enough data for warmup.")
            return
            
        # Train ML model on first chunk of data to simulate out-of-sample
        train_end_idx = int(len(all_dates) * 0.5) # First 50% for initial ML train
        train_end_date = all_dates[train_end_idx]
        
        logger.info(f"Training initial ML models up to {train_end_date.date()}...")
        for sym in self.symbols:
            df = data[sym].loc[:train_end_date]
            if len(df) > warmup_days:
                self.ml_engine.train_and_evaluate(sym, df)

        # Start walk-forward simulation
        for i in range(train_end_idx, len(all_dates)):
            current_date = all_dates[i]
            
            # 1. Update Portfolio Value at current prices
            current_prices = {}
            portfolio_value = self.cash
            open_position_values = {}
            
            for sym in self.symbols:
                df = data[sym]
                if current_date in df.index:
                    price = float(df.loc[current_date, 'close'])
                    current_prices[sym] = price
                    pos_val = self.positions[sym] * price
                    portfolio_value += pos_val
                    if pos_val > 0:
                        open_position_values[sym] = pos_val

            self.peak_equity = max(self.peak_equity, portfolio_value)
            
            # Account State for Risk Engine
            account = AccountState(
                available_margin=self.cash,
                peak_margin=self.peak_equity,
                realized_pnl=0.0, 
                unrealized_pnl=portfolio_value - self.initial_capital,
                open_positions=open_position_values
            )

            # 2. Generate Signals
            signals = []
            for sym in self.symbols:
                df = data[sym]
                if current_date not in df.index:
                    continue
                    
                history = df.loc[:current_date]
                if len(history) < warmup_days:
                    continue
                    
                # Technical Signal requires object with .close, .high, .low, .volume
                candle_objects = list(history.itertuples())
                sig = self.strategy.generate_signal(sym, candle_objects)
                
                # ML Prediction
                pred = self.ml_engine.predict(sym, history)
                
                # Simple ensemble: only trade if ML agrees with Technicals, or just use technicals and ML confidence
                # Let's say if signal is BUY and ML predicts positive return
                if sig.direction == SignalDirection.BUY and pred and pred.predicted_direction == "UP":
                    signals.append(sig)
                elif sig.direction == SignalDirection.SELL: # Exit signal
                    signals.append(sig)

            # 3. Portfolio Allocation
            if signals:
                # Build prices dataframe for optimization (last 252 days)
                hist_start = max(0, i - 252)
                hist_dates = all_dates[hist_start:i+1]
                
                prices_dict = {}
                for sym in self.symbols:
                    prices_dict[sym] = data[sym]['close'].reindex(hist_dates).ffill()
                prices_df = pd.DataFrame(prices_dict)
                
                current_weights = {sym: (self.positions[sym] * current_prices.get(sym, 0)) / portfolio_value for sym in self.symbols}
                target_weights = self.optimizer.optimize(current_weights, prices_df)
                
                # 4. Execute Trades
                for sym, target_w in target_weights.items():
                    if sym not in current_prices: continue
                    
                    price = current_prices[sym]
                    target_value = portfolio_value * target_w
                    current_value = self.positions[sym] * price
                    diff_value = target_value - current_value
                    
                    if abs(diff_value) < portfolio_value * 0.01: 
                        continue # Ignore small rebalances
                        
                    qty = int(abs(diff_value) / price)
                    if qty == 0: continue
                    
                    direction = SignalDirection.BUY if diff_value > 0 else SignalDirection.SELL
                    
                    # Risk validation for BUYs
                    if direction == SignalDirection.BUY:
                        test_sig = Signal(symbol=sym, direction=direction, entry_price=price, timestamp=str(current_date), confidence=0.8, stop_loss=price*0.95, take_target=price*1.1)
                        approved, reason = self.risk_engine.validate_signal(test_sig, account, qty)
                        if not approved:
                            continue
                            
                    # Execute
                    trade_cost = qty * price
                    transaction_cost = trade_cost * self.transaction_cost_pct
                    
                    if direction == SignalDirection.BUY:
                        if self.cash >= trade_cost + transaction_cost:
                            self.cash -= (trade_cost + transaction_cost)
                            self.positions[sym] += qty
                            self.trades.append({'date': current_date, 'symbol': sym, 'side': 'BUY', 'qty': qty, 'price': price, 'cost': transaction_cost})
                    else:
                        if self.positions[sym] >= qty:
                            self.cash += (trade_cost - transaction_cost)
                            self.positions[sym] -= qty
                            self.trades.append({'date': current_date, 'symbol': sym, 'side': 'SELL', 'qty': qty, 'price': price, 'cost': transaction_cost})

            # Record daily equity
            self.equity_curve.append({
                'date': current_date,
                'equity': portfolio_value,
                'cash': self.cash
            })

        self.calculate_metrics()

    def calculate_metrics(self):
        df = pd.DataFrame(self.equity_curve).set_index('date')
        df['returns'] = df['equity'].pct_change()
        
        total_return = (df['equity'].iloc[-1] / self.initial_capital) - 1
        annualized_return = (1 + total_return) ** (252 / len(df)) - 1
        
        volatility = df['returns'].std() * np.sqrt(252)
        sharpe = (annualized_return - 0.05) / volatility if volatility > 0 else 0
        
        df['cummax'] = df['equity'].cummax()
        df['drawdown'] = (df['cummax'] - df['equity']) / df['cummax']
        max_drawdown = df['drawdown'].max()
        
        win_rate = len(df[df['returns'] > 0]) / len(df[df['returns'] != 0]) if len(df[df['returns'] != 0]) > 0 else 0
        
        logger.info(f"--- Backtest Results ---")
        logger.info(f"Initial Capital: {self.initial_capital:,.2f}")
        logger.info(f"Final Equity: {df['equity'].iloc[-1]:,.2f}")
        logger.info(f"Total Return: {total_return*100:.2f}%")
        logger.info(f"Annualized Return: {annualized_return*100:.2f}%")
        logger.info(f"Sharpe Ratio: {sharpe:.2f}")
        logger.info(f"Max Drawdown: {max_drawdown*100:.2f}%")
        logger.info(f"Daily Win Rate: {win_rate*100:.2f}%")
        logger.info(f"Total Trades: {len(self.trades)}")

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    symbols = ["RELIANCE.NS", "TCS.NS", "HDFCBANK.NS", "INFY.NS", "ICICIBANK.NS"]
    tester = BacktestEngine(symbols, start_date="2022-01-01", end_date="2024-01-01")
    tester.run()
