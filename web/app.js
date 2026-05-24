// ============================================================
// Indian Stock Trading Signal Dashboard - app.js
// Complete vanilla JS implementation
// ============================================================

// ────────────────────────────────────────────────────────────
// CONSTANTS
// ────────────────────────────────────────────────────────────

const NIFTY_50 = [
    'ADANIENT','ADANIPORTS','APOLLOHOSP','ASIANPAINT','AXISBANK',
    'BAJAJ-AUTO','BAJFINANCE','BAJAJFINSV','BEL','BPCL',
    'BHARTIARTL','BRITANNIA','CIPLA','COALINDIA','DIVISLAB',
    'DRREDDY','EICHERMOT','ETERNAL','GRASIM','HCLTECH',
    'HDFCBANK','HDFCLIFE','HEROMOTOCO','HINDALCO','HINDUNILVR',
    'ICICIBANK','ITC','INDUSINDBK','INFY','JSWSTEEL',
    'JIOFIN','KOTAKBANK','LT','M&M','MARUTI',
    'NESTLEIND','NTPC','ONGC','POWERGRID','RELIANCE',
    'SBILIFE','SBIN','SHRIRAMFIN','SUNPHARMA','TCS',
    'TATACONSUM','TATAMOTORS','TATASTEEL','TECHM','TITAN',
    'TRENT','ULTRACEMCO','WIPRO'
];

const BANK_NIFTY = [
    'HDFCBANK','ICICIBANK','KOTAKBANK','AXISBANK','SBIN',
    'INDUSINDBK','BANDHANBNK','FEDERALBNK','IDFCFIRSTB','PNB',
    'BANKBARODA','AUBANK'
];

const STRATEGY_INFO = {
    ema_crossover: {
        name: 'EMA Crossover',
        category: 'classic',
        description: '9/21 EMA crossover signals',
        icon: '📈',
        fn: 'strategyEMACrossover'
    },
    rsi_reversion: {
        name: 'RSI Mean Reversion',
        category: 'classic',
        description: 'RSI oversold/overbought reversals',
        icon: '🔄',
        fn: 'strategyRSIReversion'
    },
    macd_momentum: {
        name: 'MACD Momentum',
        category: 'classic',
        description: 'MACD line/signal crossover',
        icon: '📊',
        fn: 'strategyMACDMomentum'
    },
    supertrend: {
        name: 'Supertrend',
        category: 'classic',
        description: 'Supertrend direction change',
        icon: '🚀',
        fn: 'strategySupertrend'
    },
    bollinger_breakout: {
        name: 'Bollinger Breakout',
        category: 'classic',
        description: 'Bollinger Band breakout/squeeze',
        icon: '💥',
        fn: 'strategyBollingerBreakout'
    },
    combo: {
        name: 'EMA+RSI+MACD Combo',
        category: 'classic',
        description: 'Multi-indicator confirmation',
        icon: '🎯',
        fn: 'strategyCombo'
    },
    vwap_ema: {
        name: 'VWAP + EMA',
        category: 'classic',
        description: 'VWAP crossover with EMA trend',
        icon: '⚡',
        fn: 'strategyVWAPEMA'
    },
    ict_fvg: {
        name: 'ICT Fair Value Gap',
        category: 'ict',
        description: 'Fair Value Gap detection & entry',
        icon: '🕳️',
        fn: 'strategyICTFVG'
    },
    ict_orderblock: {
        name: 'ICT Order Block',
        category: 'ict',
        description: 'Institutional Order Block entries',
        icon: '🏛️',
        fn: 'strategyICTOrderBlock'
    },
    ict_liquidity: {
        name: 'ICT Liquidity Sweep',
        category: 'ict',
        description: 'Liquidity sweep + Market Structure Shift',
        icon: '🌊',
        fn: 'strategyICTLiquidity'
    },
    ict_ote: {
        name: 'ICT Optimal Trade Entry',
        category: 'ict',
        description: '62-79% Fibonacci retracement OTE',
        icon: '🎰',
        fn: 'strategyICTOTE'
    }
};

const CORS_PROXIES = [
    (url) => url,
    (url) => `https://api.allorigins.win/raw?url=${encodeURIComponent(url)}`,
    (url) => `https://corsproxy.io/?${encodeURIComponent(url)}`
];

// ────────────────────────────────────────────────────────────
// STATE
// ────────────────────────────────────────────────────────────

let currentView = 'scanner';
let scanResults = [];
let isRunning = false;
let selectedStrategies = new Set(['ema_crossover', 'supertrend', 'ict_fvg']);
let cachedData = {};

// ────────────────────────────────────────────────────────────
// UTILITY HELPERS
// ────────────────────────────────────────────────────────────

function formatIndianNumber(num) {
    if (num === null || num === undefined || isNaN(num)) return '—';
    const isNeg = num < 0;
    const absStr = Math.abs(num).toFixed(2);
    const [intPart, decPart] = absStr.split('.');
    let result = '';
    if (intPart.length <= 3) {
        result = intPart;
    } else {
        result = intPart.slice(-3);
        let remaining = intPart.slice(0, -3);
        while (remaining.length > 2) {
            result = remaining.slice(-2) + ',' + result;
            remaining = remaining.slice(0, -2);
        }
        if (remaining.length > 0) {
            result = remaining + ',' + result;
        }
    }
    return (isNeg ? '-' : '') + result + '.' + decPart;
}

function formatRupee(num) {
    if (num === null || num === undefined || isNaN(num)) return '—';
    return '₹' + formatIndianNumber(num);
}

function formatPct(num) {
    if (num === null || num === undefined || isNaN(num)) return '—';
    return num.toFixed(2) + '%';
}

function sleep(ms) {
    return new Promise(resolve => setTimeout(resolve, ms));
}

function clamp(val, min, max) {
    return Math.max(min, Math.min(max, val));
}

// ────────────────────────────────────────────────────────────
// DATA FETCHING
// ────────────────────────────────────────────────────────────

async function fetchWithProxy(url) {
    for (let i = 0; i < CORS_PROXIES.length; i++) {
        try {
            const proxyUrl = CORS_PROXIES[i](url);
            const response = await fetch(proxyUrl, { signal: AbortSignal.timeout(15000) });
            if (!response.ok) continue;
            const data = await response.json();
            return data;
        } catch (e) {
            if (i === CORS_PROXIES.length - 1) throw e;
        }
    }
    throw new Error('All proxies failed');
}

async function fetchStockData(symbol, period = '1y', interval = '1d') {
    const cleanSymbol = symbol.replace(/\.(NS|BO)$/i, '').toUpperCase();
    const cacheKey = `${cleanSymbol}_${period}_${interval}`;
    if (cachedData[cacheKey]) return cachedData[cacheKey];

    const suffixes = ['.NS', '.BO'];
    let lastErr = null;

    for (const suffix of suffixes) {
        try {
            const ticker = cleanSymbol + suffix;
            const url = `https://query1.finance.yahoo.com/v8/finance/chart/${ticker}?range=${period}&interval=${interval}`;
            const json = await fetchWithProxy(url);

            const result = json.chart?.result?.[0];
            if (!result || !result.timestamp || result.timestamp.length === 0) continue;

            const timestamps = result.timestamp;
            const quote = result.indicators?.quote?.[0];
            if (!quote) continue;

            const dates = [];
            const open = [];
            const high = [];
            const low = [];
            const close = [];
            const volume = [];

            for (let i = 0; i < timestamps.length; i++) {
                if (quote.close[i] === null || quote.close[i] === undefined) continue;
                dates.push(new Date(timestamps[i] * 1000));
                open.push(quote.open[i] ?? quote.close[i]);
                high.push(quote.high[i] ?? quote.close[i]);
                low.push(quote.low[i] ?? quote.close[i]);
                close.push(quote.close[i]);
                volume.push(quote.volume[i] ?? 0);
            }

            if (close.length < 5) continue;

            const data = { symbol: cleanSymbol, dates, open, high, low, close, volume };
            cachedData[cacheKey] = data;
            return data;
        } catch (e) {
            lastErr = e;
        }
    }

    throw new Error(`Failed to fetch ${cleanSymbol}: ${lastErr?.message || 'Unknown error'}`);
}

// ────────────────────────────────────────────────────────────
// TECHNICAL INDICATORS
// ────────────────────────────────────────────────────────────

function calcSMA(data, period) {
    const result = new Array(data.length).fill(null);
    for (let i = period - 1; i < data.length; i++) {
        let sum = 0;
        for (let j = 0; j < period; j++) {
            sum += data[i - j];
        }
        result[i] = sum / period;
    }
    return result;
}

function calcEMA(data, period) {
    const result = new Array(data.length).fill(null);
    const k = 2 / (period + 1);
    let seed = 0;
    for (let i = 0; i < period; i++) {
        seed += data[i];
    }
    seed /= period;
    result[period - 1] = seed;
    for (let i = period; i < data.length; i++) {
        result[i] = data[i] * k + result[i - 1] * (1 - k);
    }
    return result;
}

function calcRSI(close, period = 14) {
    const result = new Array(close.length).fill(null);
    if (close.length < period + 1) return result;

    let gainSum = 0;
    let lossSum = 0;

    for (let i = 1; i <= period; i++) {
        const change = close[i] - close[i - 1];
        if (change >= 0) gainSum += change;
        else lossSum += Math.abs(change);
    }

    let avgGain = gainSum / period;
    let avgLoss = lossSum / period;

    result[period] = avgLoss === 0 ? 100 : 100 - (100 / (1 + avgGain / avgLoss));

    for (let i = period + 1; i < close.length; i++) {
        const change = close[i] - close[i - 1];
        const gain = change >= 0 ? change : 0;
        const loss = change < 0 ? Math.abs(change) : 0;

        avgGain = (avgGain * (period - 1) + gain) / period;
        avgLoss = (avgLoss * (period - 1) + loss) / period;

        result[i] = avgLoss === 0 ? 100 : 100 - (100 / (1 + avgGain / avgLoss));
    }
    return result;
}

function calcMACD(close, fast = 12, slow = 26, signalP = 9) {
    const emaFast = calcEMA(close, fast);
    const emaSlow = calcEMA(close, slow);

    const macdLine = new Array(close.length).fill(null);
    for (let i = 0; i < close.length; i++) {
        if (emaFast[i] !== null && emaSlow[i] !== null) {
            macdLine[i] = emaFast[i] - emaSlow[i];
        }
    }

    const validMACD = [];
    const validIdxs = [];
    for (let i = 0; i < macdLine.length; i++) {
        if (macdLine[i] !== null) {
            validMACD.push(macdLine[i]);
            validIdxs.push(i);
        }
    }

    const signalEMA = calcEMA(validMACD, signalP);

    const signalLine = new Array(close.length).fill(null);
    const histogram = new Array(close.length).fill(null);

    for (let j = 0; j < validIdxs.length; j++) {
        const idx = validIdxs[j];
        if (signalEMA[j] !== null) {
            signalLine[idx] = signalEMA[j];
            histogram[idx] = macdLine[idx] - signalEMA[j];
        }
    }

    return { macd: macdLine, signal: signalLine, histogram };
}

function calcATR(high, low, close, period = 14) {
    const tr = new Array(close.length).fill(0);
    tr[0] = high[0] - low[0];

    for (let i = 1; i < close.length; i++) {
        const hl = high[i] - low[i];
        const hc = Math.abs(high[i] - close[i - 1]);
        const lc = Math.abs(low[i] - close[i - 1]);
        tr[i] = Math.max(hl, hc, lc);
    }

    const atr = new Array(close.length).fill(null);
    let sum = 0;
    for (let i = 0; i < period; i++) {
        sum += tr[i];
    }
    atr[period - 1] = sum / period;

    for (let i = period; i < close.length; i++) {
        atr[i] = (atr[i - 1] * (period - 1) + tr[i]) / period;
    }
    return atr;
}

function calcSupertrend(high, low, close, period = 10, mult = 3) {
    const atr = calcATR(high, low, close, period);
    const len = close.length;
    const supertrend = new Array(len).fill(null);
    const direction = new Array(len).fill(0); // 1 = up (bullish), -1 = down (bearish)

    const upperBand = new Array(len).fill(null);
    const lowerBand = new Array(len).fill(null);

    for (let i = 0; i < len; i++) {
        if (atr[i] === null) continue;
        const mid = (high[i] + low[i]) / 2;
        upperBand[i] = mid + mult * atr[i];
        lowerBand[i] = mid - mult * atr[i];
    }

    let prevUpper = upperBand[period - 1];
    let prevLower = lowerBand[period - 1];
    direction[period - 1] = close[period - 1] > prevUpper ? 1 : -1;
    supertrend[period - 1] = direction[period - 1] === 1 ? prevLower : prevUpper;

    for (let i = period; i < len; i++) {
        if (upperBand[i] === null) continue;

        if (lowerBand[i] > prevLower) {
            lowerBand[i] = lowerBand[i];
        } else {
            lowerBand[i] = prevLower;
        }

        if (upperBand[i] < prevUpper) {
            upperBand[i] = upperBand[i];
        } else {
            upperBand[i] = prevUpper;
        }

        if (direction[i - 1] === 1) {
            if (close[i] < lowerBand[i]) {
                direction[i] = -1;
                supertrend[i] = upperBand[i];
            } else {
                direction[i] = 1;
                supertrend[i] = lowerBand[i];
            }
        } else {
            if (close[i] > upperBand[i]) {
                direction[i] = 1;
                supertrend[i] = lowerBand[i];
            } else {
                direction[i] = -1;
                supertrend[i] = upperBand[i];
            }
        }

        prevUpper = upperBand[i];
        prevLower = lowerBand[i];
    }

    return { supertrend, direction };
}

function calcBollingerBands(close, period = 20, stdDev = 2) {
    const mid = calcSMA(close, period);
    const upper = new Array(close.length).fill(null);
    const lower = new Array(close.length).fill(null);

    for (let i = period - 1; i < close.length; i++) {
        let sumSq = 0;
        for (let j = 0; j < period; j++) {
            sumSq += Math.pow(close[i - j] - mid[i], 2);
        }
        const sd = Math.sqrt(sumSq / period);
        upper[i] = mid[i] + stdDev * sd;
        lower[i] = mid[i] - stdDev * sd;
    }
    return { upper, mid, lower };
}

function calcVWAP(high, low, close, volume) {
    const vwap = new Array(close.length).fill(null);
    let cumVol = 0;
    let cumTP = 0;

    for (let i = 0; i < close.length; i++) {
        const tp = (high[i] + low[i] + close[i]) / 3;
        cumVol += volume[i];
        cumTP += tp * volume[i];
        vwap[i] = cumVol > 0 ? cumTP / cumVol : tp;
    }
    return vwap;
}

// ────────────────────────────────────────────────────────────
// ICT HELPERS
// ────────────────────────────────────────────────────────────

function detectSwingHighs(high, lookback = 5) {
    const swings = [];
    for (let i = lookback; i < high.length - lookback; i++) {
        let isSwingHigh = true;
        for (let j = 1; j <= lookback; j++) {
            if (high[i] <= high[i - j] || high[i] <= high[i + j]) {
                isSwingHigh = false;
                break;
            }
        }
        if (isSwingHigh) {
            swings.push({ index: i, price: high[i] });
        }
    }
    return swings;
}

function detectSwingLows(low, lookback = 5) {
    const swings = [];
    for (let i = lookback; i < low.length - lookback; i++) {
        let isSwingLow = true;
        for (let j = 1; j <= lookback; j++) {
            if (low[i] >= low[i - j] || low[i] >= low[i + j]) {
                isSwingLow = false;
                break;
            }
        }
        if (isSwingLow) {
            swings.push({ index: i, price: low[i] });
        }
    }
    return swings;
}

function detectFVG(high, low, close) {
    const fvgs = [];
    for (let i = 2; i < close.length; i++) {
        // Bullish FVG: candle[i] low > candle[i-2] high (gap up)
        if (low[i] > high[i - 2]) {
            fvgs.push({
                index: i,
                type: 'bullish',
                top: low[i],
                bottom: high[i - 2],
                mid: (low[i] + high[i - 2]) / 2
            });
        }
        // Bearish FVG: candle[i] high < candle[i-2] low (gap down)
        if (high[i] < low[i - 2]) {
            fvgs.push({
                index: i,
                type: 'bearish',
                top: low[i - 2],
                bottom: high[i],
                mid: (low[i - 2] + high[i]) / 2
            });
        }
    }
    return fvgs;
}

function detectOrderBlocks(open, high, low, close, atr) {
    const obs = [];
    for (let i = 2; i < close.length - 1; i++) {
        if (atr[i] === null) continue;
        const currentRange = high[i] - low[i];
        // Strong move away (next candle is big impulsive)
        const nextRange = high[i + 1] - low[i + 1];
        const isBigMove = nextRange > 1.5 * atr[i];

        // Bullish OB: last bearish candle before a big bullish move
        if (close[i] < open[i] && close[i + 1] > open[i + 1] && isBigMove) {
            obs.push({
                index: i,
                type: 'bullish',
                top: open[i],
                bottom: low[i],
                breakCandle: i + 1
            });
        }
        // Bearish OB: last bullish candle before a big bearish move
        if (close[i] > open[i] && close[i + 1] < open[i + 1] && isBigMove) {
            obs.push({
                index: i,
                type: 'bearish',
                top: high[i],
                bottom: open[i],
                breakCandle: i + 1
            });
        }
    }
    return obs;
}

function detectMSS(high, low, close, lookback = 5) {
    const shifts = [];
    const swingHighs = detectSwingHighs(high, lookback);
    const swingLows = detectSwingLows(low, lookback);

    // Bullish MSS: price breaks above a recent swing high after making lower lows
    for (let i = 1; i < swingHighs.length; i++) {
        const sh = swingHighs[i];
        // Look for bar that closes above this swing high
        for (let j = sh.index + 1; j < Math.min(sh.index + lookback * 2, close.length); j++) {
            if (close[j] > sh.price) {
                // Check that there was a recent lower low
                const recentLows = swingLows.filter(sl => sl.index > swingHighs[i - 1].index && sl.index < j);
                if (recentLows.length > 0) {
                    shifts.push({
                        index: j,
                        type: 'bullish',
                        level: sh.price,
                        swingIndex: sh.index
                    });
                }
                break;
            }
        }
    }

    // Bearish MSS: price breaks below a recent swing low after making higher highs
    for (let i = 1; i < swingLows.length; i++) {
        const sl = swingLows[i];
        for (let j = sl.index + 1; j < Math.min(sl.index + lookback * 2, close.length); j++) {
            if (close[j] < sl.price) {
                const recentHighs = swingHighs.filter(sh => sh.index > swingLows[i - 1].index && sh.index < j);
                if (recentHighs.length > 0) {
                    shifts.push({
                        index: j,
                        type: 'bearish',
                        level: sl.price,
                        swingIndex: sl.index
                    });
                }
                break;
            }
        }
    }

    return shifts;
}

// ────────────────────────────────────────────────────────────
// STRATEGIES
// ────────────────────────────────────────────────────────────

function strategyEMACrossover(data, fastP = 9, slowP = 21) {
    const signals = [];
    const { close, high, low } = data;
    const emaFast = calcEMA(close, fastP);
    const emaSlow = calcEMA(close, slowP);
    const atr = calcATR(high, low, close, 14);

    for (let i = slowP + 1; i < close.length; i++) {
        if (emaFast[i] === null || emaSlow[i] === null || emaFast[i - 1] === null || emaSlow[i - 1] === null) continue;
        if (atr[i] === null) continue;

        // Bullish crossover
        if (emaFast[i - 1] <= emaSlow[i - 1] && emaFast[i] > emaSlow[i]) {
            const entry = close[i];
            const sl = entry - 1.5 * atr[i];
            const target = entry + 2.0 * atr[i];
            signals.push({ index: i, signal: 1, entryPrice: entry, stopLoss: sl, target });
        }
        // Bearish crossover
        if (emaFast[i - 1] >= emaSlow[i - 1] && emaFast[i] < emaSlow[i]) {
            const entry = close[i];
            const sl = entry + 1.5 * atr[i];
            const target = entry - 2.0 * atr[i];
            signals.push({ index: i, signal: -1, entryPrice: entry, stopLoss: sl, target });
        }
    }
    return signals;
}

function strategyRSIReversion(data, period = 14, oversold = 30, overbought = 70) {
    const signals = [];
    const { close, high, low } = data;
    const rsi = calcRSI(close, period);
    const atr = calcATR(high, low, close, 14);

    for (let i = period + 2; i < close.length; i++) {
        if (rsi[i] === null || rsi[i - 1] === null || atr[i] === null) continue;

        // Buy: RSI crosses above oversold from below
        if (rsi[i - 1] < oversold && rsi[i] >= oversold) {
            const entry = close[i];
            const sl = entry - 2 * atr[i];
            const target = entry + 3 * atr[i];
            signals.push({ index: i, signal: 1, entryPrice: entry, stopLoss: sl, target });
        }
        // Sell: RSI crosses below overbought from above
        if (rsi[i - 1] > overbought && rsi[i] <= overbought) {
            const entry = close[i];
            const sl = entry + 2 * atr[i];
            const target = entry - 3 * atr[i];
            signals.push({ index: i, signal: -1, entryPrice: entry, stopLoss: sl, target });
        }
    }
    return signals;
}

function strategyMACDMomentum(data) {
    const signals = [];
    const { close, high, low } = data;
    const { macd, signal: sig, histogram } = calcMACD(close);
    const atr = calcATR(high, low, close, 14);

    for (let i = 27; i < close.length; i++) {
        if (macd[i] === null || sig[i] === null || macd[i - 1] === null || sig[i - 1] === null) continue;
        if (atr[i] === null) continue;

        // Bullish: MACD crosses above signal
        if (macd[i - 1] <= sig[i - 1] && macd[i] > sig[i]) {
            const entry = close[i];
            const sl = entry - 1.5 * atr[i];
            const target = entry + 2.5 * atr[i];
            signals.push({ index: i, signal: 1, entryPrice: entry, stopLoss: sl, target });
        }
        // Bearish: MACD crosses below signal
        if (macd[i - 1] >= sig[i - 1] && macd[i] < sig[i]) {
            const entry = close[i];
            const sl = entry + 1.5 * atr[i];
            const target = entry - 2.5 * atr[i];
            signals.push({ index: i, signal: -1, entryPrice: entry, stopLoss: sl, target });
        }
    }
    return signals;
}

function strategySupertrend(data, period = 10, mult = 2) {
    const signals = [];
    const { close, high, low } = data;
    const { supertrend, direction } = calcSupertrend(high, low, close, period, mult);
    const atr = calcATR(high, low, close, 14);

    for (let i = period + 1; i < close.length; i++) {
        if (direction[i] === 0 || direction[i - 1] === 0 || atr[i] === null) continue;

        // Bullish: direction flips from -1 to 1
        if (direction[i - 1] === -1 && direction[i] === 1) {
            const entry = close[i];
            const sl = supertrend[i] !== null ? supertrend[i] : entry - 2 * atr[i];
            const risk = Math.abs(entry - sl);
            const target = entry + 2 * risk;
            signals.push({ index: i, signal: 1, entryPrice: entry, stopLoss: sl, target });
        }
        // Bearish: direction flips from 1 to -1
        if (direction[i - 1] === 1 && direction[i] === -1) {
            const entry = close[i];
            const sl = supertrend[i] !== null ? supertrend[i] : entry + 2 * atr[i];
            const risk = Math.abs(sl - entry);
            const target = entry - 2 * risk;
            signals.push({ index: i, signal: -1, entryPrice: entry, stopLoss: sl, target });
        }
    }
    return signals;
}

function strategyBollingerBreakout(data) {
    const signals = [];
    const { close, high, low } = data;
    const { upper, mid, lower } = calcBollingerBands(close, 20, 2);
    const atr = calcATR(high, low, close, 14);

    for (let i = 21; i < close.length; i++) {
        if (upper[i] === null || lower[i] === null || atr[i] === null) continue;
        if (upper[i - 1] === null || lower[i - 1] === null) continue;

        // Bullish: close crosses above lower band from below (mean reversion)
        if (close[i - 1] <= lower[i - 1] && close[i] > lower[i]) {
            const entry = close[i];
            const sl = entry - 1.5 * atr[i];
            const target = mid[i]; // Target the middle band
            signals.push({ index: i, signal: 1, entryPrice: entry, stopLoss: sl, target });
        }
        // Bearish: close crosses below upper band from above
        if (close[i - 1] >= upper[i - 1] && close[i] < upper[i]) {
            const entry = close[i];
            const sl = entry + 1.5 * atr[i];
            const target = mid[i];
            signals.push({ index: i, signal: -1, entryPrice: entry, stopLoss: sl, target });
        }
    }
    return signals;
}

function strategyCombo(data) {
    const signals = [];
    const { close, high, low } = data;
    const ema9 = calcEMA(close, 9);
    const ema21 = calcEMA(close, 21);
    const rsi = calcRSI(close, 14);
    const { macd, signal: sig } = calcMACD(close);
    const atr = calcATR(high, low, close, 14);

    for (let i = 27; i < close.length; i++) {
        if (ema9[i] === null || ema21[i] === null || rsi[i] === null || macd[i] === null || sig[i] === null || atr[i] === null) continue;

        const emaBullish = ema9[i] > ema21[i];
        const emaBearish = ema9[i] < ema21[i];
        const rsiBull = rsi[i] > 40 && rsi[i] < 70;
        const rsiBear = rsi[i] < 60 && rsi[i] > 30;
        const macdBull = macd[i] > sig[i];
        const macdBear = macd[i] < sig[i];

        // Only detect fresh crossovers for entry timing
        const emaCross = ema9[i - 1] !== null && ema21[i - 1] !== null;
        const freshBullCross = emaCross && ema9[i - 1] <= ema21[i - 1] && ema9[i] > ema21[i];
        const freshBearCross = emaCross && ema9[i - 1] >= ema21[i - 1] && ema9[i] < ema21[i];

        const macdCross = macd[i - 1] !== null && sig[i - 1] !== null;
        const freshMACDBull = macdCross && macd[i - 1] <= sig[i - 1] && macd[i] > sig[i];
        const freshMACDBear = macdCross && macd[i - 1] >= sig[i - 1] && macd[i] < sig[i];

        // Bullish combo: EMA bullish crossover + RSI supportive + MACD bullish
        if ((freshBullCross || freshMACDBull) && emaBullish && rsiBull && macdBull) {
            const entry = close[i];
            const sl = entry - 2 * atr[i];
            const target = entry + 3 * atr[i];
            signals.push({ index: i, signal: 1, entryPrice: entry, stopLoss: sl, target });
        }

        // Bearish combo
        if ((freshBearCross || freshMACDBear) && emaBearish && rsiBear && macdBear) {
            const entry = close[i];
            const sl = entry + 2 * atr[i];
            const target = entry - 3 * atr[i];
            signals.push({ index: i, signal: -1, entryPrice: entry, stopLoss: sl, target });
        }
    }
    return signals;
}

function strategyVWAPEMA(data) {
    const signals = [];
    const { close, high, low, volume } = data;
    const vwap = calcVWAP(high, low, close, volume);
    const ema20 = calcEMA(close, 20);
    const atr = calcATR(high, low, close, 14);

    for (let i = 21; i < close.length; i++) {
        if (vwap[i] === null || ema20[i] === null || atr[i] === null) continue;
        if (vwap[i - 1] === null || ema20[i - 1] === null) continue;

        // Bullish: price crosses above VWAP while EMA is trending up
        const priceCrossAboveVWAP = close[i - 1] <= vwap[i - 1] && close[i] > vwap[i];
        const emaTrendUp = ema20[i] > ema20[i - 1];

        if (priceCrossAboveVWAP && emaTrendUp) {
            const entry = close[i];
            const sl = Math.min(vwap[i], entry - 1.5 * atr[i]);
            const target = entry + 2.5 * atr[i];
            signals.push({ index: i, signal: 1, entryPrice: entry, stopLoss: sl, target });
        }

        // Bearish: price crosses below VWAP while EMA is trending down
        const priceCrossBelowVWAP = close[i - 1] >= vwap[i - 1] && close[i] < vwap[i];
        const emaTrendDown = ema20[i] < ema20[i - 1];

        if (priceCrossBelowVWAP && emaTrendDown) {
            const entry = close[i];
            const sl = Math.max(vwap[i], entry + 1.5 * atr[i]);
            const target = entry - 2.5 * atr[i];
            signals.push({ index: i, signal: -1, entryPrice: entry, stopLoss: sl, target });
        }
    }
    return signals;
}

function strategyICTFVG(data) {
    const signals = [];
    const { open, high, low, close } = data;
    const atr = calcATR(high, low, close, 14);
    const fvgs = detectFVG(high, low, close);

    for (const fvg of fvgs) {
        const i = fvg.index;
        if (atr[i] === null) continue;

        // Look for price to return into the FVG zone within the next 10 bars
        for (let j = i + 1; j < Math.min(i + 10, close.length); j++) {
            if (fvg.type === 'bullish') {
                // Price dips into the FVG zone
                if (low[j] <= fvg.top && low[j] >= fvg.bottom) {
                    const entry = fvg.mid;
                    const sl = fvg.bottom - 0.5 * atr[i];
                    const risk = Math.abs(entry - sl);
                    const target = entry + 2 * risk;
                    signals.push({ index: j, signal: 1, entryPrice: entry, stopLoss: sl, target });
                    break;
                }
            } else {
                // Price rallies into the FVG zone
                if (high[j] >= fvg.bottom && high[j] <= fvg.top) {
                    const entry = fvg.mid;
                    const sl = fvg.top + 0.5 * atr[i];
                    const risk = Math.abs(sl - entry);
                    const target = entry - 2 * risk;
                    signals.push({ index: j, signal: -1, entryPrice: entry, stopLoss: sl, target });
                    break;
                }
            }
        }
    }
    return signals;
}

function strategyICTOrderBlock(data) {
    const signals = [];
    const { open, high, low, close } = data;
    const atr = calcATR(high, low, close, 14);
    const obs = detectOrderBlocks(open, high, low, close, atr);

    for (const ob of obs) {
        const i = ob.breakCandle;
        if (i >= close.length || atr[i] === null) continue;

        // Look for price to retrace into OB zone within next 15 bars
        for (let j = i + 1; j < Math.min(i + 15, close.length); j++) {
            if (ob.type === 'bullish') {
                if (low[j] <= ob.top && low[j] >= ob.bottom) {
                    const entry = (ob.top + ob.bottom) / 2;
                    const sl = ob.bottom - 0.5 * atr[i];
                    const risk = Math.abs(entry - sl);
                    const target = entry + 2.5 * risk;
                    signals.push({ index: j, signal: 1, entryPrice: entry, stopLoss: sl, target });
                    break;
                }
            } else {
                if (high[j] >= ob.bottom && high[j] <= ob.top) {
                    const entry = (ob.top + ob.bottom) / 2;
                    const sl = ob.top + 0.5 * atr[i];
                    const risk = Math.abs(sl - entry);
                    const target = entry - 2.5 * risk;
                    signals.push({ index: j, signal: -1, entryPrice: entry, stopLoss: sl, target });
                    break;
                }
            }
        }
    }
    return signals;
}

function strategyICTLiquidity(data) {
    const signals = [];
    const { open, high, low, close } = data;
    const atr = calcATR(high, low, close, 14);
    const mssShifts = detectMSS(high, low, close, 5);
    const swingHighs = detectSwingHighs(high, 5);
    const swingLows = detectSwingLows(low, 5);

    for (const mss of mssShifts) {
        const i = mss.index;
        if (i >= close.length || atr[i] === null) continue;

        if (mss.type === 'bullish') {
            // Look for a liquidity sweep below a recent swing low before the MSS
            const recentLows = swingLows.filter(sl => sl.index < i && sl.index > i - 20);
            const swept = recentLows.find(sl => {
                // Was the low taken out before the MSS?
                for (let k = sl.index + 1; k <= i; k++) {
                    if (low[k] < sl.price) return true;
                }
                return false;
            });

            if (swept) {
                const entry = close[i];
                const sl = swept.price - 0.5 * atr[i];
                const risk = Math.abs(entry - sl);
                const target = entry + 2.5 * risk;
                signals.push({ index: i, signal: 1, entryPrice: entry, stopLoss: sl, target });
            }
        } else {
            // Bearish: liquidity sweep above a swing high
            const recentHighs = swingHighs.filter(sh => sh.index < i && sh.index > i - 20);
            const swept = recentHighs.find(sh => {
                for (let k = sh.index + 1; k <= i; k++) {
                    if (high[k] > sh.price) return true;
                }
                return false;
            });

            if (swept) {
                const entry = close[i];
                const sl = swept.price + 0.5 * atr[i];
                const risk = Math.abs(sl - entry);
                const target = entry - 2.5 * risk;
                signals.push({ index: i, signal: -1, entryPrice: entry, stopLoss: sl, target });
            }
        }
    }
    return signals;
}

function strategyICTOTE(data) {
    const signals = [];
    const { high, low, close } = data;
    const atr = calcATR(high, low, close, 14);
    const swingHighs = detectSwingHighs(high, 5);
    const swingLows = detectSwingLows(low, 5);

    // Find swing pairs and compute OTE zone (62%-79% Fib retracement)
    for (let i = 0; i < swingLows.length; i++) {
        // Bullish OTE: after a swing low, swing high, then retrace to 62-79%
        const sl = swingLows[i];
        // Find next swing high after this low
        const nextSH = swingHighs.find(sh => sh.index > sl.index);
        if (!nextSH) continue;

        const range = nextSH.price - sl.price;
        if (range <= 0) continue;

        const oteTop = nextSH.price - 0.618 * range; // 61.8% retracement level
        const oteBottom = nextSH.price - 0.79 * range; // 79% retracement level

        // Look for price entering OTE zone after the swing high
        for (let j = nextSH.index + 1; j < Math.min(nextSH.index + 15, close.length); j++) {
            if (atr[j] === null) continue;
            if (low[j] <= oteTop && low[j] >= oteBottom) {
                const entry = (oteTop + oteBottom) / 2;
                const stopLoss = oteBottom - 0.5 * atr[j];
                const risk = Math.abs(entry - stopLoss);
                const target = nextSH.price + 0.5 * risk; // Target above previous swing high
                signals.push({ index: j, signal: 1, entryPrice: entry, stopLoss, target });
                break;
            }
        }
    }

    for (let i = 0; i < swingHighs.length; i++) {
        // Bearish OTE: after a swing high, swing low, then retrace up to 62-79%
        const sh = swingHighs[i];
        const nextSL = swingLows.find(sl => sl.index > sh.index);
        if (!nextSL) continue;

        const range = sh.price - nextSL.price;
        if (range <= 0) continue;

        const oteBottom = nextSL.price + 0.618 * range; // 61.8% retracement
        const oteTop = nextSL.price + 0.79 * range; // 79% retracement

        for (let j = nextSL.index + 1; j < Math.min(nextSL.index + 15, close.length); j++) {
            if (atr[j] === null) continue;
            if (high[j] >= oteBottom && high[j] <= oteTop) {
                const entry = (oteTop + oteBottom) / 2;
                const stopLoss = oteTop + 0.5 * atr[j];
                const risk = Math.abs(stopLoss - entry);
                const target = nextSL.price - 0.5 * risk;
                signals.push({ index: j, signal: -1, entryPrice: entry, stopLoss, target });
                break;
            }
        }
    }

    return signals;
}

// Map from strategy key to function
const STRATEGY_FUNCTIONS = {
    ema_crossover: strategyEMACrossover,
    rsi_reversion: strategyRSIReversion,
    macd_momentum: strategyMACDMomentum,
    supertrend: strategySupertrend,
    bollinger_breakout: strategyBollingerBreakout,
    combo: strategyCombo,
    vwap_ema: strategyVWAPEMA,
    ict_fvg: strategyICTFVG,
    ict_orderblock: strategyICTOrderBlock,
    ict_liquidity: strategyICTLiquidity,
    ict_ote: strategyICTOTE
};

// ────────────────────────────────────────────────────────────
// BACKTESTER
// ────────────────────────────────────────────────────────────

function runBacktest(signals, data, capital = 100000, commissionPct = 0.05) {
    const trades = [];
    const equityCurve = [{ index: 0, equity: capital }];
    let currentCapital = capital;
    let peakEquity = capital;

    const { close, high, low, dates } = data;
    const positionSize = 0.1; // Risk 10% per trade

    for (const sig of signals) {
        if (sig.index >= close.length) continue;

        const entry = sig.entryPrice;
        const sl = sig.stopLoss;
        const target = sig.target;
        const risk = Math.abs(entry - sl);
        if (risk <= 0) continue;

        const tradeCapital = currentCapital * positionSize;
        const qty = Math.floor(tradeCapital / entry);
        if (qty <= 0) continue;

        const commission = entry * qty * (commissionPct / 100);
        let exitPrice = null;
        let exitIndex = null;
        let exitReason = 'open';

        // Simulate forward
        for (let j = sig.index + 1; j < close.length; j++) {
            if (sig.signal === 1) {
                // Long trade
                if (low[j] <= sl) {
                    exitPrice = sl;
                    exitIndex = j;
                    exitReason = 'SL';
                    break;
                }
                if (high[j] >= target) {
                    exitPrice = target;
                    exitIndex = j;
                    exitReason = 'Target';
                    break;
                }
            } else {
                // Short trade
                if (high[j] >= sl) {
                    exitPrice = sl;
                    exitIndex = j;
                    exitReason = 'SL';
                    break;
                }
                if (low[j] <= target) {
                    exitPrice = target;
                    exitIndex = j;
                    exitReason = 'Target';
                    break;
                }
            }
        }

        // If trade never closed, use last close
        if (exitPrice === null) {
            exitPrice = close[close.length - 1];
            exitIndex = close.length - 1;
            exitReason = 'Open';
        }

        const exitCommission = exitPrice * qty * (commissionPct / 100);
        const grossPnL = sig.signal === 1
            ? (exitPrice - entry) * qty
            : (entry - exitPrice) * qty;
        const netPnL = grossPnL - commission - exitCommission;
        const pnlPct = (netPnL / tradeCapital) * 100;
        const plannedRR = risk > 0 ? Math.abs(target - entry) / risk : 0;
        const realizedRR = risk > 0 ? (sig.signal === 1 ? (exitPrice - entry) / risk : (entry - exitPrice) / risk) : 0;

        currentCapital += netPnL;
        peakEquity = Math.max(peakEquity, currentCapital);

        trades.push({
            entryIndex: sig.index,
            exitIndex,
            signal: sig.signal,
            entryPrice: entry,
            exitPrice,
            stopLoss: sl,
            target,
            qty,
            grossPnL,
            netPnL,
            pnlPct,
            exitReason,
            plannedRR,
            realizedRR,
            entryDate: dates[sig.index],
            exitDate: dates[exitIndex]
        });

        equityCurve.push({
            index: exitIndex,
            equity: currentCapital,
            date: dates[exitIndex]
        });
    }

    // Compute metrics
    const wins = trades.filter(t => t.netPnL > 0);
    const losses = trades.filter(t => t.netPnL <= 0);
    const totalReturn = ((currentCapital - capital) / capital) * 100;
    const winRate = trades.length > 0 ? (wins.length / trades.length) * 100 : 0;
    const avgWin = wins.length > 0 ? wins.reduce((s, t) => s + t.pnlPct, 0) / wins.length : 0;
    const avgLoss = losses.length > 0 ? Math.abs(losses.reduce((s, t) => s + t.pnlPct, 0) / losses.length) : 0;
    const grossProfit = wins.reduce((s, t) => s + t.netPnL, 0);
    const grossLoss = Math.abs(losses.reduce((s, t) => s + t.netPnL, 0));
    const profitFactor = grossLoss > 0 ? grossProfit / grossLoss : grossProfit > 0 ? Infinity : 0;

    // Max drawdown
    let maxDD = 0;
    let peak = capital;
    for (const pt of equityCurve) {
        peak = Math.max(peak, pt.equity);
        const dd = ((peak - pt.equity) / peak) * 100;
        maxDD = Math.max(maxDD, dd);
    }

    // Sharpe ratio (annualized, assuming 252 trading days)
    const returns = [];
    for (let i = 1; i < equityCurve.length; i++) {
        const r = (equityCurve[i].equity - equityCurve[i - 1].equity) / equityCurve[i - 1].equity;
        returns.push(r);
    }
    let sharpe = 0;
    if (returns.length > 1) {
        const meanR = returns.reduce((a, b) => a + b, 0) / returns.length;
        const stdR = Math.sqrt(returns.reduce((s, r) => s + Math.pow(r - meanR, 2), 0) / (returns.length - 1));
        sharpe = stdR > 0 ? (meanR / stdR) * Math.sqrt(252) : 0;
    }

    const avgPlannedRR = trades.length > 0 ? trades.reduce((s, t) => s + t.plannedRR, 0) / trades.length : 0;
    const avgRealizedRR = trades.length > 0 ? trades.reduce((s, t) => s + t.realizedRR, 0) / trades.length : 0;
    const riskReward = avgLoss > 0 ? avgWin / avgLoss : 0;

    const metrics = {
        totalReturn,
        winRate,
        profitFactor,
        sharpeRatio: sharpe,
        maxDrawdown: maxDD,
        totalTrades: trades.length,
        avgWin,
        avgLoss,
        riskReward,
        plannedRR: avgPlannedRR,
        realizedRR: avgRealizedRR,
        finalCapital: currentCapital,
        totalWins: wins.length,
        totalLosses: losses.length
    };

    return { trades, equityCurve, metrics };
}

// ────────────────────────────────────────────────────────────
// SCANNER
// ────────────────────────────────────────────────────────────

async function runScanner(stocks, mode) {
    if (isRunning) {
        showToast('Scanner is already running!', 'warning');
        return;
    }
    isRunning = true;
    scanResults = [];

    const progressBar = document.getElementById('scanProgress');
    const progressFill = document.getElementById('scanProgressFill');
    const progressText = document.getElementById('scanProgressText');
    const resultsContainer = document.getElementById('scanResultsBody');
    const runBtn = document.getElementById('runBtn');

    if (progressBar) progressBar.style.display = 'block';
    if (runBtn) {
        runBtn.disabled = true;
        runBtn.innerHTML = '<span class="spinner-small"></span> Scanning...';
    }
    if (resultsContainer) resultsContainer.innerHTML = '';

    const activeStrategies = getActiveStrategies();
    if (activeStrategies.length === 0) {
        showToast('Please select at least one strategy', 'error');
        isRunning = false;
        resetRunButton();
        return;
    }

    let completed = 0;
    const total = stocks.length;

    for (let s = 0; s < stocks.length; s++) {
        const symbol = stocks[s].trim().toUpperCase();
        if (!symbol) { completed++; continue; }

        try {
            if (progressText) progressText.textContent = `Scanning ${symbol} (${s + 1}/${total})`;
            if (progressFill) progressFill.style.width = `${((s + 1) / total) * 100}%`;

            const data = await fetchStockData(symbol, mode === 'intraday' ? '5d' : '1y', mode === 'intraday' ? '15m' : '1d');

            const stratResults = {};
            let bullCount = 0;
            let bearCount = 0;
            let latestSignal = null;
            let latestSignalTime = -1;

            for (const key of activeStrategies) {
                const fn = STRATEGY_FUNCTIONS[key];
                if (!fn) continue;
                try {
                    const signals = fn(data);
                    stratResults[key] = signals;

                    // Get the latest signal for this strategy
                    if (signals.length > 0) {
                        const lastSig = signals[signals.length - 1];
                        // Only count recent signals (within last 5 bars)
                        if (lastSig.index >= data.close.length - 5) {
                            if (lastSig.signal === 1) bullCount++;
                            else if (lastSig.signal === -1) bearCount++;

                            if (lastSig.index > latestSignalTime) {
                                latestSignalTime = lastSig.index;
                                latestSignal = lastSig;
                            }
                        }
                    }
                } catch (e) {
                    stratResults[key] = [];
                }
            }

            const totalActive = activeStrategies.length;
            const compositeScore = ((bullCount - bearCount) / totalActive) * 100;
            const lastClose = data.close[data.close.length - 1];
            const prevClose = data.close[data.close.length - 2] || lastClose;
            const changePct = ((lastClose - prevClose) / prevClose) * 100;

            scanResults.push({
                symbol,
                lastClose,
                changePct,
                compositeScore,
                bullCount,
                bearCount,
                totalStrategies: totalActive,
                latestSignal,
                stratResults,
                data
            });

            updateScanResults(scanResults);

        } catch (e) {
            scanResults.push({
                symbol,
                lastClose: null,
                changePct: null,
                compositeScore: 0,
                bullCount: 0,
                bearCount: 0,
                totalStrategies: activeStrategies.length,
                latestSignal: null,
                stratResults: {},
                data: null,
                error: e.message
            });
            updateScanResults(scanResults);
        }

        completed++;
        // Rate limiting
        if (s < stocks.length - 1) await sleep(500);
    }

    if (progressBar) progressBar.style.display = 'none';
    isRunning = false;
    resetRunButton();

    const signalCount = scanResults.filter(r => r.latestSignal).length;
    showToast(`Scan complete! ${signalCount} signal${signalCount !== 1 ? 's' : ''} found across ${stocks.length} stocks.`, 'success');
}

function getActiveStrategies() {
    const checkboxes = document.querySelectorAll('.strategy-checkbox:checked');
    return Array.from(checkboxes).map(cb => cb.value);
}

function resetRunButton() {
    const runBtn = document.getElementById('runBtn');
    if (runBtn) {
        runBtn.disabled = false;
        runBtn.innerHTML = '<i class="icon">▶</i> Run Scanner';
    }
}

// ────────────────────────────────────────────────────────────
// UI FUNCTIONS
// ────────────────────────────────────────────────────────────

function showView(viewName) {
    currentView = viewName;
    const views = document.querySelectorAll('.view-panel');
    views.forEach(v => v.classList.remove('active'));

    const target = document.getElementById(`view-${viewName}`);
    if (target) target.classList.add('active');

    const tabs = document.querySelectorAll('.tab-btn');
    tabs.forEach(t => t.classList.remove('active'));

    const activeTab = document.querySelector(`.tab-btn[data-view="${viewName}"]`);
    if (activeTab) activeTab.classList.add('active');
}

function updateScanResults(results) {
    const tbody = document.getElementById('scanResultsBody');
    if (!tbody) return;

    // Sort by composite score descending
    const sorted = [...results].sort((a, b) => b.compositeScore - a.compositeScore);

    tbody.innerHTML = sorted.map((r, idx) => {
        if (r.error) {
            return `<tr class="scan-row error-row">
                <td>${idx + 1}</td>
                <td class="symbol-cell">${r.symbol}</td>
                <td colspan="5" class="error-text">⚠️ ${r.error}</td>
            </tr>`;
        }

        const signalClass = r.compositeScore > 0 ? 'bullish' : r.compositeScore < 0 ? 'bearish' : 'neutral';
        const signalIcon = r.compositeScore > 0 ? '🟢' : r.compositeScore < 0 ? '🔴' : '⚪';
        const changeClass = (r.changePct || 0) >= 0 ? 'positive' : 'negative';
        const scoreBar = Math.min(Math.abs(r.compositeScore), 100);

        let signalBadge = '<span class="badge neutral">No Signal</span>';
        if (r.latestSignal) {
            signalBadge = r.latestSignal.signal === 1
                ? `<span class="badge bullish">BUY @ ${formatRupee(r.latestSignal.entryPrice)}</span>`
                : `<span class="badge bearish">SELL @ ${formatRupee(r.latestSignal.entryPrice)}</span>`;
        }

        return `<tr class="scan-row ${signalClass}" onclick="showDetailModal(scanResults[${results.indexOf(r)}])" style="cursor:pointer">
            <td>${idx + 1}</td>
            <td class="symbol-cell">
                <span class="symbol-name">${r.symbol}</span>
            </td>
            <td class="price-cell">${formatRupee(r.lastClose)}</td>
            <td class="${changeClass}">${r.changePct !== null ? (r.changePct >= 0 ? '+' : '') + r.changePct.toFixed(2) + '%' : '—'}</td>
            <td>
                <div class="score-container">
                    <div class="score-bar">
                        <div class="score-fill ${signalClass}" style="width:${scoreBar}%"></div>
                    </div>
                    <span class="score-value">${signalIcon} ${r.compositeScore.toFixed(0)}%</span>
                </div>
            </td>
            <td>
                <span class="strategy-count">${r.bullCount}↑ / ${r.bearCount}↓</span>
            </td>
            <td>${signalBadge}</td>
        </tr>`;
    }).join('');
}

function updateBacktestReport(result, strategyName, symbol) {
    const container = document.getElementById('backtestReport');
    if (!container) return;

    const m = result.metrics;

    container.innerHTML = `
        <div class="report-header">
            <h3>📊 Backtest: ${strategyName} on ${symbol}</h3>
            <div class="report-period">1 Year | Daily | Capital: ₹1,00,000</div>
        </div>

        <div class="metrics-grid">
            <div class="metric-card ${m.totalReturn >= 0 ? 'positive' : 'negative'}">
                <div class="metric-label">Total Return</div>
                <div class="metric-value">${formatPct(m.totalReturn)}</div>
                <div class="metric-sub">${formatRupee(m.finalCapital)}</div>
            </div>
            <div class="metric-card">
                <div class="metric-label">Win Rate</div>
                <div class="metric-value">${formatPct(m.winRate)}</div>
                <div class="metric-sub">${m.totalWins}W / ${m.totalLosses}L</div>
            </div>
            <div class="metric-card ${m.profitFactor >= 1.5 ? 'positive' : m.profitFactor < 1 ? 'negative' : ''}">
                <div class="metric-label">Profit Factor</div>
                <div class="metric-value">${m.profitFactor === Infinity ? '∞' : m.profitFactor.toFixed(2)}</div>
            </div>
            <div class="metric-card ${m.sharpeRatio >= 1 ? 'positive' : m.sharpeRatio < 0 ? 'negative' : ''}">
                <div class="metric-label">Sharpe Ratio</div>
                <div class="metric-value">${m.sharpeRatio.toFixed(2)}</div>
            </div>
            <div class="metric-card negative">
                <div class="metric-label">Max Drawdown</div>
                <div class="metric-value">${formatPct(m.maxDrawdown)}</div>
            </div>
            <div class="metric-card">
                <div class="metric-label">Total Trades</div>
                <div class="metric-value">${m.totalTrades}</div>
            </div>
            <div class="metric-card positive">
                <div class="metric-label">Avg Win</div>
                <div class="metric-value">+${formatPct(m.avgWin)}</div>
            </div>
            <div class="metric-card negative">
                <div class="metric-label">Avg Loss</div>
                <div class="metric-value">-${formatPct(m.avgLoss)}</div>
            </div>
            <div class="metric-card">
                <div class="metric-label">Risk/Reward</div>
                <div class="metric-value">${m.riskReward.toFixed(2)}</div>
            </div>
            <div class="metric-card">
                <div class="metric-label">Planned R:R</div>
                <div class="metric-value">${m.plannedRR.toFixed(2)}</div>
            </div>
            <div class="metric-card">
                <div class="metric-label">Realized R:R</div>
                <div class="metric-value">${m.realizedRR.toFixed(2)}</div>
            </div>
        </div>

        <div class="chart-row">
            <div class="chart-container">
                <h4>Equity Curve</h4>
                <canvas id="equityChart"></canvas>
            </div>
            <div class="chart-container">
                <h4>Trade P&L</h4>
                <canvas id="pnlChart"></canvas>
            </div>
        </div>

        <div class="trades-table-wrapper">
            <h4>📋 Trade Log (${result.trades.length} trades)</h4>
            <table class="trades-table">
                <thead>
                    <tr>
                        <th>#</th>
                        <th>Type</th>
                        <th>Entry Date</th>
                        <th>Entry</th>
                        <th>Exit</th>
                        <th>SL</th>
                        <th>Target</th>
                        <th>Qty</th>
                        <th>P&L</th>
                        <th>%</th>
                        <th>Exit Reason</th>
                    </tr>
                </thead>
                <tbody>
                    ${result.trades.map((t, i) => `
                        <tr class="${t.netPnL >= 0 ? 'win-row' : 'loss-row'}">
                            <td>${i + 1}</td>
                            <td><span class="badge ${t.signal === 1 ? 'bullish' : 'bearish'}">${t.signal === 1 ? 'LONG' : 'SHORT'}</span></td>
                            <td>${t.entryDate ? t.entryDate.toLocaleDateString('en-IN') : '—'}</td>
                            <td>${formatRupee(t.entryPrice)}</td>
                            <td>${formatRupee(t.exitPrice)}</td>
                            <td>${formatRupee(t.stopLoss)}</td>
                            <td>${formatRupee(t.target)}</td>
                            <td>${t.qty}</td>
                            <td class="${t.netPnL >= 0 ? 'positive' : 'negative'}">${formatRupee(t.netPnL)}</td>
                            <td class="${t.pnlPct >= 0 ? 'positive' : 'negative'}">${t.pnlPct >= 0 ? '+' : ''}${t.pnlPct.toFixed(2)}%</td>
                            <td><span class="exit-badge ${t.exitReason.toLowerCase()}">${t.exitReason}</span></td>
                        </tr>
                    `).join('')}
                </tbody>
            </table>
        </div>
    `;

    // Render charts after DOM update
    setTimeout(() => {
        renderEquityChart(result.equityCurve);
        renderPnLChart(result.trades);
    }, 100);
}

function updateComparisonTable(results) {
    const container = document.getElementById('comparisonTable');
    if (!container) return;

    const sorted = [...results].sort((a, b) => b.metrics.totalReturn - a.metrics.totalReturn);

    container.innerHTML = `
        <table class="comparison-table">
            <thead>
                <tr>
                    <th>Rank</th>
                    <th>Strategy</th>
                    <th>Return</th>
                    <th>Win Rate</th>
                    <th>Profit Factor</th>
                    <th>Sharpe</th>
                    <th>Max DD</th>
                    <th>Trades</th>
                    <th>R:R</th>
                </tr>
            </thead>
            <tbody>
                ${sorted.map((r, i) => {
                    const m = r.metrics;
                    return `<tr class="${m.totalReturn >= 0 ? 'positive-row' : 'negative-row'}">
                        <td>${i + 1}</td>
                        <td><span class="strat-icon">${STRATEGY_INFO[r.key]?.icon || '📊'}</span> ${r.name}</td>
                        <td class="${m.totalReturn >= 0 ? 'positive' : 'negative'}">${formatPct(m.totalReturn)}</td>
                        <td>${formatPct(m.winRate)}</td>
                        <td>${m.profitFactor === Infinity ? '∞' : m.profitFactor.toFixed(2)}</td>
                        <td>${m.sharpeRatio.toFixed(2)}</td>
                        <td class="negative">${formatPct(m.maxDrawdown)}</td>
                        <td>${m.totalTrades}</td>
                        <td>${m.riskReward.toFixed(2)}</td>
                    </tr>`;
                }).join('')}
            </tbody>
        </table>
    `;
}

function renderEquityChart(equityCurve) {
    const canvas = document.getElementById('equityChart');
    if (!canvas || typeof Chart === 'undefined') return;

    const ctx = canvas.getContext('2d');
    // Destroy existing chart if any
    if (canvas._chartInstance) canvas._chartInstance.destroy();

    const labels = equityCurve.map((pt, i) => pt.date ? pt.date.toLocaleDateString('en-IN') : `T${i}`);
    const data = equityCurve.map(pt => pt.equity);
    const startCapital = data[0] || 100000;

    const chart = new Chart(ctx, {
        type: 'line',
        data: {
            labels,
            datasets: [{
                label: 'Equity',
                data,
                borderColor: data[data.length - 1] >= startCapital ? '#00e676' : '#ff5252',
                backgroundColor: data[data.length - 1] >= startCapital
                    ? 'rgba(0,230,118,0.1)'
                    : 'rgba(255,82,82,0.1)',
                fill: true,
                tension: 0.3,
                pointRadius: 2,
                borderWidth: 2
            }, {
                label: 'Starting Capital',
                data: new Array(labels.length).fill(startCapital),
                borderColor: 'rgba(255,255,255,0.2)',
                borderDash: [5, 5],
                borderWidth: 1,
                pointRadius: 0,
                fill: false
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { labels: { color: '#b0b0b0', font: { size: 11 } } },
                tooltip: {
                    callbacks: {
                        label: (ctx) => `Equity: ${formatRupee(ctx.raw)}`
                    }
                }
            },
            scales: {
                x: { ticks: { color: '#888', maxTicksLimit: 10 }, grid: { color: 'rgba(255,255,255,0.05)' } },
                y: {
                    ticks: {
                        color: '#888',
                        callback: (v) => '₹' + formatIndianNumber(v)
                    },
                    grid: { color: 'rgba(255,255,255,0.05)' }
                }
            }
        }
    });
    canvas._chartInstance = chart;
}

function renderPnLChart(trades) {
    const canvas = document.getElementById('pnlChart');
    if (!canvas || typeof Chart === 'undefined') return;

    const ctx = canvas.getContext('2d');
    if (canvas._chartInstance) canvas._chartInstance.destroy();

    const labels = trades.map((t, i) => `#${i + 1}`);
    const data = trades.map(t => t.netPnL);
    const colors = data.map(v => v >= 0 ? '#00e676' : '#ff5252');

    const chart = new Chart(ctx, {
        type: 'bar',
        data: {
            labels,
            datasets: [{
                label: 'Trade P&L',
                data,
                backgroundColor: colors,
                borderColor: colors,
                borderWidth: 1,
                borderRadius: 3
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { labels: { color: '#b0b0b0', font: { size: 11 } } },
                tooltip: {
                    callbacks: {
                        label: (ctx) => `P&L: ${formatRupee(ctx.raw)}`
                    }
                }
            },
            scales: {
                x: { ticks: { color: '#888' }, grid: { color: 'rgba(255,255,255,0.05)' } },
                y: {
                    ticks: {
                        color: '#888',
                        callback: (v) => '₹' + formatIndianNumber(v)
                    },
                    grid: { color: 'rgba(255,255,255,0.05)' }
                }
            }
        }
    });
    canvas._chartInstance = chart;
}

function showToast(message, type = 'info') {
    const container = document.getElementById('toastContainer') || createToastContainer();

    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;

    const icons = { success: '✅', error: '❌', warning: '⚠️', info: 'ℹ️' };
    toast.innerHTML = `
        <span class="toast-icon">${icons[type] || icons.info}</span>
        <span class="toast-message">${message}</span>
        <button class="toast-close" onclick="this.parentElement.remove()">×</button>
    `;

    container.appendChild(toast);

    // Animate in
    requestAnimationFrame(() => toast.classList.add('show'));

    // Auto-dismiss
    setTimeout(() => {
        toast.classList.remove('show');
        setTimeout(() => toast.remove(), 300);
    }, 4000);
}

function createToastContainer() {
    const container = document.createElement('div');
    container.id = 'toastContainer';
    container.className = 'toast-container';
    document.body.appendChild(container);
    return container;
}

function showDetailModal(stockResult) {
    if (!stockResult || !stockResult.data) {
        showToast('No data available for this stock', 'error');
        return;
    }

    const modal = document.getElementById('detailModal');
    const modalBody = document.getElementById('modalBody');
    if (!modal || !modalBody) return;

    const data = stockResult.data;
    const close = data.close;
    const lastClose = close[close.length - 1];
    const prevClose = close[close.length - 2] || lastClose;
    const changePct = ((lastClose - prevClose) / prevClose) * 100;

    // Compute indicators for display
    const rsi = calcRSI(close, 14);
    const ema9 = calcEMA(close, 9);
    const ema21 = calcEMA(close, 21);
    const { macd, signal: macdSig } = calcMACD(close);
    const { supertrend: st, direction: stDir } = calcSupertrend(data.high, data.low, close, 10, 3);
    const { upper: bbUpper, mid: bbMid, lower: bbLower } = calcBollingerBands(close);
    const vwap = calcVWAP(data.high, data.low, close, data.volume);
    const atr = calcATR(data.high, data.low, close, 14);

    const lastIdx = close.length - 1;

    // Strategy signals summary
    let strategyHTML = '';
    for (const key of Object.keys(stockResult.stratResults || {})) {
        const sigs = stockResult.stratResults[key];
        const info = STRATEGY_INFO[key];
        const lastSig = sigs.length > 0 ? sigs[sigs.length - 1] : null;
        const isRecent = lastSig && lastSig.index >= close.length - 5;

        strategyHTML += `
            <div class="strat-detail-row">
                <span class="strat-icon">${info?.icon || '📊'}</span>
                <span class="strat-name">${info?.name || key}</span>
                <span class="strat-signal-count">${sigs.length} signals</span>
                ${isRecent
                    ? `<span class="badge ${lastSig.signal === 1 ? 'bullish' : 'bearish'}">
                        ${lastSig.signal === 1 ? 'BUY' : 'SELL'} @ ${formatRupee(lastSig.entryPrice)}
                    </span>`
                    : '<span class="badge neutral">—</span>'
                }
            </div>
        `;
    }

    modalBody.innerHTML = `
        <div class="modal-header-info">
            <h2>${stockResult.symbol}</h2>
            <div class="modal-price">
                <span class="modal-ltp">${formatRupee(lastClose)}</span>
                <span class="modal-change ${changePct >= 0 ? 'positive' : 'negative'}">
                    ${changePct >= 0 ? '+' : ''}${changePct.toFixed(2)}%
                </span>
            </div>
        </div>

        <div class="indicator-grid">
            <div class="ind-card">
                <span class="ind-label">RSI (14)</span>
                <span class="ind-value ${rsi[lastIdx] > 70 ? 'negative' : rsi[lastIdx] < 30 ? 'positive' : ''}">
                    ${rsi[lastIdx] !== null ? rsi[lastIdx].toFixed(1) : '—'}
                </span>
            </div>
            <div class="ind-card">
                <span class="ind-label">EMA 9</span>
                <span class="ind-value">${ema9[lastIdx] !== null ? formatRupee(ema9[lastIdx]) : '—'}</span>
            </div>
            <div class="ind-card">
                <span class="ind-label">EMA 21</span>
                <span class="ind-value">${ema21[lastIdx] !== null ? formatRupee(ema21[lastIdx]) : '—'}</span>
            </div>
            <div class="ind-card">
                <span class="ind-label">MACD</span>
                <span class="ind-value ${macd[lastIdx] > 0 ? 'positive' : 'negative'}">
                    ${macd[lastIdx] !== null ? macd[lastIdx].toFixed(2) : '—'}
                </span>
            </div>
            <div class="ind-card">
                <span class="ind-label">Supertrend</span>
                <span class="ind-value ${stDir[lastIdx] === 1 ? 'positive' : 'negative'}">
                    ${stDir[lastIdx] === 1 ? '🟢 Bullish' : stDir[lastIdx] === -1 ? '🔴 Bearish' : '—'}
                </span>
            </div>
            <div class="ind-card">
                <span class="ind-label">BB Upper</span>
                <span class="ind-value">${bbUpper[lastIdx] !== null ? formatRupee(bbUpper[lastIdx]) : '—'}</span>
            </div>
            <div class="ind-card">
                <span class="ind-label">BB Lower</span>
                <span class="ind-value">${bbLower[lastIdx] !== null ? formatRupee(bbLower[lastIdx]) : '—'}</span>
            </div>
            <div class="ind-card">
                <span class="ind-label">VWAP</span>
                <span class="ind-value">${vwap[lastIdx] !== null ? formatRupee(vwap[lastIdx]) : '—'}</span>
            </div>
            <div class="ind-card">
                <span class="ind-label">ATR (14)</span>
                <span class="ind-value">${atr[lastIdx] !== null ? formatRupee(atr[lastIdx]) : '—'}</span>
            </div>
        </div>

        <div class="strat-details-section">
            <h4>Strategy Signals</h4>
            ${strategyHTML || '<p class="no-data">No strategies analyzed</p>'}
        </div>

        <div class="modal-actions">
            <button class="btn btn-primary" onclick="runBacktestForModal('${stockResult.symbol}')">
                📊 Run Backtest
            </button>
            <button class="btn btn-secondary" onclick="runAllBacktestsForModal('${stockResult.symbol}')">
                📋 Compare All Strategies
            </button>
        </div>

        <div id="modalBacktestResult"></div>
    `;

    modal.classList.add('active');
    document.body.style.overflow = 'hidden';
}

async function runBacktestForModal(symbol) {
    const container = document.getElementById('modalBacktestResult');
    if (!container) return;

    container.innerHTML = '<div class="loading-spinner"><div class="spinner"></div><p>Running backtest...</p></div>';

    try {
        const data = await fetchStockData(symbol);
        const activeStrategies = getActiveStrategies();

        if (activeStrategies.length === 0) {
            container.innerHTML = '<p class="error-text">No strategies selected</p>';
            return;
        }

        // Use first active strategy
        const key = activeStrategies[0];
        const fn = STRATEGY_FUNCTIONS[key];
        if (!fn) return;

        const signals = fn(data);
        const result = runBacktest(signals, data);

        container.innerHTML = '';

        // Create inline report
        const reportDiv = document.createElement('div');
        reportDiv.id = 'backtestReport';
        container.appendChild(reportDiv);

        updateBacktestReport(result, STRATEGY_INFO[key]?.name || key, symbol);
    } catch (e) {
        container.innerHTML = `<p class="error-text">Backtest failed: ${e.message}</p>`;
    }
}

async function runAllBacktestsForModal(symbol) {
    const container = document.getElementById('modalBacktestResult');
    if (!container) return;

    container.innerHTML = '<div class="loading-spinner"><div class="spinner"></div><p>Comparing strategies...</p></div>';

    try {
        const data = await fetchStockData(symbol);
        const activeStrategies = getActiveStrategies();

        const compResults = [];
        for (const key of activeStrategies) {
            const fn = STRATEGY_FUNCTIONS[key];
            if (!fn) continue;
            try {
                const signals = fn(data);
                const result = runBacktest(signals, data);
                compResults.push({
                    key,
                    name: STRATEGY_INFO[key]?.name || key,
                    ...result
                });
            } catch (e) {
                // skip failed strategy
            }
        }

        container.innerHTML = '<div id="comparisonTable"></div>';
        updateComparisonTable(compResults);
    } catch (e) {
        container.innerHTML = `<p class="error-text">Comparison failed: ${e.message}</p>`;
    }
}

function closeModal() {
    const modal = document.getElementById('detailModal');
    if (modal) {
        modal.classList.remove('active');
        document.body.style.overflow = '';
    }
}

// ────────────────────────────────────────────────────────────
// EVENT LISTENERS & INITIALIZATION
// ────────────────────────────────────────────────────────────

function getStockList() {
    const input = document.getElementById('stockInput');
    if (!input) return [];
    const raw = input.value.trim();
    if (!raw) return [];
    return raw.split(/[,\n]+/).map(s => s.trim().toUpperCase()).filter(s => s.length > 0);
}

function setupEventListeners() {
    // Tab clicks
    document.querySelectorAll('.tab-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            showView(btn.dataset.view);
        });
    });

    // Run button
    const runBtn = document.getElementById('runBtn');
    if (runBtn) {
        runBtn.addEventListener('click', async () => {
            const stocks = getStockList();
            if (stocks.length === 0) {
                showToast('Please enter at least one stock symbol', 'warning');
                return;
            }

            if (currentView === 'scanner') {
                const modeSelect = document.getElementById('modeSelect');
                const mode = modeSelect ? modeSelect.value : 'swing';
                await runScanner(stocks, mode);
            } else if (currentView === 'backtest') {
                await runBacktestView(stocks);
            }
        });
    }

    // Quick-add chips
    document.querySelectorAll('.chip').forEach(chip => {
        chip.addEventListener('click', () => {
            const group = chip.dataset.group;
            const input = document.getElementById('stockInput');
            if (!input) return;

            let stocks = [];
            if (group === 'nifty50') stocks = NIFTY_50;
            else if (group === 'banknifty') stocks = BANK_NIFTY;
            else if (group === 'custom') {
                // Individual stock chip
                const symbol = chip.dataset.symbol;
                if (symbol) {
                    const current = input.value.trim();
                    const existing = current ? current.split(/[,\n]+/).map(s => s.trim().toUpperCase()) : [];
                    if (!existing.includes(symbol.toUpperCase())) {
                        input.value = current ? current + ', ' + symbol : symbol;
                    }
                    return;
                }
            }

            if (stocks.length > 0) {
                input.value = stocks.join(', ');
                showToast(`Loaded ${stocks.length} stocks`, 'info');
            }
        });
    });

    // Select all / deselect all strategies
    const selectAllBtn = document.getElementById('selectAllStrats');
    if (selectAllBtn) {
        selectAllBtn.addEventListener('click', () => {
            document.querySelectorAll('.strategy-checkbox').forEach(cb => cb.checked = true);
            updateStrategyCount();
        });
    }

    const deselectAllBtn = document.getElementById('deselectAllStrats');
    if (deselectAllBtn) {
        deselectAllBtn.addEventListener('click', () => {
            document.querySelectorAll('.strategy-checkbox').forEach(cb => cb.checked = false);
            updateStrategyCount();
        });
    }

    // Strategy checkboxes
    document.querySelectorAll('.strategy-checkbox').forEach(cb => {
        cb.addEventListener('change', updateStrategyCount);
    });

    // Enter key on stock input
    const stockInput = document.getElementById('stockInput');
    if (stockInput) {
        stockInput.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                if (runBtn) runBtn.click();
            }
        });
    }

    // Modal close
    const modalOverlay = document.getElementById('detailModal');
    if (modalOverlay) {
        modalOverlay.addEventListener('click', (e) => {
            if (e.target === modalOverlay) closeModal();
        });
    }

    const modalCloseBtn = document.getElementById('modalCloseBtn');
    if (modalCloseBtn) {
        modalCloseBtn.addEventListener('click', closeModal);
    }

    // ESC key to close modal
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') closeModal();
    });

    // Category filter buttons
    document.querySelectorAll('.cat-filter-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            const cat = btn.dataset.category;
            document.querySelectorAll('.cat-filter-btn').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');

            document.querySelectorAll('.strategy-item').forEach(item => {
                if (cat === 'all' || item.dataset.category === cat) {
                    item.style.display = '';
                } else {
                    item.style.display = 'none';
                }
            });
        });
    });
}

function updateStrategyCount() {
    const count = document.querySelectorAll('.strategy-checkbox:checked').length;
    const countEl = document.getElementById('strategyCount');
    if (countEl) countEl.textContent = `${count} selected`;
}

async function runBacktestView(stocks) {
    const container = document.getElementById('backtestReport');
    if (!container) return;

    const activeStrategies = getActiveStrategies();
    if (activeStrategies.length === 0) {
        showToast('Select at least one strategy', 'warning');
        return;
    }

    container.innerHTML = '<div class="loading-spinner"><div class="spinner"></div><p>Running backtest...</p></div>';

    try {
        const symbol = stocks[0];
        const data = await fetchStockData(symbol);

        if (activeStrategies.length === 1) {
            const key = activeStrategies[0];
            const fn = STRATEGY_FUNCTIONS[key];
            const signals = fn(data);
            const result = runBacktest(signals, data);
            updateBacktestReport(result, STRATEGY_INFO[key]?.name || key, symbol);
        } else {
            // Compare multiple strategies
            const compResults = [];
            for (const key of activeStrategies) {
                const fn = STRATEGY_FUNCTIONS[key];
                if (!fn) continue;
                try {
                    const signals = fn(data);
                    const result = runBacktest(signals, data);
                    compResults.push({ key, name: STRATEGY_INFO[key]?.name || key, ...result });
                } catch (e) {
                    // skip
                }
            }

            // Show best strategy's full report
            if (compResults.length > 0) {
                const best = compResults.sort((a, b) => b.metrics.totalReturn - a.metrics.totalReturn)[0];
                updateBacktestReport(best, best.name + ' (Best)', symbol);

                // Add comparison table below
                const compDiv = document.createElement('div');
                compDiv.id = 'comparisonTable';
                compDiv.style.marginTop = '2rem';
                container.appendChild(compDiv);

                const compHeader = document.createElement('h3');
                compHeader.textContent = '📋 Strategy Comparison';
                compHeader.style.color = '#e0e0e0';
                compHeader.style.marginBottom = '1rem';
                container.appendChild(compHeader);

                const compTableDiv = document.createElement('div');
                compTableDiv.id = 'comparisonTable';
                container.appendChild(compTableDiv);

                updateComparisonTable(compResults);
            }
        }

        showToast('Backtest complete!', 'success');
    } catch (e) {
        container.innerHTML = `<p class="error-text">❌ ${e.message}</p>`;
        showToast(`Backtest failed: ${e.message}`, 'error');
    }
}

// ────────────────────────────────────────────────────────────
// INITIALIZATION
// ────────────────────────────────────────────────────────────

function initApp() {
    // Set default selected strategies
    document.querySelectorAll('.strategy-checkbox').forEach(cb => {
        if (selectedStrategies.has(cb.value)) {
            cb.checked = true;
        }
    });

    // Show scanner view by default
    showView('scanner');
    updateStrategyCount();
    setupEventListeners();

    // Show welcome toast
    showToast('Dashboard ready! Enter stock symbols to begin scanning.', 'info');

    console.log('🚀 Indian Stock Trading Signal Dashboard initialized');
    console.log(`📊 ${Object.keys(STRATEGY_INFO).length} strategies loaded`);
    console.log(`📈 NIFTY 50: ${NIFTY_50.length} stocks | BANK NIFTY: ${BANK_NIFTY.length} stocks`);
}

// Start when DOM is ready
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initApp);
} else {
    initApp();
}
