"""
ORB Scanner Logic - Cloud Version with Filters
"""
import requests
from datetime import datetime, timedelta


SYMBOLS = [
    {'fyers': 'NSE:NIFTY50-INDEX', 'name': 'NIFTY50', 'type': 'index'},
    {'fyers': 'NSE:NIFTYBANK-INDEX', 'name': 'BANKNIFTY', 'type': 'index'},
    {'fyers': 'NSE:RELIANCE-EQ', 'name': 'RELIANCE', 'type': 'stock'},
    {'fyers': 'NSE:INFY-EQ', 'name': 'INFY', 'type': 'stock'},
    {'fyers': 'NSE:HDFCBANK-EQ', 'name': 'HDFCBANK', 'type': 'stock'},
    {'fyers': 'NSE:SBIN-EQ', 'name': 'SBIN', 'type': 'stock'},
    {'fyers': 'NSE:ICICIBANK-EQ', 'name': 'ICICIBANK', 'type': 'stock'},
    {'fyers': 'NSE:AXISBANK-EQ', 'name': 'AXISBANK', 'type': 'stock'},
    {'fyers': 'NSE:ITC-EQ', 'name': 'ITC', 'type': 'stock'},
    {'fyers': 'NSE:TCS-EQ', 'name': 'TCS', 'type': 'stock'},
    {'fyers': 'NSE:BAJFINANCE-EQ', 'name': 'BAJFINANCE', 'type': 'stock'},
    {'fyers': 'NSE:TATASTEEL-EQ', 'name': 'TATASTEEL', 'type': 'stock'},
]

ORB_CANDLES = 3  # 3 x 5min = 15 min
RR = 2.0
HISTORY_URL = 'https://api-t1.fyers.in/data/history'


class ORBScanner:
    def __init__(self):
        self.prev_day_data = {}

    def fetch_5m(self, symbol, token, client_id):
        """Fetch 5m candles from Fyers."""
        now = datetime.now()
        from_date = (now - timedelta(days=5)).strftime('%Y-%m-%d')
        to_date = now.strftime('%Y-%m-%d')

        url = (f"{HISTORY_URL}?symbol={symbol}&resolution=5"
               f"&date_format=1&range_from={from_date}&range_to={to_date}&cont_flag=1")

        headers = {'Authorization': f"{client_id}:{token}"}

        try:
            resp = requests.get(url, headers=headers, timeout=10)
            data = resp.json()
            if data.get('s') == 'ok' and data.get('candles'):
                return self._parse(data['candles'])
        except Exception as e:
            print(f"Fetch error {symbol}: {e}")

        return None

    def _parse(self, candles):
        """Parse Fyers candle data."""
        result = []
        for c in candles:
            dt = datetime.fromtimestamp(c[0])
            result.append({
                'date': dt,
                'open': c[1], 'high': c[2], 'low': c[3], 'close': c[4], 'volume': c[5],
                'time': dt.strftime('%H:%M'),
                'day': dt.strftime('%Y-%m-%d'),
            })
        return result

    def calc_vwap(self, candles):
        """Calculate VWAP for given candles."""
        cum_vol = 0
        cum_tp_vol = 0
        vwap_values = []
        for c in candles:
            tp = (c['high'] + c['low'] + c['close']) / 3
            cum_vol += c['volume']
            cum_tp_vol += tp * c['volume']
            vwap_values.append(cum_tp_vol / cum_vol if cum_vol > 0 else tp)
        return vwap_values

    def detect_orb(self, candles, name, use_filters=True):
        """Detect ORB breakout with optional filters."""
        if not candles or len(candles) < 10:
            return None

        days = sorted(set(c['day'] for c in candles))
        today = days[-1]
        today_c = [c for c in candles if c['day'] == today]

        if len(today_c) < ORB_CANDLES + 1:
            return {'symbol': name, 'status': 'WAITING', 'message': 'ORB forming...'}

        # ORB range
        orb = today_c[:ORB_CANDLES]
        orb_h = max(c['high'] for c in orb)
        orb_l = min(c['low'] for c in orb)
        orb_r = orb_h - orb_l
        if orb_r <= 0:
            return None

        # ── FILTERS ──
        if use_filters and len(days) >= 2:
            prev_day = days[-2]
            prev_c = [c for c in candles if c['day'] == prev_day]
            if prev_c:
                prev_vwap = self.calc_vwap(prev_c)[-1]
                today_open = today_c[0]['open']
                orb_vol = sum(c['volume'] for c in orb) / len(orb)
                prev_avg_vol = sum(c['volume'] for c in prev_c) / len(prev_c) if prev_c else orb_vol
            else:
                prev_vwap = None
                orb_vol = 0
                prev_avg_vol = 0
        else:
            prev_vwap = None

        # Scan for breakout
        post = today_c[ORB_CANDLES:]
        if not post:
            return {'symbol': name, 'status': 'WAITING', 'orb_high': orb_h, 'orb_low': orb_l, 'orb_range': orb_r}

        signal = None
        b_candle = None

        for c in post:
            # Time filter: only before 12:00
            if use_filters and c['time'] >= '12:00':
                break

            if c['close'] > orb_h:
                signal = 'BUY'
                b_candle = c
                break
            elif c['close'] < orb_l:
                signal = 'SELL'
                b_candle = c
                break

        if not signal:
            last = today_c[-1]
            return {
                'symbol': name, 'status': 'NO_BREAKOUT',
                'orb_high': orb_h, 'orb_low': orb_l, 'orb_range': orb_r,
                'ltp': last['close'],
                'dist_high': ((orb_h - last['close']) / last['close']) * 100,
                'dist_low': ((last['close'] - orb_l) / last['close']) * 100,
            }

        # Apply trend filter
        if use_filters and prev_vwap is not None:
            today_open = today_c[0]['open']
            if signal == 'BUY' and today_open < prev_vwap:
                return {'symbol': name, 'status': 'FILTERED', 'reason': 'Bearish day (below VWAP)', 'signal': signal}
            if signal == 'SELL' and today_open > prev_vwap:
                return {'symbol': name, 'status': 'FILTERED', 'reason': 'Bullish day (above VWAP)', 'signal': signal}

        # Volume filter
        if use_filters and prev_vwap is not None:
            if orb_vol < prev_avg_vol * 0.8:
                return {'symbol': name, 'status': 'FILTERED', 'reason': 'Low volume', 'signal': signal}

        # Calculate levels
        entry = b_candle['close']
        if signal == 'BUY':
            sl = orb_l
            target = entry + (entry - sl) * RR
        else:
            sl = orb_h
            target = entry - (sl - entry) * RR

        risk = abs(entry - sl)
        rr = abs(target - entry) / risk if risk > 0 else 0

        # Current P&L
        last = today_c[-1]
        cur = last['close']
        if signal == 'BUY':
            if cur <= sl:
                trade_status = 'SL HIT ❌'
                pnl = ((sl - entry) / entry) * 100
            elif cur >= target:
                trade_status = 'TARGET HIT ✅'
                pnl = ((target - entry) / entry) * 100
            else:
                trade_status = 'ACTIVE 🟢'
                pnl = ((cur - entry) / entry) * 100
        else:
            if cur >= sl:
                trade_status = 'SL HIT ❌'
                pnl = ((entry - sl) / entry) * 100
            elif cur <= target:
                trade_status = 'TARGET HIT ✅'
                pnl = ((entry - target) / entry) * 100
            else:
                trade_status = 'ACTIVE 🟢'
                pnl = ((entry - cur) / entry) * 100

        return {
            'symbol': name, 'status': 'SIGNAL', 'signal': signal,
            'entry': entry, 'sl': sl, 'target': target,
            'risk': risk, 'rr': rr,
            'breakout_time': b_candle['time'],
            'orb_high': orb_h, 'orb_low': orb_l, 'orb_range': orb_r,
            'current_price': cur, 'current_pnl': pnl,
            'trade_status': trade_status,
        }

    def scan_all(self, token, client_id, use_filters=True):
        """Scan all symbols."""
        results = []
        for s in SYMBOLS:
            try:
                candles = self.fetch_5m(s['fyers'], token, client_id)
                r = self.detect_orb(candles, s['name'], use_filters)
                if r:
                    r['type'] = s['type']
                    results.append(r)
            except Exception as e:
                print(f"Error scanning {s['name']}: {e}")
            import time
            time.sleep(0.3)
        return results
