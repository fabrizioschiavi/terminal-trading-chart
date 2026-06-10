#!/usr/bin/env python3
"""
Terminal Trading Chart
Based on the concept by Fabrizio Schiavi (fsd.it)
https://github.com/fabrizioschiavi/terminal-trading-chart

- Y-axis: real asset prices
- Each column occupies only the H-L range of the candle
- Cells in range: sell (red, bottom) / buy (green, top)
  with glyph determined by component volume vs median
- 3 dates on X-axis: start / middle / end of period

Usage:
    python terminal_chart.py [TICKER] [PERIOD] [INTERVAL]

Examples:
    python terminal_chart.py BTC-EUR 60d 1d
    python terminal_chart.py AAPL 60d 1d
    python terminal_chart.py EURUSD=X 30d 1h
    python terminal_chart.py DEMO

Requirements:
    pip install yfinance
"""

import sys
import os
import datetime

# ── ANSI colours ────────────────────────────────────────────────────────────
RESET     = "\033[0m"
BOLD      = "\033[1m"
FG_GREEN  = "\033[38;2;0;210;85m"
FG_RED    = "\033[38;2;215;55;55m"
FG_YELLOW = "\033[38;2;255;215;0m"
FG_GRAY   = "\033[38;2;85;95;85m"
FG_WHITE  = "\033[38;2;185;195;185m"
FG_LIME   = "\033[38;2;130;255;130m"
FG_ROSE   = "\033[38;2;255;105;105m"
FG_LGRAY  = "\033[38;2;135;145;135m"
BG_DARK   = "\033[48;2;36;40;36m"

# ── Unicode glyphs ──────────────────────────────────────────────────────────
DOT       = "\u22c5"
BULLET    = "\u2219"
BAR_THIN  = "\u2502"
BAR_MED   = "\u2503"
BAR_THICK = "\u2588"


def glyph_for_vol(volume: float, median: float) -> str:
    """Glyph based on total volume vs global median."""
    if median <= 0:
        return BAR_THIN
    r = volume / median
    if r >= 3.0:
        return BAR_THICK    # █  very high volume
    elif r >= 2.0:
        return BAR_MED      # ┃  high volume
    else:
        return BAR_THIN     # │  normal volume


def sell_buy_split(o, h, l, c):
    """
    Estimate sell% and buy% from close position within H-L range.
    Close near high → buying prevails (high buy_frac).
    Returns (sell_frac, buy_frac).
    """
    rng = h - l
    if rng < 1e-12:
        return 0.5, 0.5
    buy_frac = (c - l) / rng
    sell_frac = 1.0 - buy_frac
    return sell_frac, buy_frac


def find_resistance_support(rows):
    """
    Returns (resistance_price, support_price):
    most prominent swing high and swing low with 5-bar window.
    """
    highs = [r[2] for r in rows]
    lows = [r[3] for r in rows]
    n = 5
    best_res = (0.0, None)
    best_sup = (0.0, None)
    for i in range(n, len(rows) - n):
        wh = highs[i-n:i] + highs[i+1:i+n+1]
        wl = lows[i-n:i] + lows[i+1:i+n+1]
        if highs[i] > max(wh):
            p = highs[i] - max(wh)
            if p > best_res[0]:
                best_res = (p, highs[i])
        if lows[i] < min(wl):
            p = min(wl) - lows[i]
            if p > best_sup[0]:
                best_sup = (p, lows[i])
    return best_res[1], best_sup[1]


def median(values):
    s = sorted(values)
    n = len(s)
    if n == 0:
        return 1.0
    mid = n // 2
    return (s[mid] + s[~mid]) / 2.0


def auto_dec(price_max):
    if price_max < 0.1:
        return 6
    if price_max < 1:
        return 5
    if price_max < 10:
        return 4
    if price_max < 1000:
        return 2
    return 0


def render(rows, ticker: str = "", chart_height: int = 32):
    try:
        t_cols = os.get_terminal_size().columns
    except OSError:
        t_cols = 120

    chart_width = min(len(rows), (t_cols - 12) // 2)
    rows = rows[-chart_width:]

    dates = [r[0] for r in rows]
    opens = [r[1] for r in rows]
    highs = [r[2] for r in rows]
    lows = [r[3] for r in rows]
    closes = [r[4] for r in rows]
    volumes = [r[5] for r in rows]

    price_max = max(highs)
    price_min = min(lows)
    price_range = price_max - price_min or 1e-9
    step = price_range / chart_height
    vol_med = median(volumes)
    dec = auto_dec(price_max)
    fmt = f"{{:.{dec}f}}"
    axis_w = len(fmt.format(price_max)) + 1
    resistance, support = find_resistance_support(rows)

    def price_to_row(p):
        r = int((price_max - p) / price_range * chart_height)
        return max(0, min(chart_height - 1, r))

    cols = len(rows)
    grid = [[(DOT, FG_GRAY)] * cols for _ in range(chart_height)]

    for col, (o, h, l, c, v) in enumerate(zip(opens, highs, lows, closes, volumes)):
        sell_frac, buy_frac = sell_buy_split(o, h, l, c)
        
        # Determine glyph based on TOTAL volume
        glyph = glyph_for_vol(v, vol_med)
        
        row_h = price_to_row(h)
        row_l = price_to_row(l)
        total_cells = row_l - row_h + 1
        if total_cells < 1:
            total_cells = 1
        
        # Calculate buy (green) and sell (red) cells
        # buy (green) on top, sell (red) on bottom
        buy_cells = max(1, round(buy_frac * total_cells))
        buy_cells = min(buy_cells, total_cells - 1) if total_cells > 1 else 1
        sell_cells = total_cells - buy_cells

        for row in range(row_h, row_l + 1):
            offset = row - row_h  # 0 = top cell (highest price)
            
            # First buy_cells rows are GREEN (buying)
            if offset < buy_cells:
                grid[row][col] = (glyph, FG_GREEN)
            else:
                grid[row][col] = (glyph, FG_RED)

    lines = []
    header = f" {ticker}  (last {len(rows)} bars)"
    lines.append(BG_DARK + FG_YELLOW + BOLD + header + RESET)
    lines.append("")

    for row_idx in range(chart_height):
        row_price = price_max - row_idx * step
        if row_idx == 0:
            lbl_col = FG_LIME
        elif row_idx == chart_height - 1:
            lbl_col = FG_ROSE
        else:
            lbl_col = FG_WHITE

        label = fmt.format(row_price).rjust(axis_w)
        line_parts = [BG_DARK + lbl_col + label + " " + RESET + BG_DARK]

        near_res = (resistance is not None and abs(row_price - resistance) < step * 0.6)
        near_sup = (support is not None and abs(row_price - support) < step * 0.6)

        for col in range(cols):
            ch, col_c = grid[row_idx][col]
            if (near_res or near_sup) and ch == DOT:
                ch = BULLET
                col_c = FG_GRAY
            line_parts.append(col_c + ch + " ")

        line_parts.append(RESET)
        lines.append("".join(line_parts))

    lines.append(_date_axis(dates, axis_w, cols))
    lines.append("")
    _legend(lines)

    if sys.platform == "win32":
        import ctypes
        k = ctypes.windll.kernel32
        k.SetConsoleMode(k.GetStdHandle(-11), 7)

    print("\n".join(lines))


def _date_axis(dates, axis_w, cols):
    def fmt_date(d):
        if isinstance(d, (datetime.datetime, datetime.date)):
            return f"{d.day}-{d.month}"
        try:
            return f"{d.day}-{d.month}"
        except AttributeError:
            return str(d)[:5]

    left = fmt_date(dates[0])
    mid = fmt_date(dates[len(dates) // 2])
    right = fmt_date(dates[-1])

    left_pos = 0
    mid_pos = (len(dates) // 2) * 2
    right_pos = (len(dates) - 1) * 2
    total_chars = cols * 2
    row = [" "] * total_chars

    def place(pos, text):
        for i, ch in enumerate(text):
            idx = pos + i
            if 0 <= idx < total_chars:
                row[idx] = ch

    place(left_pos, left)
    place(mid_pos - len(mid) // 2, mid)
    place(right_pos - len(right) + 1, right)

    prefix = " " * (axis_w + 1)
    return BG_DARK + FG_LGRAY + prefix + "".join(row) + RESET


def _legend(lines):
    U2502, U2503, U2588 = "\u2502", "\u2503", "\u2588"
    U2219, U22C5 = "\u2219", "\u22c5"
    R, G, L = FG_RED, FG_GREEN, FG_LGRAY

    def row(sym, s_label, b_label):
        return (BG_DARK + R + sym + " " + L + s_label.ljust(40) +
                G + sym + " " + L + b_label + RESET)

    lines += [
        BG_DARK + RESET,
        "  " + G + "GREEN ↑" + L + " = buying (top)        " + R + "RED ↓" + L + " = selling (bottom)",
        "",
        row(U2502, "normal volume   (< 2× median)",
                   "normal volume   (< 2× median)"),
        row(U2503, "high volume     (≥ 2× median)",
                   "high volume     (≥ 2× median)"),
        row(U2588, "very high volume(≥ 3× median)",
                   "very high volume(≥ 3× median)"),
        "",
        (BG_DARK + FG_LGRAY + U2219 + " resistance / support     " +
         U22C5 + " grid points" + RESET),
        BG_DARK + FG_LGRAY + "© Fabrizio Schiavi fsd.it  |  Python implementation" + RESET,
        "",
    ]


def demo_data():
    """Synthetic BTC-EUR-like data (~40,000–52,000 EUR)."""
    import random
    random.seed(7)
    price = 46_000.0
    rows = []
    base_vol = 12_000
    date = datetime.date(2026, 1, 2)
    for _ in range(60):
        o = price
        drift = random.uniform(-800, 800)
        rng = random.uniform(300, 1800)
        h = o + rng * random.uniform(0.3, 1.0)
        l = o - rng * random.uniform(0.3, 1.0)
        c = max(l + 50, min(h - 50, o + drift))
        vol = int(base_vol * random.choice([0.5, 0.7, 0.8, 1.0, 1.0, 1.2, 1.5, 2.0, 2.2, 3.0, 3.5]))
        rows.append((date, o, h, l, c, vol))
        price = c
        date += datetime.timedelta(days=1)
    return rows


def main():
    ticker = sys.argv[1] if len(sys.argv) > 1 else "BTC-EUR"
    period = sys.argv[2] if len(sys.argv) > 2 else "60d"
    interval = sys.argv[3] if len(sys.argv) > 3 else "1d"

    if ticker.upper() == "DEMO":
        print("\n  [DEMO MODE – synthetic data]\n")
        raw = demo_data()
        render(raw, ticker="DEMO")
        return

    print(f"\n  Downloading {ticker}  period={period}  interval={interval} …\n")
    
    try:
        import yfinance as yf
        import pandas as pd
        
        print("  Fetching data...")
        
        end_date = datetime.datetime.now()
        days_map = {"60d": 60, "30d": 30, "90d": 90, "1mo": 30, "2mo": 60, "3mo": 90, "6mo": 180, "1y": 365}
        days = days_map.get(period, 90)
        start_date = end_date - datetime.timedelta(days=days)
        
        df = yf.download(
            ticker,
            start=start_date.strftime("%Y-%m-%d"),
            end=end_date.strftime("%Y-%m-%d"),
            interval=interval,
            progress=False,
            auto_adjust=True
        )
        
        if df.empty:
            raise ValueError("Empty DataFrame")
        
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        
        required = ["Open", "High", "Low", "Close", "Volume"]
        available = [c for c in required if c in df.columns]
        
        if len(available) < 5:
            raise ValueError(f"Missing columns: {set(required) - set(available)}")
        
        df = df[required].dropna()
        
        if len(df) == 0:
            raise ValueError("No valid data")
        
        raw = [
            (idx, float(r.Open), float(r.High), float(r.Low), float(r.Close), float(r.Volume))
            for idx, r in df.iterrows()
        ]
        print(f"  ✓ {len(raw)} bars downloaded.\n")
        render(raw, ticker=ticker.upper())
        
    except Exception as e:
        print(f"\n  ✗ Download failed: {e}\n")
        print("  → Using DEMO mode:\n")
        raw = demo_data()
        render(raw, ticker=f"{ticker.upper()} (DEMO)")


if __name__ == "__main__":
    main()