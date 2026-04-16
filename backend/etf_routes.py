from flask import Blueprint, jsonify, send_from_directory
import sqlite3
import os

etf_bp = Blueprint('etf', __name__)

DB_PATH = os.path.join(os.path.dirname(__file__), '..', 'data', 'market_data.db')


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


@etf_bp.route('/etf/00981A')
def etf_holdings_page():
    template_dir = os.path.join(os.path.dirname(__file__), '..', 'templates')
    return send_from_directory(template_dir, 'etf_holdings.html')


@etf_bp.route('/api/etf/00981A/holdings')
def api_holdings():
    try:
        conn = get_db()
        row = conn.execute("""
            SELECT data_date FROM etf_holdings_history
            WHERE etf_code = '00981A'
            ORDER BY data_date DESC LIMIT 1
        """).fetchone()
        if not row:
            return jsonify({"holdings": [], "data_date": None})
        latest_date = row["data_date"]
        holdings = conn.execute("""
            SELECT stock_code, stock_name, ratio, shares
            FROM etf_holdings_history
            WHERE etf_code = '00981A' AND data_date = ?
            ORDER BY ratio DESC
        """, (latest_date,)).fetchall()
        conn.close()
        return jsonify({"data_date": latest_date, "holdings": [dict(h) for h in holdings]})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@etf_bp.route('/api/etf/00981A/changes')
def api_changes():
    try:
        conn = get_db()
        dates = [row[0] for row in conn.execute("""
            SELECT DISTINCT data_date FROM etf_holdings_history
            WHERE etf_code = '00981A'
            ORDER BY data_date DESC LIMIT 2
        """)]
        if len(dates) < 2:
            return jsonify({"changes": [], "date_new": None, "date_old": None})
        d_new, d_old = dates[0], dates[1]
        changes = conn.execute("""
            SELECT
                n.stock_code, n.stock_name,
                n.ratio AS ratio_new, o.ratio AS ratio_old,
                n.shares AS shares_new, o.shares AS shares_old,
                (n.shares - COALESCE(o.shares, 0)) AS shares_delta
            FROM
                (SELECT * FROM etf_holdings_history WHERE etf_code='00981A' AND data_date=?) n
            LEFT JOIN
                (SELECT * FROM etf_holdings_history WHERE etf_code='00981A' AND data_date=?) o
            ON n.stock_code = o.stock_code
            WHERE shares_delta != 0
            ORDER BY ABS(shares_delta) DESC
        """, (d_new, d_old)).fetchall()
        conn.close()
        return jsonify({"date_new": d_new, "date_old": d_old, "changes": [dict(c) for c in changes]})
    except Exception as e:
        return jsonify({"error": str(e)}), 500
