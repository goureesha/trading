"""
Trading Strategies Library
===========================
Contains multiple trading strategies that can be backtested and live tested.
Each strategy returns entry/exit signals on a DataFrame.
"""

import numpy as np
import pandas as pd


# ─────────────────────────────────────────────────────────────────────────────
# INDICATOR HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def ema(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(span=period, adjust=False).mean()


def sma(series: pd.Series, period: int) -> pd.Series:
    return series.rolling(window=period).mean()


def rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.where(delta > 0, 0.0)
    loss = -delta.where(delta < 0, 0.0)
    avg_gain = gain.ewm(alpha=1 / period, min_periods=period).mean()
    avg_loss = loss.ewm(alpha=1 / period, min_periods=period).mean()
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def macd(close: pd.Series, fast=12, slow=26, signal=9):
    ema_fast = ema(close, fast)
    ema_slow = ema(close, slow)
    macd_line = ema_fast - ema_slow
    signal_line = ema(macd_line, signal)
    histogram = macd_line - signal_line
    return macd_line, signal_line, histogram


def atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    high_low = df["High"] - df["Low"]
    high_close = (df["High"] - df["Close"].shift()).abs()
    low_close = (df["Low"] - df["Close"].shift()).abs()
    true_range = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    return true_range.ewm(alpha=1 / period, min_periods=period).mean()


def supertrend(df: pd.DataFrame, period: int = 10, multiplier: float = 3.0):
    hl2 = (df["High"] + df["Low"]) / 2
    atr_val = atr(df, period)
    upper_band = hl2 + (multiplier * atr_val)
    lower_band = hl2 - (multiplier * atr_val)

    st = pd.Series(np.nan, index=df.index)
    direction = pd.Series(1, index=df.index)

    for i in range(1, len(df)):
        if lower_band.iloc[i] > lower_band.iloc[i - 1] or df["Close"].iloc[i - 1] < lower_band.iloc[i - 1]:
            pass
        else:
            lower_band.iloc[i] = lower_band.iloc[i - 1]

        if upper_band.iloc[i] < upper_band.iloc[i - 1] or df["Close"].iloc[i - 1] > upper_band.iloc[i - 1]:
            pass
        else:
            upper_band.iloc[i] = upper_band.iloc[i - 1]

        if st.iloc[i - 1] == upper_band.iloc[i - 1]:
            if df["Close"].iloc[i] > upper_band.iloc[i]:
                st.iloc[i] = lower_band.iloc[i]
                direction.iloc[i] = 1
            else:
                st.iloc[i] = upper_band.iloc[i]
                direction.iloc[i] = -1
        else:
            if df["Close"].iloc[i] < lower_band.iloc[i]:
                st.iloc[i] = upper_band.iloc[i]
                direction.iloc[i] = -1
            else:
                st.iloc[i] = lower_band.iloc[i]
                direction.iloc[i] = 1

    return st, direction


def bollinger_bands(close: pd.Series, period: int = 20, std_dev: float = 2.0):
    mid = sma(close, period)
    std = close.rolling(window=period).std()
    upper = mid + (std_dev * std)
    lower = mid - (std_dev * std)
    return upper, mid, lower


def vwap(df: pd.DataFrame) -> pd.Series:
    typical_price = (df["High"] + df["Low"] + df["Close"]) / 3
    if "Volume" in df.columns and df["Volume"].sum() > 0:
        cum_vol = df["Volume"].cumsum()
        cum_tp_vol = (typical_price * df["Volume"]).cumsum()
        return cum_tp_vol / cum_vol
    return typical_price


# ─────────────────────────────────────────────────────────────────────────────
# STRATEGY BASE CLASS
# ─────────────────────────────────────────────────────────────────────────────

class Strategy:
    """Base class for all strategies."""
    name = "Base Strategy"
    description = ""

    def __init__(self, **params):
        self.params = params

    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Must return a DataFrame with columns:
        - 'signal': +1 (buy), -1 (sell), 0 (hold)
        - 'entry_price': price at entry
        - 'stop_loss': stop loss price
        - 'target': target price
        """
        raise NotImplementedError


# ─────────────────────────────────────────────────────────────────────────────
# STRATEGY 1: EMA CROSSOVER
# ─────────────────────────────────────────────────────────────────────────────

class EMACrossover(Strategy):
    name = "EMA Crossover"
    description = "Buy when fast EMA crosses above slow EMA, sell on cross below. Uses ATR for SL/Target."

    def __init__(self, fast_period=9, slow_period=21, atr_sl_mult=1.5, atr_tp_mult=2.0):
        self.fast_period = fast_period
        self.slow_period = slow_period
        self.atr_sl_mult = atr_sl_mult
        self.atr_tp_mult = atr_tp_mult

    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        df["ema_fast"] = ema(df["Close"], self.fast_period)
        df["ema_slow"] = ema(df["Close"], self.slow_period)
        df["atr"] = atr(df)

        df["signal"] = 0
        # Bullish crossover
        df.loc[(df["ema_fast"] > df["ema_slow"]) & (df["ema_fast"].shift(1) <= df["ema_slow"].shift(1)), "signal"] = 1
        # Bearish crossover
        df.loc[(df["ema_fast"] < df["ema_slow"]) & (df["ema_fast"].shift(1) >= df["ema_slow"].shift(1)), "signal"] = -1

        df["stop_loss"] = np.where(df["signal"] == 1, df["Close"] - self.atr_sl_mult * df["atr"],
                           np.where(df["signal"] == -1, df["Close"] + self.atr_sl_mult * df["atr"], np.nan))
        df["target"] = np.where(df["signal"] == 1, df["Close"] + self.atr_tp_mult * df["atr"],
                        np.where(df["signal"] == -1, df["Close"] - self.atr_tp_mult * df["atr"], np.nan))
        df["entry_price"] = np.where(df["signal"] != 0, df["Close"], np.nan)

        return df


# ─────────────────────────────────────────────────────────────────────────────
# STRATEGY 2: RSI MEAN REVERSION
# ─────────────────────────────────────────────────────────────────────────────

class RSIMeanReversion(Strategy):
    name = "RSI Mean Reversion"
    description = "Buy when RSI drops below oversold, sell when RSI rises above overbought. Exits at RSI 50."

    def __init__(self, rsi_period=14, oversold=30, overbought=70, atr_sl_mult=1.5, atr_tp_mult=2.0):
        self.rsi_period = rsi_period
        self.oversold = oversold
        self.overbought = overbought
        self.atr_sl_mult = atr_sl_mult
        self.atr_tp_mult = atr_tp_mult

    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        df["rsi"] = rsi(df["Close"], self.rsi_period)
        df["atr"] = atr(df)

        df["signal"] = 0
        # Buy when RSI crosses above oversold from below
        df.loc[(df["rsi"] > self.oversold) & (df["rsi"].shift(1) <= self.oversold), "signal"] = 1
        # Sell when RSI crosses below overbought from above
        df.loc[(df["rsi"] < self.overbought) & (df["rsi"].shift(1) >= self.overbought), "signal"] = -1

        df["stop_loss"] = np.where(df["signal"] == 1, df["Close"] - self.atr_sl_mult * df["atr"],
                           np.where(df["signal"] == -1, df["Close"] + self.atr_sl_mult * df["atr"], np.nan))
        df["target"] = np.where(df["signal"] == 1, df["Close"] + self.atr_tp_mult * df["atr"],
                        np.where(df["signal"] == -1, df["Close"] - self.atr_tp_mult * df["atr"], np.nan))
        df["entry_price"] = np.where(df["signal"] != 0, df["Close"], np.nan)

        return df


# ─────────────────────────────────────────────────────────────────────────────
# STRATEGY 3: MACD MOMENTUM
# ─────────────────────────────────────────────────────────────────────────────

class MACDMomentum(Strategy):
    name = "MACD Momentum"
    description = "Buy on MACD bullish crossover (MACD > Signal), sell on bearish crossover."

    def __init__(self, fast=12, slow=26, signal_period=9, atr_sl_mult=1.5, atr_tp_mult=2.5):
        self.fast = fast
        self.slow = slow
        self.signal_period = signal_period
        self.atr_sl_mult = atr_sl_mult
        self.atr_tp_mult = atr_tp_mult

    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        df["macd"], df["macd_signal"], df["macd_hist"] = macd(df["Close"], self.fast, self.slow, self.signal_period)
        df["atr"] = atr(df)

        df["signal"] = 0
        # Bullish: MACD crosses above signal
        df.loc[(df["macd"] > df["macd_signal"]) & (df["macd"].shift(1) <= df["macd_signal"].shift(1)), "signal"] = 1
        # Bearish: MACD crosses below signal
        df.loc[(df["macd"] < df["macd_signal"]) & (df["macd"].shift(1) >= df["macd_signal"].shift(1)), "signal"] = -1

        df["stop_loss"] = np.where(df["signal"] == 1, df["Close"] - self.atr_sl_mult * df["atr"],
                           np.where(df["signal"] == -1, df["Close"] + self.atr_sl_mult * df["atr"], np.nan))
        df["target"] = np.where(df["signal"] == 1, df["Close"] + self.atr_tp_mult * df["atr"],
                        np.where(df["signal"] == -1, df["Close"] - self.atr_tp_mult * df["atr"], np.nan))
        df["entry_price"] = np.where(df["signal"] != 0, df["Close"], np.nan)

        return df


# ─────────────────────────────────────────────────────────────────────────────
# STRATEGY 4: SUPERTREND
# ─────────────────────────────────────────────────────────────────────────────

class SupertrendStrategy(Strategy):
    name = "Supertrend"
    description = "Buy when Supertrend turns bullish (green), sell when it turns bearish (red)."

    def __init__(self, period=10, multiplier=2.0, atr_sl_mult=1.5, atr_tp_mult=2.0):
        self.period = period
        self.multiplier = multiplier
        self.atr_sl_mult = atr_sl_mult
        self.atr_tp_mult = atr_tp_mult

    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        df["st"], df["st_dir"] = supertrend(df, self.period, self.multiplier)
        df["atr"] = atr(df)

        df["signal"] = 0
        # Buy when direction changes to bullish
        df.loc[(df["st_dir"] == 1) & (df["st_dir"].shift(1) == -1), "signal"] = 1
        # Sell when direction changes to bearish
        df.loc[(df["st_dir"] == -1) & (df["st_dir"].shift(1) == 1), "signal"] = -1

        df["stop_loss"] = np.where(df["signal"] == 1, df["Close"] - self.atr_sl_mult * df["atr"],
                           np.where(df["signal"] == -1, df["Close"] + self.atr_sl_mult * df["atr"], np.nan))
        df["target"] = np.where(df["signal"] == 1, df["Close"] + self.atr_tp_mult * df["atr"],
                        np.where(df["signal"] == -1, df["Close"] - self.atr_tp_mult * df["atr"], np.nan))
        df["entry_price"] = np.where(df["signal"] != 0, df["Close"], np.nan)

        return df


# ─────────────────────────────────────────────────────────────────────────────
# STRATEGY 5: BOLLINGER BAND SQUEEZE + BREAKOUT
# ─────────────────────────────────────────────────────────────────────────────

class BollingerBreakout(Strategy):
    name = "Bollinger Breakout"
    description = "Buy when price breaks above upper Bollinger Band with volume, sell on break below lower band."

    def __init__(self, bb_period=20, std_dev=2.0, vol_mult=1.5, atr_sl_mult=1.5, atr_tp_mult=2.0):
        self.bb_period = bb_period
        self.std_dev = std_dev
        self.vol_mult = vol_mult
        self.atr_sl_mult = atr_sl_mult
        self.atr_tp_mult = atr_tp_mult

    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        df["bb_upper"], df["bb_mid"], df["bb_lower"] = bollinger_bands(df["Close"], self.bb_period, self.std_dev)
        df["atr"] = atr(df)
        df["vol_avg"] = df["Volume"].rolling(20).mean()

        df["signal"] = 0
        # Buy: price closes above upper band with high volume
        buy_cond = (df["Close"] > df["bb_upper"]) & (df["Close"].shift(1) <= df["bb_upper"].shift(1))
        if "Volume" in df.columns:
            buy_cond = buy_cond & (df["Volume"] > self.vol_mult * df["vol_avg"])
        df.loc[buy_cond, "signal"] = 1

        # Sell: price closes below lower band
        sell_cond = (df["Close"] < df["bb_lower"]) & (df["Close"].shift(1) >= df["bb_lower"].shift(1))
        df.loc[sell_cond, "signal"] = -1

        df["stop_loss"] = np.where(df["signal"] == 1, df["Close"] - self.atr_sl_mult * df["atr"],
                           np.where(df["signal"] == -1, df["Close"] + self.atr_sl_mult * df["atr"], np.nan))
        df["target"] = np.where(df["signal"] == 1, df["Close"] + self.atr_tp_mult * df["atr"],
                        np.where(df["signal"] == -1, df["Close"] - self.atr_tp_mult * df["atr"], np.nan))
        df["entry_price"] = np.where(df["signal"] != 0, df["Close"], np.nan)

        return df


# ─────────────────────────────────────────────────────────────────────────────
# STRATEGY 6: EMA + RSI + MACD COMBO
# ─────────────────────────────────────────────────────────────────────────────

class ComboStrategy(Strategy):
    name = "EMA+RSI+MACD Combo"
    description = "Buy when EMA bullish + RSI not overbought + MACD bullish. Strongest multi-indicator filter."

    def __init__(self, ema_fast=9, ema_slow=21, rsi_period=14, atr_sl_mult=1.5, atr_tp_mult=2.5):
        self.ema_fast = ema_fast
        self.ema_slow = ema_slow
        self.rsi_period = rsi_period
        self.atr_sl_mult = atr_sl_mult
        self.atr_tp_mult = atr_tp_mult

    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        df["ema_f"] = ema(df["Close"], self.ema_fast)
        df["ema_s"] = ema(df["Close"], self.ema_slow)
        df["rsi"] = rsi(df["Close"], self.rsi_period)
        df["macd_line"], df["macd_sig"], df["macd_hist"] = macd(df["Close"])
        df["atr"] = atr(df)

        df["signal"] = 0

        # Buy: EMA bullish cross + RSI < 65 (not overbought) + MACD histogram positive
        buy_cond = (
            (df["ema_f"] > df["ema_s"]) &
            (df["ema_f"].shift(1) <= df["ema_s"].shift(1)) &
            (df["rsi"] < 65) &
            (df["macd_hist"] > 0)
        )
        df.loc[buy_cond, "signal"] = 1

        # Sell: EMA bearish cross + RSI > 35 (not oversold) + MACD histogram negative
        sell_cond = (
            (df["ema_f"] < df["ema_s"]) &
            (df["ema_f"].shift(1) >= df["ema_s"].shift(1)) &
            (df["rsi"] > 35) &
            (df["macd_hist"] < 0)
        )
        df.loc[sell_cond, "signal"] = -1

        df["stop_loss"] = np.where(df["signal"] == 1, df["Close"] - self.atr_sl_mult * df["atr"],
                           np.where(df["signal"] == -1, df["Close"] + self.atr_sl_mult * df["atr"], np.nan))
        df["target"] = np.where(df["signal"] == 1, df["Close"] + self.atr_tp_mult * df["atr"],
                        np.where(df["signal"] == -1, df["Close"] - self.atr_tp_mult * df["atr"], np.nan))
        df["entry_price"] = np.where(df["signal"] != 0, df["Close"], np.nan)

        return df


# ─────────────────────────────────────────────────────────────────────────────
# STRATEGY 7: VWAP + EMA (INTRADAY)
# ─────────────────────────────────────────────────────────────────────────────

class VWAPStrategy(Strategy):
    name = "VWAP + EMA"
    description = "Buy when price crosses above VWAP and EMA is bullish. Best for intraday."

    def __init__(self, ema_period=20, atr_sl_mult=1.0, atr_tp_mult=1.5):
        self.ema_period = ema_period
        self.atr_sl_mult = atr_sl_mult
        self.atr_tp_mult = atr_tp_mult

    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        df["vwap"] = vwap(df)
        df["ema_line"] = ema(df["Close"], self.ema_period)
        df["atr"] = atr(df)

        df["signal"] = 0
        # Buy: price crosses above VWAP and is above EMA
        buy_cond = (
            (df["Close"] > df["vwap"]) &
            (df["Close"].shift(1) <= df["vwap"].shift(1)) &
            (df["Close"] > df["ema_line"])
        )
        df.loc[buy_cond, "signal"] = 1

        # Sell: price crosses below VWAP and is below EMA
        sell_cond = (
            (df["Close"] < df["vwap"]) &
            (df["Close"].shift(1) >= df["vwap"].shift(1)) &
            (df["Close"] < df["ema_line"])
        )
        df.loc[sell_cond, "signal"] = -1

        df["stop_loss"] = np.where(df["signal"] == 1, df["Close"] - self.atr_sl_mult * df["atr"],
                           np.where(df["signal"] == -1, df["Close"] + self.atr_sl_mult * df["atr"], np.nan))
        df["target"] = np.where(df["signal"] == 1, df["Close"] + self.atr_tp_mult * df["atr"],
                        np.where(df["signal"] == -1, df["Close"] - self.atr_tp_mult * df["atr"], np.nan))
        df["entry_price"] = np.where(df["signal"] != 0, df["Close"], np.nan)

        return df


# =============================================================================
# ICT (INNER CIRCLE TRADER) STRATEGIES
# =============================================================================


# ─────────────────────────────────────────────────────────────────────────────
# ICT HELPER FUNCTIONS
# ─────────────────────────────────────────────────────────────────────────────

def detect_swing_highs(df: pd.DataFrame, lookback: int = 5) -> pd.Series:
    """Detect swing highs: a high that is higher than 'lookback' bars on each side."""
    highs = df["High"]
    swing_high = pd.Series(False, index=df.index)
    for i in range(lookback, len(df) - lookback):
        if highs.iloc[i] == highs.iloc[i - lookback:i + lookback + 1].max():
            swing_high.iloc[i] = True
    return swing_high


def detect_swing_lows(df: pd.DataFrame, lookback: int = 5) -> pd.Series:
    """Detect swing lows: a low that is lower than 'lookback' bars on each side."""
    lows = df["Low"]
    swing_low = pd.Series(False, index=df.index)
    for i in range(lookback, len(df) - lookback):
        if lows.iloc[i] == lows.iloc[i - lookback:i + lookback + 1].min():
            swing_low.iloc[i] = True
    return swing_low


def detect_fvg(df: pd.DataFrame):
    """
    Detect Fair Value Gaps (FVG) - ICT concept.
    Bullish FVG: candle[i-2] high < candle[i] low (gap up through middle candle)
    Bearish FVG: candle[i-2] low > candle[i] high (gap down through middle candle)
    """
    bullish_fvg = pd.Series(False, index=df.index)
    bearish_fvg = pd.Series(False, index=df.index)
    fvg_upper = pd.Series(np.nan, index=df.index)
    fvg_lower = pd.Series(np.nan, index=df.index)

    for i in range(2, len(df)):
        # Bullish FVG: gap between candle[i-2] high and candle[i] low
        if df["Low"].iloc[i] > df["High"].iloc[i - 2]:
            bullish_fvg.iloc[i] = True
            fvg_upper.iloc[i] = df["Low"].iloc[i]
            fvg_lower.iloc[i] = df["High"].iloc[i - 2]

        # Bearish FVG: gap between candle[i-2] low and candle[i] high
        if df["High"].iloc[i] < df["Low"].iloc[i - 2]:
            bearish_fvg.iloc[i] = True
            fvg_upper.iloc[i] = df["Low"].iloc[i - 2]
            fvg_lower.iloc[i] = df["High"].iloc[i]

    return bullish_fvg, bearish_fvg, fvg_upper, fvg_lower


def detect_order_blocks(df: pd.DataFrame, lookback: int = 10):
    """
    Detect Order Blocks - ICT concept.
    Bullish OB: Last bearish candle before a strong bullish move.
    Bearish OB: Last bullish candle before a strong bearish move.
    """
    bullish_ob = pd.Series(False, index=df.index)
    bearish_ob = pd.Series(False, index=df.index)
    ob_high = pd.Series(np.nan, index=df.index)
    ob_low = pd.Series(np.nan, index=df.index)

    atr_val = atr(df, 14)

    for i in range(lookback, len(df)):
        # Strong bullish move: current close > previous close + 1.5*ATR
        if df["Close"].iloc[i] > df["Close"].iloc[i - 1] + 1.5 * atr_val.iloc[i]:
            # Find last bearish candle before this move
            for j in range(i - 1, max(i - lookback, 0), -1):
                if df["Close"].iloc[j] < df["Open"].iloc[j]:  # Bearish candle
                    bullish_ob.iloc[i] = True
                    ob_high.iloc[i] = df["High"].iloc[j]
                    ob_low.iloc[i] = df["Low"].iloc[j]
                    break

        # Strong bearish move: current close < previous close - 1.5*ATR
        if df["Close"].iloc[i] < df["Close"].iloc[i - 1] - 1.5 * atr_val.iloc[i]:
            # Find last bullish candle before this move
            for j in range(i - 1, max(i - lookback, 0), -1):
                if df["Close"].iloc[j] > df["Open"].iloc[j]:  # Bullish candle
                    bearish_ob.iloc[i] = True
                    ob_high.iloc[i] = df["High"].iloc[j]
                    ob_low.iloc[i] = df["Low"].iloc[j]
                    break

    return bullish_ob, bearish_ob, ob_high, ob_low


def detect_market_structure_shift(df: pd.DataFrame, lookback: int = 5):
    """
    Detect Market Structure Shift (MSS) - ICT concept.
    Bullish MSS: Price breaks above the most recent swing high after making lower lows.
    Bearish MSS: Price breaks below the most recent swing low after making higher highs.
    """
    bullish_mss = pd.Series(False, index=df.index)
    bearish_mss = pd.Series(False, index=df.index)

    swing_highs = detect_swing_highs(df, lookback)
    swing_lows = detect_swing_lows(df, lookback)

    last_swing_high = np.nan
    last_swing_low = np.nan

    for i in range(lookback, len(df)):
        if swing_highs.iloc[i]:
            last_swing_high = df["High"].iloc[i]
        if swing_lows.iloc[i]:
            last_swing_low = df["Low"].iloc[i]

        # Bullish MSS: close breaks above last swing high
        if not np.isnan(last_swing_high) and df["Close"].iloc[i] > last_swing_high:
            if df["Close"].iloc[i - 1] <= last_swing_high:
                bullish_mss.iloc[i] = True

        # Bearish MSS: close breaks below last swing low
        if not np.isnan(last_swing_low) and df["Close"].iloc[i] < last_swing_low:
            if df["Close"].iloc[i - 1] >= last_swing_low:
                bearish_mss.iloc[i] = True

    return bullish_mss, bearish_mss


# ─────────────────────────────────────────────────────────────────────────────
# STRATEGY 8: ICT FAIR VALUE GAP (FVG)
# ─────────────────────────────────────────────────────────────────────────────

class ICTFairValueGap(Strategy):
    name = "ICT Fair Value Gap"
    description = "Buy when price retraces into a bullish FVG, sell into bearish FVG. Core ICT concept."

    def __init__(self, atr_sl_mult=1.5, atr_tp_mult=3.0):
        self.atr_sl_mult = atr_sl_mult
        self.atr_tp_mult = atr_tp_mult

    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        df["atr"] = atr(df)
        bullish_fvg, bearish_fvg, fvg_upper, fvg_lower = detect_fvg(df)

        df["signal"] = 0

        # Track active FVGs (unfilled gaps)
        active_bull_fvgs = []  # list of (upper, lower) tuples
        active_bear_fvgs = []

        for i in range(len(df)):
            # Register new FVGs
            if bullish_fvg.iloc[i]:
                active_bull_fvgs.append((fvg_upper.iloc[i], fvg_lower.iloc[i]))
            if bearish_fvg.iloc[i]:
                active_bear_fvgs.append((fvg_upper.iloc[i], fvg_lower.iloc[i]))

            # Check if price retraces into a bullish FVG (buy opportunity)
            new_bull = []
            for upper, lower in active_bull_fvgs:
                if df["Low"].iloc[i] <= upper and df["Close"].iloc[i] >= lower:
                    # Price entered the FVG zone - BUY signal
                    if df["signal"].iloc[i] == 0:
                        df.iloc[i, df.columns.get_loc("signal")] = 1
                    # FVG is filled, remove it
                else:
                    new_bull.append((upper, lower))
            active_bull_fvgs = new_bull[-5:]  # Keep only last 5

            # Check if price retraces into a bearish FVG (sell opportunity)
            new_bear = []
            for upper, lower in active_bear_fvgs:
                if df["High"].iloc[i] >= lower and df["Close"].iloc[i] <= upper:
                    if df["signal"].iloc[i] == 0:
                        df.iloc[i, df.columns.get_loc("signal")] = -1
                else:
                    new_bear.append((upper, lower))
            active_bear_fvgs = new_bear[-5:]

        df["stop_loss"] = np.where(df["signal"] == 1, df["Close"] - self.atr_sl_mult * df["atr"],
                           np.where(df["signal"] == -1, df["Close"] + self.atr_sl_mult * df["atr"], np.nan))
        df["target"] = np.where(df["signal"] == 1, df["Close"] + self.atr_tp_mult * df["atr"],
                        np.where(df["signal"] == -1, df["Close"] - self.atr_tp_mult * df["atr"], np.nan))
        df["entry_price"] = np.where(df["signal"] != 0, df["Close"], np.nan)

        return df


# ─────────────────────────────────────────────────────────────────────────────
# STRATEGY 9: ICT ORDER BLOCK
# ─────────────────────────────────────────────────────────────────────────────

class ICTOrderBlock(Strategy):
    name = "ICT Order Block"
    description = "Buy at bullish order blocks (last bearish candle before impulse up), sell at bearish OBs."

    def __init__(self, lookback=10, atr_sl_mult=1.5, atr_tp_mult=3.0):
        self.lookback = lookback
        self.atr_sl_mult = atr_sl_mult
        self.atr_tp_mult = atr_tp_mult

    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        df["atr"] = atr(df)
        bullish_ob, bearish_ob, ob_high, ob_low = detect_order_blocks(df, self.lookback)

        df["signal"] = 0

        # Track active order blocks
        active_bull_obs = []  # (high, low) of bullish OB zones
        active_bear_obs = []

        for i in range(len(df)):
            if bullish_ob.iloc[i]:
                active_bull_obs.append((ob_high.iloc[i], ob_low.iloc[i]))
            if bearish_ob.iloc[i]:
                active_bear_obs.append((ob_high.iloc[i], ob_low.iloc[i]))

            # Price retraces to bullish OB zone
            new_bull = []
            for high, low in active_bull_obs:
                if df["Low"].iloc[i] <= high and df["Close"].iloc[i] >= low:
                    if df["signal"].iloc[i] == 0:
                        df.iloc[i, df.columns.get_loc("signal")] = 1
                elif df["Close"].iloc[i] < low - df["atr"].iloc[i]:
                    pass  # OB invalidated
                else:
                    new_bull.append((high, low))
            active_bull_obs = new_bull[-5:]

            # Price retraces to bearish OB zone
            new_bear = []
            for high, low in active_bear_obs:
                if df["High"].iloc[i] >= low and df["Close"].iloc[i] <= high:
                    if df["signal"].iloc[i] == 0:
                        df.iloc[i, df.columns.get_loc("signal")] = -1
                elif df["Close"].iloc[i] > high + df["atr"].iloc[i]:
                    pass  # OB invalidated
                else:
                    new_bear.append((high, low))
            active_bear_obs = new_bear[-5:]

        df["stop_loss"] = np.where(df["signal"] == 1, df["Close"] - self.atr_sl_mult * df["atr"],
                           np.where(df["signal"] == -1, df["Close"] + self.atr_sl_mult * df["atr"], np.nan))
        df["target"] = np.where(df["signal"] == 1, df["Close"] + self.atr_tp_mult * df["atr"],
                        np.where(df["signal"] == -1, df["Close"] - self.atr_tp_mult * df["atr"], np.nan))
        df["entry_price"] = np.where(df["signal"] != 0, df["Close"], np.nan)

        return df


# ─────────────────────────────────────────────────────────────────────────────
# STRATEGY 10: ICT LIQUIDITY SWEEP + MSS
# ─────────────────────────────────────────────────────────────────────────────

class ICTLiquiditySweep(Strategy):
    name = "ICT Liquidity Sweep"
    description = "Buy after liquidity sweep of lows + market structure shift bullish. Classic ICT reversal."

    def __init__(self, swing_lookback=5, atr_sl_mult=1.5, atr_tp_mult=3.0):
        self.swing_lookback = swing_lookback
        self.atr_sl_mult = atr_sl_mult
        self.atr_tp_mult = atr_tp_mult

    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        df["atr"] = atr(df)

        swing_lows = detect_swing_lows(df, self.swing_lookback)
        swing_highs = detect_swing_highs(df, self.swing_lookback)
        bullish_mss, bearish_mss = detect_market_structure_shift(df, self.swing_lookback)

        df["signal"] = 0

        # Track recent swing levels for liquidity sweeps
        recent_swing_lows = []
        recent_swing_highs = []

        for i in range(self.swing_lookback, len(df)):
            if swing_lows.iloc[i]:
                recent_swing_lows.append(df["Low"].iloc[i])
                recent_swing_lows = recent_swing_lows[-3:]
            if swing_highs.iloc[i]:
                recent_swing_highs.append(df["High"].iloc[i])
                recent_swing_highs = recent_swing_highs[-3:]

            # Bullish: sweep of lows (wick below swing low) + close back above + MSS
            if recent_swing_lows:
                swept_low = min(recent_swing_lows)
                if (df["Low"].iloc[i] < swept_low and
                    df["Close"].iloc[i] > swept_low and
                    bullish_mss.iloc[i]):
                    df.iloc[i, df.columns.get_loc("signal")] = 1

            # Bearish: sweep of highs (wick above swing high) + close back below + MSS
            if recent_swing_highs:
                swept_high = max(recent_swing_highs)
                if (df["High"].iloc[i] > swept_high and
                    df["Close"].iloc[i] < swept_high and
                    bearish_mss.iloc[i]):
                    df.iloc[i, df.columns.get_loc("signal")] = -1

        df["stop_loss"] = np.where(df["signal"] == 1, df["Close"] - self.atr_sl_mult * df["atr"],
                           np.where(df["signal"] == -1, df["Close"] + self.atr_sl_mult * df["atr"], np.nan))
        df["target"] = np.where(df["signal"] == 1, df["Close"] + self.atr_tp_mult * df["atr"],
                        np.where(df["signal"] == -1, df["Close"] - self.atr_tp_mult * df["atr"], np.nan))
        df["entry_price"] = np.where(df["signal"] != 0, df["Close"], np.nan)

        return df


# ─────────────────────────────────────────────────────────────────────────────
# STRATEGY 11: ICT OPTIMAL TRADE ENTRY (OTE)
# ─────────────────────────────────────────────────────────────────────────────

class ICTOptimalTradeEntry(Strategy):
    name = "ICT OTE (Fib)"
    description = "Buy at 62-79% Fib retracement of bullish leg after MSS. ICT's premium entry zone."

    def __init__(self, fib_low=0.62, fib_high=0.79, swing_lookback=5, atr_sl_mult=1.5, atr_tp_mult=3.0):
        self.fib_low = fib_low
        self.fib_high = fib_high
        self.swing_lookback = swing_lookback
        self.atr_sl_mult = atr_sl_mult
        self.atr_tp_mult = atr_tp_mult

    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        df["atr"] = atr(df)

        swing_highs = detect_swing_highs(df, self.swing_lookback)
        swing_lows = detect_swing_lows(df, self.swing_lookback)
        bullish_mss, bearish_mss = detect_market_structure_shift(df, self.swing_lookback)

        df["signal"] = 0

        last_swing_high = np.nan
        last_swing_low = np.nan
        bullish_mss_active = False
        bearish_mss_active = False
        mss_swing_high = np.nan
        mss_swing_low = np.nan

        for i in range(self.swing_lookback, len(df)):
            if swing_highs.iloc[i]:
                last_swing_high = df["High"].iloc[i]
            if swing_lows.iloc[i]:
                last_swing_low = df["Low"].iloc[i]

            # Detect MSS and set up OTE zone
            if bullish_mss.iloc[i] and not np.isnan(last_swing_low) and not np.isnan(last_swing_high):
                bullish_mss_active = True
                mss_swing_low = last_swing_low
                mss_swing_high = last_swing_high

            if bearish_mss.iloc[i] and not np.isnan(last_swing_low) and not np.isnan(last_swing_high):
                bearish_mss_active = True
                mss_swing_low = last_swing_low
                mss_swing_high = last_swing_high

            # Bullish OTE: price retraces to 62-79% of the bullish leg
            if bullish_mss_active:
                leg = mss_swing_high - mss_swing_low
                if leg > 0:
                    ote_upper = mss_swing_high - (self.fib_low * leg)  # 62% retracement
                    ote_lower = mss_swing_high - (self.fib_high * leg)  # 79% retracement

                    if df["Low"].iloc[i] <= ote_upper and df["Close"].iloc[i] >= ote_lower:
                        df.iloc[i, df.columns.get_loc("signal")] = 1
                        bullish_mss_active = False  # Used up

            # Bearish OTE: price retraces up to 62-79% of the bearish leg
            if bearish_mss_active:
                leg = mss_swing_high - mss_swing_low
                if leg > 0:
                    ote_lower = mss_swing_low + (self.fib_low * leg)  # 62% retracement
                    ote_upper = mss_swing_low + (self.fib_high * leg)  # 79% retracement

                    if df["High"].iloc[i] >= ote_lower and df["Close"].iloc[i] <= ote_upper:
                        df.iloc[i, df.columns.get_loc("signal")] = -1
                        bearish_mss_active = False

        df["stop_loss"] = np.where(df["signal"] == 1, df["Close"] - self.atr_sl_mult * df["atr"],
                           np.where(df["signal"] == -1, df["Close"] + self.atr_sl_mult * df["atr"], np.nan))
        df["target"] = np.where(df["signal"] == 1, df["Close"] + self.atr_tp_mult * df["atr"],
                        np.where(df["signal"] == -1, df["Close"] - self.atr_tp_mult * df["atr"], np.nan))
        df["entry_price"] = np.where(df["signal"] != 0, df["Close"], np.nan)

        return df


# ─────────────────────────────────────────────────────────────────────────────
# REGISTRY
# ─────────────────────────────────────────────────────────────────────────────

ALL_STRATEGIES = {
    # Classic Technical Analysis
    "ema_crossover": EMACrossover,
    "rsi_reversion": RSIMeanReversion,
    "macd_momentum": MACDMomentum,
    "supertrend": SupertrendStrategy,
    "bollinger_breakout": BollingerBreakout,
    "combo": ComboStrategy,
    "vwap_ema": VWAPStrategy,
    # ICT Strategies
    "ict_fvg": ICTFairValueGap,
    "ict_orderblock": ICTOrderBlock,
    "ict_liquidity": ICTLiquiditySweep,
    "ict_ote": ICTOptimalTradeEntry,
}


def get_strategy(name: str, **kwargs) -> Strategy:
    if name not in ALL_STRATEGIES:
        raise ValueError(f"Unknown strategy '{name}'. Available: {list(ALL_STRATEGIES.keys())}")
    return ALL_STRATEGIES[name](**kwargs)


def list_strategies():
    print(f"\n  {'--- Classic Technical Analysis ---':^70}")
    classic = ["ema_crossover", "rsi_reversion", "macd_momentum", "supertrend", "bollinger_breakout", "combo", "vwap_ema"]
    for key in classic:
        cls = ALL_STRATEGIES[key]
        print(f"  {key:<20} {cls.name:<25} {cls.description}")
    print(f"\n  {'--- ICT (Inner Circle Trader) ---':^70}")
    ict = ["ict_fvg", "ict_orderblock", "ict_liquidity", "ict_ote"]
    for key in ict:
        cls = ALL_STRATEGIES[key]
        print(f"  {key:<20} {cls.name:<25} {cls.description}")
