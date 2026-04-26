"""從 market_data.db 抓出大盤摘要需要的資料。"""

import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "data" / "market_data.db"


def _connect():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _fmt_yi(n):
    """資料已經是『億』為單位,直接加正負號。"""
    if n is None:
        return "N/A"
    return f"{n:+.2f}億"


def _fmt_lots(n):
    """期貨口數,加正負號 + 千分位。"""
    if n is None:
        return "N/A"
    return f"{n:+,d}口"


def _fmt_date(d):
    """20260424 → 2026-04-24"""
    if not d or len(str(d)) != 8:
        return str(d)
    s = str(d)
    return f"{s[:4]}-{s[4:6]}-{s[6:8]}"


def build_market_context() -> dict:
    conn = _connect()
    cur = conn.cursor()

    cur.execute("SELECT * FROM market_breadth ORDER BY date DESC LIMIT 2")
    breadth_rows = cur.fetchall()
    if not breadth_rows:
        conn.close()
        return None
    latest_breadth = breadth_rows[0]
    prev_breadth = breadth_rows[1] if len(breadth_rows) > 1 else None
    latest_date = latest_breadth["date"]

    cur.execute("SELECT * FROM institutional_money WHERE date = ?", (latest_date,))
    inst = cur.fetchone()

    cur.execute("SELECT * FROM mxf_futures_data WHERE date = ?", (latest_date,))
    mxf = cur.fetchone()

    cur.execute("SELECT * FROM futures_data WHERE date = ?", (latest_date,))
    fut = cur.fetchone()

    cur.execute("SELECT * FROM margin_data ORDER BY date DESC LIMIT 2")
    margin_rows = cur.fetchall()
    latest_margin = margin_rows[0] if margin_rows else None
    prev_margin = margin_rows[1] if len(margin_rows) > 1 else None

    conn.close()

    # 大盤指數變化
    taiex_change = 0
    taiex_change_pct = 0
    if prev_breadth and latest_breadth["taiex_close"] and prev_breadth["taiex_close"]:
        taiex_change = latest_breadth["taiex_close"] - prev_breadth["taiex_close"]
        taiex_change_pct = taiex_change / prev_breadth["taiex_close"] * 100

    # 融資餘額變化(資料以億為單位)
    margin_change = None
    if (latest_margin and prev_margin
            and latest_margin["margin_balance"] is not None
            and prev_margin["margin_balance"] is not None):
        margin_change = latest_margin["margin_balance"] - prev_margin["margin_balance"]

    # 自營商合計(自買 + 避險)
    dealer_total = None
    if inst:
        dealer_total = (inst["dealer_self_diff"] or 0) + (inst["dealer_hedge_diff"] or 0)

    ctx = {
        "date": _fmt_date(latest_date),

        # 大盤
        "taiex_close": latest_breadth["taiex_close"],
        "taiex_change": taiex_change,
        "taiex_change_pct": taiex_change_pct,
        "up_count": latest_breadth["up_count"],
        "down_count": latest_breadth["down_count"],
        "unchanged": latest_breadth["unchanged"],
        "up_ratio": latest_breadth["up_ratio"] or 0,  # 已經是百分比
        "new_highs": latest_breadth["new_highs"] if latest_breadth["new_highs"] is not None else "N/A",
        "new_lows": latest_breadth["new_lows"] if latest_breadth["new_lows"] is not None else "N/A",
        "up_limit": latest_breadth["up_limit"],
        "down_limit": latest_breadth["down_limit"],

        # 三大法人現股(資料已是億)
        "foreign_diff": _fmt_yi(inst["foreign_diff"]) if inst else "N/A",
        "trust_diff": _fmt_yi(inst["trust_diff"]) if inst else "N/A",
        "dealer_diff": _fmt_yi(dealer_total),
        "total_inst_diff": _fmt_yi(inst["total_diff"]) if inst else "N/A",

        # 期貨總體
        "fut_foreign_net": _fmt_lots(fut["foreign_net"]) if fut else "N/A",
        "fut_trust_net": _fmt_lots(fut["trust_net"]) if fut else "N/A",
        "fut_dealer_net": _fmt_lots(fut["dealer_net"]) if fut else "N/A",
        "fut_retail_ratio": f"{fut['retail_ratio']:.2f}" if fut and fut["retail_ratio"] is not None else "N/A",
        "pcr_volume": f"{fut['pcr_volume']:.2f}" if fut and fut["pcr_volume"] is not None else "N/A",

        # 小台散戶
        "mxf_retail_net": _fmt_lots(mxf["retail_net"]) if mxf else "N/A",
        # 注意:這個欄位存的是百分比(-35.77 表示散戶 -35.77% 偏空)
        "mxf_retail_ratio_pct": f"{mxf['retail_ratio']:+.2f}%" if mxf and mxf["retail_ratio"] is not None else "N/A",

        # 融資(資料已是億)
        "margin_balance": _fmt_yi(latest_margin["margin_balance"]) if latest_margin else "N/A",
        "margin_change": _fmt_yi(margin_change),
    }

    return ctx

