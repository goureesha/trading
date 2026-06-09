"""
ORB Scanner Cloud - Flask Backend
Runs on Render.com, serves dashboard + background ORB scanner
"""
import os
import json
import hashlib
import threading
import time
import requests
from datetime import datetime, timedelta
from flask import Flask, request, jsonify, render_template
from scanner import ORBScanner
from telegram_bot import send_telegram

app = Flask(__name__)

# ── State ──
state = {
    'token': None,
    'scanning': False,
    'results': [],
    'last_scan': None,
    'started_at': None,
    'scan_count': 0,
    'daily_pnl': 0,
    'filters_on': True,
}

scanner = ORBScanner()

# ── Config ──
CLIENT_ID = os.environ.get('FYERS_CLIENT_ID', '70OO9494R9-100')
SECRET = os.environ.get('FYERS_SECRET', 'M4RUQHA4T0')
REDIRECT = 'https://127.0.0.1'
TELEGRAM_TOKEN = os.environ.get('TELEGRAM_TOKEN', '')
TELEGRAM_CHAT_ID = os.environ.get('TELEGRAM_CHAT_ID', '')


# ── Routes ──

@app.route('/')
def index():
    return render_template('index.html')


@app.route('/api/login', methods=['POST'])
def login():
    """Accept Fyers redirect URL, extract auth code, generate token."""
    data = request.json
    url = data.get('url', '')

    # Extract auth_code
    auth_code = None
    try:
        from urllib.parse import urlparse, parse_qs
        parsed = urlparse(url)
        params = parse_qs(parsed.query)
        auth_code = params.get('auth_code', [None])[0]
    except:
        auth_code = url.strip()

    if not auth_code:
        return jsonify({'ok': False, 'error': 'Invalid URL. Paste the full redirect URL.'})

    # Generate token
    try:
        app_id_hash = hashlib.sha256(f"{CLIENT_ID}:{SECRET}".encode()).hexdigest()
        resp = requests.post('https://api-t1.fyers.in/api/v3/validate-authcode', json={
            'grant_type': 'authorization_code',
            'appIdHash': app_id_hash,
            'code': auth_code,
        }, timeout=15)
        result = resp.json()

        if result.get('s') == 'ok' and result.get('access_token'):
            state['token'] = result['access_token']
            send_alert('🔐 Login successful! Ready to scan.')
            return jsonify({'ok': True, 'message': 'Login successful!'})
        else:
            return jsonify({'ok': False, 'error': result.get('message', 'Login failed')})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)})


@app.route('/api/start', methods=['POST'])
def start_scan():
    """Start the background scanner."""
    if not state['token']:
        return jsonify({'ok': False, 'error': 'Login first!'})

    if state['scanning']:
        return jsonify({'ok': False, 'error': 'Already scanning'})

    state['scanning'] = True
    state['started_at'] = datetime.now().strftime('%H:%M:%S')
    state['scan_count'] = 0
    state['results'] = []

    # Start background scanner thread
    t = threading.Thread(target=scan_loop, daemon=True)
    t.start()

    send_alert('🚀 ORB Scanner started! Will run until 3:30 PM.')
    return jsonify({'ok': True, 'message': 'Scanner started!'})


@app.route('/api/stop', methods=['POST'])
def stop_scan():
    """Stop the scanner."""
    state['scanning'] = False
    send_alert('⏹️ Scanner stopped.')
    return jsonify({'ok': True})


@app.route('/api/status', methods=['GET'])
def get_status():
    """Return current scan results."""
    return jsonify({
        'ok': True,
        'scanning': state['scanning'],
        'logged_in': state['token'] is not None,
        'results': state['results'],
        'last_scan': state['last_scan'],
        'started_at': state['started_at'],
        'scan_count': state['scan_count'],
        'daily_pnl': state['daily_pnl'],
        'filters_on': state['filters_on'],
    })


@app.route('/api/auth-url', methods=['GET'])
def get_auth_url():
    """Return the Fyers auth URL."""
    url = f"https://api-t1.fyers.in/api/v3/generate-authcode?client_id={CLIENT_ID}&redirect_uri={REDIRECT}&response_type=code&state=orbscanner"
    return jsonify({'url': url})


@app.route('/health')
def health():
    """Keep-alive endpoint."""
    return 'OK'


# ── Scanner Loop ──

def scan_loop():
    """Background scanner - runs every 5 min until 3:30 PM."""
    prev_signals = {}

    while state['scanning']:
        now = datetime.now()
        hour, minute = now.hour, now.minute

        # Only scan during market hours (9:15 AM - 3:30 PM IST)
        # Note: Render uses UTC, IST = UTC + 5:30
        # We'll use the server time assuming IST
        if hour < 9 or (hour == 9 and minute < 15):
            time.sleep(60)
            continue

        if hour > 15 or (hour == 15 and minute > 30):
            # Market closed - send EOD summary
            send_eod_summary()
            state['scanning'] = False
            break

        try:
            results = scanner.scan_all(state['token'], CLIENT_ID, state['filters_on'])
            state['results'] = results
            state['last_scan'] = now.strftime('%H:%M:%S')
            state['scan_count'] += 1

            # Check for new signals / state changes
            for r in results:
                sym = r.get('symbol', '')
                sig = r.get('signal', '')
                status = r.get('trade_status', '')
                key = f"{sym}_{sig}"

                prev = prev_signals.get(key)

                if prev is None and r.get('status') == 'SIGNAL':
                    # New signal!
                    emoji = '🟢' if sig == 'BUY' else '🔴'
                    msg = (f"{emoji} {sig} {sym} @ ₹{r['entry']:.2f}\n"
                           f"SL: ₹{r['sl']:.2f} | Target: ₹{r['target']:.2f}\n"
                           f"R:R: {r['rr']:.1f}x | ORB Range: ₹{r['orb_range']:.1f}")
                    send_alert(msg)
                    prev_signals[key] = status

                elif prev and status != prev:
                    # Status changed
                    if 'TARGET' in status:
                        send_alert(f"🎯 TARGET HIT! {sym} | P&L: {r['current_pnl']:+.2f}%")
                    elif 'SL' in status:
                        send_alert(f"🛑 SL HIT! {sym} | P&L: {r['current_pnl']:+.2f}%")
                    prev_signals[key] = status

            # Calculate daily P&L
            total_pnl = sum(r.get('current_pnl', 0) for r in results if r.get('status') == 'SIGNAL')
            state['daily_pnl'] = total_pnl

        except Exception as e:
            print(f"Scan error: {e}")

        # Wait 5 minutes
        time.sleep(300)


def send_eod_summary():
    """Send end-of-day summary via Telegram."""
    results = state['results']
    signals = [r for r in results if r.get('status') == 'SIGNAL']

    if not signals:
        send_alert("📊 EOD: No signals today.")
        return

    buys = [s for s in signals if s['signal'] == 'BUY']
    sells = [s for s in signals if s['signal'] == 'SELL']
    winners = [s for s in signals if s.get('current_pnl', 0) > 0]
    losers = [s for s in signals if s.get('current_pnl', 0) <= 0]

    msg = f"📊 EOD SUMMARY — {datetime.now().strftime('%d %b %Y')}\n"
    msg += f"{'─'*30}\n"
    msg += f"Total Signals: {len(signals)} ({len(buys)} BUY, {len(sells)} SELL)\n"
    msg += f"Winners: {len(winners)} | Losers: {len(losers)}\n"
    msg += f"Win Rate: {len(winners)/len(signals)*100:.0f}%\n\n"

    for s in signals:
        emoji = '✅' if s.get('current_pnl', 0) > 0 else '❌'
        msg += f"{emoji} {s['symbol']} {s['signal']} {s.get('current_pnl',0):+.2f}%\n"

    msg += f"\n{'─'*30}\n"
    msg += f"Filters: {'ON ✅' if state['filters_on'] else 'OFF ❌'}\n"
    msg += f"Scans today: {state['scan_count']}"

    send_alert(msg)


def send_alert(message):
    """Send alert via Telegram."""
    if TELEGRAM_TOKEN and TELEGRAM_CHAT_ID:
        try:
            send_telegram(TELEGRAM_TOKEN, TELEGRAM_CHAT_ID, message)
        except Exception as e:
            print(f"Telegram error: {e}")
    print(f"[ALERT] {message}")


# ── Keep-alive ping ──
def keep_alive():
    """Ping self every 14 min to prevent Render from sleeping."""
    while True:
        time.sleep(840)  # 14 minutes
        try:
            url = os.environ.get('RENDER_EXTERNAL_URL', 'http://localhost:5000')
            requests.get(f"{url}/health", timeout=10)
        except:
            pass

threading.Thread(target=keep_alive, daemon=True).start()


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
