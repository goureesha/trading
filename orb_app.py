"""
ORB Scanner Web App - Live Dashboard
Run: python orb_app.py
Open: http://localhost:5000
"""
from flask import Flask, jsonify, render_template_string
from orb_scanner import fetch_today_5m, detect_orb, STOCKS, INDEX
from fyers_data import load_token
import threading
import time
from datetime import datetime

app = Flask(__name__)

# Cache
scan_cache = {"results": [], "last_update": None, "scanning": False}

SCAN_SYMBOLS = INDEX + STOCKS

def background_scan():
    """Run scan in background."""
    scan_cache["scanning"] = True
    results = []
    for sym in SCAN_SYMBOLS:
        try:
            df = fetch_today_5m(sym, days=5)
            result = detect_orb(df, sym)
            if result:
                results.append(result)
        except:
            pass
        time.sleep(0.3)
    scan_cache["results"] = results
    scan_cache["last_update"] = datetime.now().strftime("%H:%M:%S")
    scan_cache["scanning"] = False


@app.route("/")
def index():
    return render_template_string(HTML_TEMPLATE)


@app.route("/api/scan")
def api_scan():
    """Trigger a new scan and return results."""
    if not scan_cache["scanning"]:
        t = threading.Thread(target=background_scan, daemon=True)
        t.start()
    return jsonify({"status": "scanning"})


@app.route("/api/results")
def api_results():
    """Return cached scan results."""
    return jsonify({
        "results": scan_cache["results"],
        "last_update": scan_cache["last_update"],
        "scanning": scan_cache["scanning"],
    })


@app.route("/api/status")
def api_status():
    token = load_token()
    now = datetime.now()
    market_open = now.hour >= 9 and now.hour < 16
    return jsonify({
        "token_valid": token is not None,
        "market_open": market_open,
        "time": now.strftime("%H:%M:%S"),
    })


HTML_TEMPLATE = r"""
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>ORB Scanner - Live Trading Signals</title>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap" rel="stylesheet">
<style>
* { margin: 0; padding: 0; box-sizing: border-box; }
body {
    font-family: 'Inter', sans-serif;
    background: #0a0e17;
    color: #e2e8f0;
    min-height: 100vh;
}

/* Header */
.header {
    background: linear-gradient(135deg, #111827 0%, #1a1f35 100%);
    border-bottom: 1px solid rgba(59,130,246,0.2);
    padding: 16px 32px;
    display: flex;
    justify-content: space-between;
    align-items: center;
}
.logo {
    display: flex;
    align-items: center;
    gap: 12px;
    font-size: 22px;
    font-weight: 700;
    background: linear-gradient(135deg, #10b981, #3b82f6);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
}
.logo svg { width: 32px; height: 32px; }
.header-right { display: flex; align-items: center; gap: 16px; }
.status-badge {
    display: flex; align-items: center; gap: 6px;
    padding: 6px 14px; border-radius: 20px;
    font-size: 13px; font-weight: 500;
    background: rgba(16,185,129,0.15); color: #10b981;
    border: 1px solid rgba(16,185,129,0.3);
}
.status-badge.offline { background: rgba(239,68,68,0.15); color: #ef4444; border-color: rgba(239,68,68,0.3); }
.status-dot { width: 8px; height: 8px; border-radius: 50%; background: #10b981; animation: pulse 2s infinite; }
.status-badge.offline .status-dot { background: #ef4444; animation: none; }
@keyframes pulse { 0%,100% { opacity: 1; } 50% { opacity: 0.4; } }

.clock { font-size: 14px; color: #94a3b8; font-weight: 500; }
.scan-btn {
    padding: 10px 24px; border: none; border-radius: 10px;
    background: linear-gradient(135deg, #10b981, #059669);
    color: white; font-weight: 600; font-size: 14px;
    cursor: pointer; transition: all 0.3s;
    box-shadow: 0 0 20px rgba(16,185,129,0.3);
}
.scan-btn:hover { transform: translateY(-2px); box-shadow: 0 0 30px rgba(16,185,129,0.5); }
.scan-btn:disabled { opacity: 0.5; cursor: not-allowed; transform: none; }
.scan-btn.scanning { animation: btnPulse 1.5s infinite; }
@keyframes btnPulse { 0%,100% { box-shadow: 0 0 20px rgba(16,185,129,0.3); } 50% { box-shadow: 0 0 40px rgba(16,185,129,0.6); } }

/* Main */
.main { padding: 24px 32px; max-width: 1400px; margin: 0 auto; }

/* Summary Cards */
.summary-row { display: grid; grid-template-columns: repeat(5, 1fr); gap: 16px; margin-bottom: 24px; }
.summary-card {
    background: rgba(17,24,39,0.8); backdrop-filter: blur(16px);
    border: 1px solid rgba(255,255,255,0.06);
    border-radius: 14px; padding: 20px;
    position: relative; overflow: hidden;
    transition: transform 0.3s, box-shadow 0.3s;
}
.summary-card:hover { transform: translateY(-4px); box-shadow: 0 8px 30px rgba(0,0,0,0.3); }
.summary-card::before {
    content: ''; position: absolute; top: 0; left: 0; right: 0; height: 3px;
    background: linear-gradient(90deg, var(--accent), transparent);
}
.summary-card .label { font-size: 12px; color: #64748b; text-transform: uppercase; letter-spacing: 1px; margin-bottom: 8px; }
.summary-card .value { font-size: 28px; font-weight: 700; color: var(--accent); }
.summary-card .sub { font-size: 12px; color: #94a3b8; margin-top: 4px; }

/* Signal Cards */
.signals-section { margin-bottom: 24px; }
.section-title {
    font-size: 16px; font-weight: 600; margin-bottom: 14px;
    display: flex; align-items: center; gap: 8px;
}
.section-title .icon { font-size: 20px; }

.signal-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(320px, 1fr)); gap: 14px; }
.signal-card {
    background: rgba(17,24,39,0.8); backdrop-filter: blur(16px);
    border: 1px solid rgba(255,255,255,0.06);
    border-radius: 14px; padding: 18px;
    transition: all 0.3s; position: relative; overflow: hidden;
}
.signal-card:hover { transform: translateY(-3px); box-shadow: 0 8px 25px rgba(0,0,0,0.3); }
.signal-card.buy { border-left: 3px solid #10b981; }
.signal-card.sell { border-left: 3px solid #ef4444; }
.signal-card.waiting { border-left: 3px solid #f59e0b; }

.signal-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }
.signal-symbol { font-size: 18px; font-weight: 700; }
.signal-badge {
    padding: 4px 12px; border-radius: 20px; font-size: 12px; font-weight: 600;
    text-transform: uppercase; letter-spacing: 0.5px;
}
.signal-badge.buy { background: rgba(16,185,129,0.2); color: #10b981; box-shadow: 0 0 12px rgba(16,185,129,0.2); }
.signal-badge.sell { background: rgba(239,68,68,0.2); color: #ef4444; box-shadow: 0 0 12px rgba(239,68,68,0.2); }
.signal-badge.waiting { background: rgba(245,158,11,0.2); color: #f59e0b; }
.signal-badge.no-breakout { background: rgba(148,163,184,0.2); color: #94a3b8; }

.signal-metrics { display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px; margin-bottom: 12px; }
.metric { text-align: center; }
.metric .m-label { font-size: 10px; color: #64748b; text-transform: uppercase; letter-spacing: 0.5px; }
.metric .m-value { font-size: 15px; font-weight: 600; margin-top: 2px; }
.metric .m-value.green { color: #10b981; }
.metric .m-value.red { color: #ef4444; }

.signal-footer { display: flex; justify-content: space-between; align-items: center; padding-top: 10px; border-top: 1px solid rgba(255,255,255,0.06); }
.pnl { font-size: 14px; font-weight: 600; }
.pnl.positive { color: #10b981; }
.pnl.negative { color: #ef4444; }
.trade-status { font-size: 12px; color: #94a3b8; }

/* Options Box */
.options-box {
    background: linear-gradient(135deg, rgba(59,130,246,0.1), rgba(139,92,246,0.1));
    border: 1px solid rgba(59,130,246,0.3);
    border-radius: 14px; padding: 20px; margin-bottom: 24px;
}
.options-box h3 { color: #3b82f6; margin-bottom: 12px; font-size: 16px; }
.option-trade {
    display: flex; align-items: center; gap: 12px;
    padding: 10px 16px; background: rgba(0,0,0,0.2); border-radius: 10px;
    margin-bottom: 8px; font-size: 14px;
}
.option-trade .direction { font-weight: 700; padding: 3px 10px; border-radius: 6px; font-size: 13px; }
.option-trade .direction.ce { background: rgba(16,185,129,0.2); color: #10b981; }
.option-trade .direction.pe { background: rgba(239,68,68,0.2); color: #ef4444; }

/* Investment Plan */
.plan-box {
    background: rgba(17,24,39,0.8); border: 1px solid rgba(16,185,129,0.2);
    border-radius: 14px; padding: 20px; margin-bottom: 24px;
}
.plan-box h3 { color: #10b981; margin-bottom: 14px; }
.plan-table { width: 100%; border-collapse: collapse; }
.plan-table th { text-align: left; padding: 8px 12px; color: #64748b; font-size: 12px; text-transform: uppercase; border-bottom: 1px solid rgba(255,255,255,0.06); }
.plan-table td { padding: 10px 12px; font-size: 14px; border-bottom: 1px solid rgba(255,255,255,0.03); }
.plan-table tr:hover { background: rgba(255,255,255,0.02); }
.plan-total { font-weight: 700; color: #10b981; }

/* No Breakout */
.no-breakout-row { display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 24px; }
.no-breakout-chip {
    padding: 6px 14px; border-radius: 8px; font-size: 13px;
    background: rgba(245,158,11,0.1); border: 1px solid rgba(245,158,11,0.2);
    color: #f59e0b;
}

/* Loading */
.loading-overlay {
    display: none; position: fixed; inset: 0;
    background: rgba(10,14,23,0.8); z-index: 100;
    display: flex; align-items: center; justify-content: center;
    flex-direction: column; gap: 16px;
}
.loading-overlay.hidden { display: none; }
.spinner {
    width: 48px; height: 48px; border: 3px solid rgba(16,185,129,0.2);
    border-top-color: #10b981; border-radius: 50%;
    animation: spin 1s linear infinite;
}
@keyframes spin { to { transform: rotate(360deg); } }
.loading-text { color: #94a3b8; font-size: 14px; }

/* Empty state */
.empty-state {
    text-align: center; padding: 60px 20px; color: #64748b;
}
.empty-state .icon { font-size: 48px; margin-bottom: 16px; }
.empty-state .title { font-size: 18px; font-weight: 600; color: #94a3b8; margin-bottom: 8px; }

/* Auto-refresh bar */
.refresh-bar {
    position: fixed; bottom: 0; left: 0; right: 0;
    background: rgba(17,24,39,0.95); border-top: 1px solid rgba(255,255,255,0.06);
    padding: 10px 32px; display: flex; justify-content: space-between; align-items: center;
    font-size: 13px; color: #64748b; z-index: 50;
}
.auto-toggle { display: flex; align-items: center; gap: 8px; cursor: pointer; }
.toggle-switch {
    width: 36px; height: 20px; background: #334155; border-radius: 10px;
    position: relative; transition: background 0.3s; cursor: pointer;
}
.toggle-switch.active { background: #10b981; }
.toggle-switch::after {
    content: ''; position: absolute; width: 16px; height: 16px;
    background: white; border-radius: 50%; top: 2px; left: 2px;
    transition: transform 0.3s;
}
.toggle-switch.active::after { transform: translateX(16px); }

/* Responsive */
@media (max-width: 768px) {
    .summary-row { grid-template-columns: repeat(2, 1fr); }
    .signal-grid { grid-template-columns: 1fr; }
    .header { padding: 12px 16px; flex-wrap: wrap; gap: 12px; }
    .main { padding: 16px; }
}

/* Scrollbar */
::-webkit-scrollbar { width: 8px; }
::-webkit-scrollbar-track { background: #0a0e17; }
::-webkit-scrollbar-thumb { background: #1e293b; border-radius: 4px; }
</style>
</head>
<body>

<header class="header">
    <div class="logo">
        <svg viewBox="0 0 24 24" fill="none" stroke="url(#grad)" stroke-width="2">
            <defs><linearGradient id="grad"><stop offset="0%" stop-color="#10b981"/><stop offset="100%" stop-color="#3b82f6"/></linearGradient></defs>
            <polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/>
        </svg>
        ORB Scanner Pro
    </div>
    <div class="header-right">
        <div class="clock" id="clock"></div>
        <div class="status-badge" id="marketStatus">
            <span class="status-dot"></span>
            <span>Market Open</span>
        </div>
        <button class="scan-btn" id="scanBtn" onclick="triggerScan()">
            ⚡ Scan Now
        </button>
    </div>
</header>

<div class="main">
    <!-- Summary -->
    <div class="summary-row" id="summaryRow">
        <div class="summary-card" style="--accent: #3b82f6;">
            <div class="label">Total Scanned</div>
            <div class="value" id="totalScanned">0</div>
            <div class="sub">Stocks + Index</div>
        </div>
        <div class="summary-card" style="--accent: #10b981;">
            <div class="label">Buy Signals</div>
            <div class="value" id="buyCount">0</div>
            <div class="sub">Bullish Breakout</div>
        </div>
        <div class="summary-card" style="--accent: #ef4444;">
            <div class="label">Sell Signals</div>
            <div class="value" id="sellCount">0</div>
            <div class="sub">Bearish Breakout</div>
        </div>
        <div class="summary-card" style="--accent: #f59e0b;">
            <div class="label">Active Trades</div>
            <div class="value" id="activeCount">0</div>
            <div class="sub">Running positions</div>
        </div>
        <div class="summary-card" style="--accent: #8b5cf6;">
            <div class="label">Target Hit</div>
            <div class="value" id="targetCount">0</div>
            <div class="sub">Profit booked</div>
        </div>
    </div>

    <!-- Options -->
    <div class="options-box" id="optionsBox" style="display:none;"></div>

    <!-- Signals -->
    <div class="signals-section">
        <div class="section-title"><span class="icon">📡</span> Live ORB Signals</div>
        <div class="signal-grid" id="signalGrid">
            <div class="empty-state">
                <div class="icon">📊</div>
                <div class="title">Click "Scan Now" to detect ORB signals</div>
                <div>Scans NIFTY, BANKNIFTY and 10 top stocks</div>
            </div>
        </div>
    </div>

    <!-- No breakout -->
    <div id="noBreakoutSection" style="display:none;">
        <div class="section-title"><span class="icon">⏳</span> Waiting for Breakout</div>
        <div class="no-breakout-row" id="noBreakoutRow"></div>
    </div>

    <!-- Investment Plan -->
    <div class="plan-box" id="planBox" style="display:none;"></div>
</div>

<!-- Loading -->
<div class="loading-overlay hidden" id="loadingOverlay">
    <div class="spinner"></div>
    <div class="loading-text">Scanning 12 symbols...</div>
</div>

<!-- Refresh bar -->
<div class="refresh-bar">
    <div>Last update: <span id="lastUpdate">Never</span></div>
    <div class="auto-toggle" onclick="toggleAutoRefresh()">
        <span>Auto-refresh (60s)</span>
        <div class="toggle-switch" id="autoToggle"></div>
    </div>
</div>

<script>
let autoRefresh = false;
let refreshInterval = null;

function updateClock() {
    const now = new Date();
    document.getElementById('clock').textContent = now.toLocaleTimeString('en-IN', {hour12: false});
    const h = now.getHours();
    const isOpen = h >= 9 && h < 16;
    const badge = document.getElementById('marketStatus');
    if (isOpen) {
        badge.className = 'status-badge';
        badge.innerHTML = '<span class="status-dot"></span><span>Market Open</span>';
    } else {
        badge.className = 'status-badge offline';
        badge.innerHTML = '<span class="status-dot"></span><span>Market Closed</span>';
    }
}
setInterval(updateClock, 1000);
updateClock();

async function triggerScan() {
    const btn = document.getElementById('scanBtn');
    btn.disabled = true;
    btn.classList.add('scanning');
    btn.textContent = '⚡ Scanning...';
    document.getElementById('loadingOverlay').classList.remove('hidden');

    await fetch('/api/scan');

    // Poll for results
    const poll = setInterval(async () => {
        const resp = await fetch('/api/results');
        const data = await resp.json();
        if (!data.scanning) {
            clearInterval(poll);
            btn.disabled = false;
            btn.classList.remove('scanning');
            btn.textContent = '⚡ Scan Now';
            document.getElementById('loadingOverlay').classList.add('hidden');
            renderResults(data);
        }
    }, 1000);
}

function renderResults(data) {
    const results = data.results || [];
    document.getElementById('lastUpdate').textContent = data.last_update || 'N/A';

    const signals = results.filter(r => r.status === 'SIGNAL');
    const waiting = results.filter(r => r.status === 'NO_BREAKOUT' || r.status === 'WAITING');
    const buys = signals.filter(s => s.signal === 'BUY');
    const sells = signals.filter(s => s.signal === 'SELL');
    const active = signals.filter(s => s.trade_status && s.trade_status.includes('ACTIVE'));
    const targets = signals.filter(s => s.trade_status && s.trade_status.includes('TARGET'));

    document.getElementById('totalScanned').textContent = results.length;
    document.getElementById('buyCount').textContent = buys.length;
    document.getElementById('sellCount').textContent = sells.length;
    document.getElementById('activeCount').textContent = active.length;
    document.getElementById('targetCount').textContent = targets.length;

    // Signal cards
    const grid = document.getElementById('signalGrid');
    if (signals.length === 0) {
        grid.innerHTML = '<div class="empty-state"><div class="icon">😴</div><div class="title">No ORB breakouts detected yet</div><div>Wait for price to break the opening range</div></div>';
    } else {
        grid.innerHTML = signals.map(s => {
            const isBuy = s.signal === 'BUY';
            const pnlClass = s.current_pnl >= 0 ? 'positive' : 'negative';
            const statusIcon = s.trade_status.includes('ACTIVE') ? '🟢' :
                              s.trade_status.includes('TARGET') ? '🎯' : '🛑';
            return `
            <div class="signal-card ${isBuy ? 'buy' : 'sell'}">
                <div class="signal-header">
                    <span class="signal-symbol">${s.symbol}</span>
                    <span class="signal-badge ${isBuy ? 'buy' : 'sell'}">${s.signal}</span>
                </div>
                <div class="signal-metrics">
                    <div class="metric">
                        <div class="m-label">Entry</div>
                        <div class="m-value">₹${s.entry.toFixed(2)}</div>
                    </div>
                    <div class="metric">
                        <div class="m-label">Stop Loss</div>
                        <div class="m-value red">₹${s.sl.toFixed(2)}</div>
                    </div>
                    <div class="metric">
                        <div class="m-label">Target</div>
                        <div class="m-value green">₹${s.target.toFixed(2)}</div>
                    </div>
                </div>
                <div class="signal-metrics">
                    <div class="metric">
                        <div class="m-label">R:R</div>
                        <div class="m-value">${s.rr.toFixed(1)}x</div>
                    </div>
                    <div class="metric">
                        <div class="m-label">Breakout</div>
                        <div class="m-value">${s.breakout_time}</div>
                    </div>
                    <div class="metric">
                        <div class="m-label">ORB Range</div>
                        <div class="m-value">₹${s.orb_range.toFixed(1)}</div>
                    </div>
                </div>
                <div class="signal-footer">
                    <span class="pnl ${pnlClass}">${s.current_pnl >= 0 ? '+' : ''}${s.current_pnl.toFixed(2)}%</span>
                    <span class="trade-status">${statusIcon} ${s.trade_status}</span>
                </div>
            </div>`;
        }).join('');
    }

    // Nifty options
    const niftySignals = signals.filter(s => s.symbol === 'NIFTY50' || s.symbol === 'BANKNIFTY');
    const optBox = document.getElementById('optionsBox');
    if (niftySignals.length > 0) {
        optBox.style.display = 'block';
        optBox.innerHTML = '<h3>💰 Nifty Options Trades</h3>' +
            niftySignals.map(s => {
                const isBuy = s.signal === 'BUY';
                const optType = isBuy ? 'CE' : 'PE';
                const strike = Math.round(s.entry / 50) * 50;
                return `<div class="option-trade">
                    <span class="direction ${optType.toLowerCase()}">${optType}</span>
                    <span>BUY ${s.symbol} ${strike} ${optType} @ ~₹200</span>
                    <span style="margin-left:auto;color:#64748b">SL: ${s.sl.toFixed(0)} | Target: ${s.target.toFixed(0)}</span>
                </div>`;
            }).join('');
    } else {
        optBox.style.display = 'none';
    }

    // No breakout
    const nbSection = document.getElementById('noBreakoutSection');
    const nbRow = document.getElementById('noBreakoutRow');
    if (waiting.length > 0) {
        nbSection.style.display = 'block';
        nbRow.innerHTML = waiting.map(w => {
            const arrow = w.dist_high_pct < w.dist_low_pct ? '↑' : '↓';
            return `<div class="no-breakout-chip">${w.symbol} ${arrow} (${w.ltp ? w.ltp.toFixed(1) : '...'})</div>`;
        }).join('');
    } else {
        nbSection.style.display = 'none';
    }

    // Investment plan
    const planBox = document.getElementById('planBox');
    const activeBuys = active.filter(s => s.signal === 'BUY' && !['NIFTY50','BANKNIFTY'].includes(s.symbol));
    if (activeBuys.length > 0) {
        let totalInv = 0;
        const rows = activeBuys.slice(0, 5).map(s => {
            const qty = Math.floor(25000 / s.entry);
            const cost = qty * s.entry;
            const pot = qty * (s.target - s.entry);
            const risk = qty * Math.abs(s.entry - s.sl);
            totalInv += cost;
            return `<tr>
                <td><strong>${s.symbol}</strong></td>
                <td>${qty}</td>
                <td>₹${s.entry.toFixed(2)}</td>
                <td>₹${cost.toLocaleString('en-IN')}</td>
                <td style="color:#10b981">+₹${pot.toFixed(0)}</td>
                <td style="color:#ef4444">-₹${risk.toFixed(0)}</td>
            </tr>`;
        }).join('');

        planBox.style.display = 'block';
        planBox.innerHTML = `<h3>📋 Investment Plan (₹25K per stock)</h3>
            <table class="plan-table">
                <thead><tr><th>Stock</th><th>Qty</th><th>Price</th><th>Cost</th><th>Potential</th><th>Risk</th></tr></thead>
                <tbody>${rows}
                <tr><td colspan="3" class="plan-total">Total Investment</td><td class="plan-total" colspan="3">₹${totalInv.toLocaleString('en-IN')}</td></tr>
                </tbody>
            </table>`;
    } else {
        planBox.style.display = 'none';
    }
}

function toggleAutoRefresh() {
    autoRefresh = !autoRefresh;
    const toggle = document.getElementById('autoToggle');
    toggle.classList.toggle('active', autoRefresh);
    if (autoRefresh) {
        refreshInterval = setInterval(triggerScan, 60000);
    } else if (refreshInterval) {
        clearInterval(refreshInterval);
    }
}

// Auto-scan on load
window.addEventListener('load', () => {
    setTimeout(triggerScan, 500);
});
</script>

</body>
</html>
"""

if __name__ == "__main__":
    print("\n  ╔═══════════════════════════════════════════╗")
    print("  ║   ORB Scanner Pro - Web Dashboard         ║")
    print("  ║   Open: http://localhost:5000              ║")
    print("  ║   Press Ctrl+C to stop                    ║")
    print("  ╚═══════════════════════════════════════════╝\n")
    app.run(host="0.0.0.0", port=5000, debug=False)
