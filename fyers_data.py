"""
Fyers Data Module — Direct REST API (no SDK needed)
=====================================================
Fetches historical candle data from Fyers API v3 using plain HTTP requests.
Supports 1min, 5min, 15min, 1hr, 1day candles for NSE/BSE stocks.
Auto-authenticates using fyers_auth when token is missing.

Usage:
    from fyers_data import fetch_fyers_data, fetch_data
    df = fetch_fyers_data("RELIANCE", interval="5", days=30)
    df = fetch_data("RELIANCE", period="3mo", interval="5m")  # auto fallback to Yahoo
"""

import json
import hashlib
import requests
import pandas as pd
from pathlib import Path
from datetime import datetime, timedelta

# ── Configuration ──
CLIENT_ID = "70OO9494R9-100"
SECRET_KEY = "M4RUQHA4T0"
REDIRECT_URI = "https://127.0.0.1"
TOKEN_FILE = Path(__file__).parent / ".fyers_token.json"

# Fyers API endpoints
AUTH_URL = "https://api-t1.fyers.in/api/v3/generate-authcode"
TOKEN_URL = "https://api-t1.fyers.in/api/v3/validate-authcode"
HISTORY_URL = "https://api-t1.fyers.in/data/history"
QUOTES_URL = "https://api-t1.fyers.in/data/quotes"

# Interval mapping: user-friendly → Fyers resolution
INTERVAL_MAP = {
    "1":    "1",     # 1 minute
    "1m":   "1",
    "5":    "5",     # 5 minutes
    "5m":   "5",
    "15":   "15",    # 15 minutes
    "15m":  "15",
    "30":   "30",    # 30 minutes
    "30m":  "30",
    "60":   "60",    # 1 hour
    "1h":   "60",
    "1d":   "D",     # Daily
    "D":    "D",
    "1wk":  "W",     # Weekly (mapped from Yahoo-style)
    "W":    "W",
}

# Max days Fyers allows per resolution
MAX_DAYS = {
    "1": 30, "5": 90, "15": 180, "30": 180,
    "60": 365, "D": 365 * 5, "W": 365 * 10,
}


def get_auth_url():
    """Generate the Fyers OAuth login URL."""
    app_id = CLIENT_ID.split("-")[0]
    url = f"https://api-t1.fyers.in/api/v3/generate-authcode?client_id={CLIENT_ID}&redirect_uri={REDIRECT_URI}&response_type=code&state=tradesignalpro"
    return url


def generate_token(auth_code):
    """Exchange auth code for access token via REST API."""
    app_id_hash = hashlib.sha256(
        f"{CLIENT_ID}:{SECRET_KEY}".encode()
    ).hexdigest()

    payload = {
        "grant_type": "authorization_code",
        "appIdHash": app_id_hash,
        "code": auth_code,
    }

    resp = requests.post(TOKEN_URL, json=payload)
    data = resp.json()

    if data.get("s") == "ok" or "access_token" in data:
        token_data = {
            "access_token": data["access_token"],
            "created_at": datetime.now().isoformat(),
            "expires_at": (datetime.now() + timedelta(hours=23)).isoformat(),
            "client_id": CLIENT_ID,
        }
        TOKEN_FILE.write_text(json.dumps(token_data, indent=2), encoding="utf-8")
        print(f"✅ Token saved! Valid until {token_data['expires_at']}")
        return data["access_token"]
    else:
        print(f"❌ Token error: {data}")
        return None


def load_token():
    """Load cached access token. Auto-login if expired."""
    if not TOKEN_FILE.exists():
        # Try auto-login
        try:
            from fyers_auth import auto_login
            auto_login()
        except Exception:
            pass
    try:
        data = json.loads(TOKEN_FILE.read_text(encoding="utf-8"))
        expires = datetime.fromisoformat(data["expires_at"])
        if datetime.now() < expires:
            return data["access_token"]
        # Token expired, try auto-login
        try:
            from fyers_auth import auto_login
            auto_login()
            data = json.loads(TOKEN_FILE.read_text(encoding="utf-8"))
            return data["access_token"]
        except Exception:
            return None
    except Exception:
        return None


def _headers():
    """Get auth headers for Fyers API."""
    token = load_token()
    if not token:
        raise RuntimeError(
            "No valid Fyers token. Run: python fyers_auth.py"
        )
    return {"Authorization": f"{CLIENT_ID}:{token}"}


def resolve_symbol(stock, exchange="NSE"):
    """Convert stock name to Fyers symbol format."""
    stock = stock.upper().strip()
    stock = stock.replace(".NS", "").replace(".BO", "")

    # Index symbols
    INDEX_MAP = {
        "NIFTY": "NSE:NIFTY50-INDEX",
        "NIFTY50": "NSE:NIFTY50-INDEX",
        "BANKNIFTY": "NSE:NIFTYBANK-INDEX",
        "NIFTYBANK": "NSE:NIFTYBANK-INDEX",
        "NIFTYIT": "NSE:NIFTYIT-INDEX",
        "FINNIFTY": "NSE:FINNIFTY-INDEX",
    }
    if stock in INDEX_MAP:
        return INDEX_MAP[stock]

    if exchange == "BSE":
        return f"BSE:{stock}-EQ"
    return f"NSE:{stock}-EQ"


def fetch_fyers_data(stock, interval="1d", days=365, exchange="NSE"):
    """
    Fetch historical OHLCV data from Fyers.

    Args:
        stock: Stock symbol (e.g., "RELIANCE", "TCS")
        interval: "1m", "5m", "15m", "30m", "1h", "1d", "1wk"
        days: Number of days of history
        exchange: "NSE" or "BSE"

    Returns:
        pd.DataFrame with columns: date, open, high, low, close, volume
    """
    symbol = resolve_symbol(stock, exchange)
    resolution = INTERVAL_MAP.get(interval, interval)

    # Clamp days to Fyers limits
    max_d = MAX_DAYS.get(resolution, 365)
    days = min(days, max_d)

    # Calculate date range
    to_date = datetime.now()
    from_date = to_date - timedelta(days=days)

    params = {
        "symbol": symbol,
        "resolution": resolution,
        "date_format": "1",
        "range_from": from_date.strftime("%Y-%m-%d"),
        "range_to": to_date.strftime("%Y-%m-%d"),
        "cont_flag": "1",
    }

    try:
        resp = requests.get(HISTORY_URL, headers=_headers(), params=params, timeout=15)
        data = resp.json()

        if data.get("s") != "ok" or "candles" not in data:
            # Try BSE if NSE failed
            if exchange == "NSE":
                return fetch_fyers_data(stock, interval, days, exchange="BSE")
            print(f"❌ Fyers error for {stock}: {data.get('message', data.get('s', 'unknown'))}")
            return None

        candles = data["candles"]
        if not candles:
            return None

        df = pd.DataFrame(candles, columns=["timestamp", "open", "high", "low", "close", "volume"])
        df["date"] = pd.to_datetime(df["timestamp"], unit="s")
        df = df[["date", "open", "high", "low", "close", "volume"]]
        df = df.sort_values("date").reset_index(drop=True)
        return df

    except Exception as e:
        print(f"❌ Fyers fetch error: {e}")
        return None


def get_quote(stock, exchange="NSE"):
    """Get real-time quote for a stock."""
    symbol = resolve_symbol(stock, exchange)
    params = {"symbols": symbol}

    try:
        resp = requests.get(QUOTES_URL, headers=_headers(), params=params, timeout=10)
        data = resp.json()
        if data.get("s") == "ok" and data.get("d"):
            q = data["d"][0]["v"]
            return {
                "symbol": stock,
                "ltp": q.get("lp", 0),
                "open": q.get("open_price", 0),
                "high": q.get("high_price", 0),
                "low": q.get("low_price", 0),
                "close": q.get("prev_close_price", 0),
                "volume": q.get("volume", 0),
                "change_pct": q.get("ch", 0),
            }
        return None
    except Exception:
        return None


def fetch_data(stock, period="1y", interval="1d"):
    """
    Universal data fetcher — tries Fyers first, falls back to yfinance.

    Args:
        stock: Stock symbol
        period: "3mo", "6mo", "1y", "2y" (Yahoo-style)
        interval: "5m", "15m", "1d", "1wk" etc.

    Returns:
        pd.DataFrame with columns: date, open, high, low, close, volume
    """
    # Convert period to days
    period_days = {
        "1mo": 30, "3mo": 90, "6mo": 180,
        "1y": 365, "2y": 730, "5y": 1825,
    }.get(period, 365)

    # Try Fyers first
    token = load_token()
    if token:
        df = fetch_fyers_data(stock, interval=interval, days=period_days)
        if df is not None and len(df) >= 10:
            print(f"  📊 {stock}: {len(df)} candles from Fyers ({interval})")
            return df

    # Fallback to yfinance
    try:
        import yfinance as yf
        stock_clean = stock.upper().replace(".NS", "").replace(".BO", "")
        for suffix in [".NS", ".BO"]:
            ticker = yf.Ticker(f"{stock_clean}{suffix}")
            df = ticker.history(period=period, interval=interval)
            if df is not None and len(df) >= 10:
                df = df.reset_index()
                df.columns = [c.lower() for c in df.columns]
                if "date" not in df.columns and "datetime" in df.columns:
                    df = df.rename(columns={"datetime": "date"})
                df = df[["date", "open", "high", "low", "close", "volume"]]
                print(f"  📊 {stock}: {len(df)} candles from Yahoo ({interval})")
                return df
    except Exception:
        pass

    print(f"  ❌ {stock}: No data available")
    return None


# ── PERIOD MAPPING for Fyers ──
PERIOD_MAP = {
    "3mo": 90, "6mo": 180, "1y": 365, "2y": 730,
}


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python fyers_data.py RELIANCE [interval] [days]")
        print("  interval: 1m, 5m, 15m, 30m, 1h, 1d (default: 1d)")
        print("  days: number of days (default: 30)")
        sys.exit(0)

    stock = sys.argv[1]
    interval = sys.argv[2] if len(sys.argv) > 2 else "1d"
    days = int(sys.argv[3]) if len(sys.argv) > 3 else 30

    df = fetch_data(stock, interval=interval)
    if df is not None:
        print(f"\n{stock} — {len(df)} candles ({interval})")
        print(df.tail(10).to_string(index=False))
    else:
        print(f"No data for {stock}")
