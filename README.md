# TradeSignal Pro - Indian Stock Trading Signals

A comprehensive trading signal generator, backtester, and paper trading platform for Indian stocks (NSE/BSE).

## 🌐 Live Website
Visit the live dashboard: [TradeSignal Pro](https://goureesh.github.io/trading/)

## Features

### 📊 Signal Scanner
- Scan Nifty 50, Bank Nifty, or custom stocks
- Composite signals from multiple indicators
- Entry, Stop-Loss, and Target prices with Risk:Reward ratios

### 📈 11 Trading Strategies

**Classic Technical Analysis:**
| Strategy | Description |
|---|---|
| EMA Crossover | 9/21 EMA crossover trend following |
| RSI Mean Reversion | Oversold/overbought bounce plays |
| MACD Momentum | MACD line crossover signals |
| Supertrend | Trend direction with ATR bands |
| Bollinger Breakout | Volatility breakout with volume |
| EMA+RSI+MACD Combo | Multi-indicator confirmation |
| VWAP + EMA | Volume-weighted intraday entries |

**ICT (Inner Circle Trader):**
| Strategy | Description |
|---|---|
| Fair Value Gap | Trade imbalance retracements |
| Order Block | Enter at institutional order zones |
| Liquidity Sweep | Reversal after stop hunts + MSS |
| Optimal Trade Entry | 62-79% Fibonacci retracement |

### 🔬 Backtester
- Test any strategy on historical data
- Performance metrics: Win Rate, Profit Factor, Sharpe Ratio, Max Drawdown
- Risk:Reward ratio analysis (Planned, Realized, Win/Loss)
- Equity curve and P&L distribution charts
- Strategy comparison table

### 📡 Paper Trading
- Live signal monitoring with persistent state
- Position tracking with P&L
- Trade log with entry/exit details

## Quick Start

### Web Dashboard
Open `web/index.html` in your browser, or visit the GitHub Pages link above.

### Python CLI Tools
```bash
# Install dependencies
pip install -r requirements.txt

# Quick signal scan
python trading_signals.py --stock RELIANCE --detail

# Backtest all strategies
python backtester.py --stock RELIANCE --period 1y --compare

# Backtest ICT strategy with trade log
python backtester.py --stock RELIANCE --strategy ict_fvg --trades

# Start paper trading
python live_test.py --stock RELIANCE --strategy vwap_ema

# Check paper trading status
python live_test.py --status
```

## Tech Stack
- **Frontend**: Vanilla HTML/CSS/JS, Chart.js
- **Backend**: Python, yfinance, pandas, numpy
- **Data**: Yahoo Finance (free, 15-min delayed)
- **Hosting**: GitHub Pages

## Disclaimer
⚠️ This tool is for **educational and informational purposes only**. It is NOT financial advice. Always do your own research before trading. Past performance does not guarantee future results.
