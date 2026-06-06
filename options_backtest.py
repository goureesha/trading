"""
Nifty Options Backtest - With Theta Decay + All Real Costs
"""
from backtester import run_backtest

result = run_backtest('orb', 'NIFTY50', period='3mo', interval='5m', capital=100000)
trades = result.trades
lot_size = 25
delta = 0.5
option_budget = 20000
option_premium = 200  # Rs per unit ATM
option_cost = option_premium * lot_size  # Rs.5000

# REALISTIC COSTS
theta_per_unit_per_hour = 3.5  # Rs.3.5/unit/hour for ATM weekly
bid_ask_spread = 2.0  # Rs.2 per unit each side
brokerage_per_trade = 40  # Flat brokerage
stt_rate = 0.000625  # STT on sell side

print("NIFTY OPTIONS BACKTEST WITH THETA DECAY + ALL COSTS")
print("=" * 90)
print(f"Theta: Rs.{theta_per_unit_per_hour}/unit/hour | Spread: Rs.{bid_ask_spread}/unit | Brokerage: Rs.{brokerage_per_trade}")
print()

total_pnl = 0
total_pnl_no_costs = 0
total_theta = 0
total_spread = 0
total_broker = 0
total_stt = 0
wins = 0
losses = 0
capital = option_budget

for i, t in enumerate(trades):
    entry = t['entry_price']
    exit_p = t['exit_price']
    direction = t['direction']
    bars = t.get('hold_bars', 36)
    hours = bars * 5 / 60

    if direction == 'LONG':
        spot_pts = exit_p - entry
    else:
        spot_pts = entry - exit_p

    # Option P&L (before costs)
    opt_pts = spot_pts * delta
    opt_pnl_raw = opt_pts * lot_size
    if opt_pnl_raw < -option_cost:
        opt_pnl_raw = -option_cost

    # THETA DECAY
    theta_cost = theta_per_unit_per_hour * hours * lot_size

    # BID-ASK SPREAD (entry + exit)
    spread_cost = bid_ask_spread * lot_size * 2

    # BROKERAGE
    broker_cost = brokerage_per_trade

    # STT
    sell_prem = max(10, option_premium + opt_pts)
    stt_cost = sell_prem * lot_size * stt_rate

    # TOTAL
    total_costs = theta_cost + spread_cost + broker_cost + stt_cost
    net_pnl = opt_pnl_raw - total_costs

    total_pnl += net_pnl
    total_pnl_no_costs += opt_pnl_raw
    total_theta += theta_cost
    total_spread += spread_cost
    total_broker += broker_cost
    total_stt += stt_cost
    capital += net_pnl

    if net_pnl > 0:
        wins += 1
    else:
        losses += 1

    date_str = str(t['entry_date'])[:10]
    print(f"  {i+1:>3} {date_str:<12} {direction:<6} {hours:>4.1f}h  Spot:{spot_pts:>+7.1f}  Raw:Rs.{opt_pnl_raw:>+7.0f}  Theta:-{theta_cost:>4.0f}  NET:Rs.{net_pnl:>+7.0f}  Capital:Rs.{capital:>8.0f}")

print()
print("=" * 90)
print("FINAL RESULTS: THETA + SPREAD + BROKERAGE + STT INCLUDED")
print("=" * 90)
print(f"  Starting Capital:       Rs.{option_budget:>10,}")
print(f"  Final (NO costs):       Rs.{option_budget + total_pnl_no_costs:>10,.0f}  (P&L: Rs.{total_pnl_no_costs:>+,.0f})")
print(f"  Final (WITH costs):     Rs.{capital:>10,.0f}  (P&L: Rs.{total_pnl:>+,.0f})")
print()
print(f"  COST BREAKDOWN ({len(trades)} trades):")
print(f"    Total Theta Decay:    Rs.{total_theta:>10,.0f}")
print(f"    Total Spread Cost:    Rs.{total_spread:>10,.0f}")
print(f"    Total Brokerage:      Rs.{total_broker:>10,.0f}")
print(f"    Total STT:            Rs.{total_stt:>10,.0f}")
print(f"    TOTAL COSTS:          Rs.{total_theta+total_spread+total_broker+total_stt:>10,.0f}")
print(f"    Cost per trade avg:   Rs.{(total_theta+total_spread+total_broker+total_stt)/len(trades):>10,.0f}")
print()
print(f"  TRADE STATS:")
print(f"    Total Trades:         {len(trades)}")
print(f"    Wins (after costs):   {wins} ({wins/len(trades)*100:.1f}%)")
print(f"    Losses (after costs): {losses} ({losses/len(trades)*100:.1f}%)")
print()
print(f"  RETURNS:")
print(f"    3-Month Return:       {(total_pnl/option_budget)*100:+.1f}%")
print(f"    Monthly P&L:          Rs.{total_pnl/3:>+,.0f}/month")
print(f"    Daily Avg P&L:        Rs.{total_pnl/63:>+,.0f}/day")
print(f"    Yearly Projected:     Rs.{total_pnl*4:>+,.0f}/year")
print()
