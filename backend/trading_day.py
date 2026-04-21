"""
交易日判斷工具

以 TWSE 大盤指數 (TAIEX) 當日有無資料為唯一判斷依據。
這種做法可以自動處理國定假日、颱風臨時休市等所有情況。

Usage:
    from backend.utils.trading_day import is_trading_day
    
    if is_trading_day():
        run_scanners()
"""
import json
import logging
from datetime import date, datetime
from pathlib import Path
from typing import Optional

import requests

logger = logging.getLogger(__name__)

# 快取檔案位置 (相對於此檔案所在的 backend/utils/)
CACHE_PATH = Path(__file__).resolve().parent / "cache" / "trading_days.json"

# TWSE 每日市場成交資訊 API (比 MI_5MINS_HIST 更穩定)
# 回傳該月每個交易日的成交量/金額,只要該日有成交就一定在資料裡
TWSE_FMTQIK_API = "https://www.twse.com.tw/exchangeReport/FMTQIK"

# TWSE 需要 User-Agent,否則會回 403
REQUEST_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "zh-TW,zh;q=0.9,en;q=0.8",
}

# API 請求超時 (秒)
REQUEST_TIMEOUT = 10


def _load_cache() -> dict:
    """讀取快取檔;損毀或不存在時回傳空字典"""
    if not CACHE_PATH.exists():
        return {}
    try:
        with open(CACHE_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError) as e:
        logger.warning(f"快取檔讀取失敗,將重建: {e}")
        return {}


def _save_cache(cache: dict) -> None:
    """寫入快取檔,父目錄不存在時自動建立"""
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    try:
        with open(CACHE_PATH, "w", encoding="utf-8") as f:
            json.dump(cache, f, ensure_ascii=False, indent=2, sort_keys=True)
    except IOError as e:
        logger.error(f"快取檔寫入失敗: {e}")


def _query_twse_index(check_date: date) -> Optional[bool]:
    """
    向 TWSE FMTQIK API 查詢指定日期是否為交易日。
    
    FMTQIK 回傳該月「每日市場成交資訊」,只要該日有成交就會出現。
    比個股或指數 API 更穩定 (大盤只要有開盤一定有成交)。
    
    Returns:
        True:   當日有資料 → 有開盤
        False:  當月有其他交易日,但指定日期無資料 → 休市
        None:   API 錯誤或當月完全無資料,無法判斷 (不應快取)
    """
    params = {
        "response": "json",
        "date": check_date.strftime("%Y%m%d"),
    }
    
    try:
        resp = requests.get(
            TWSE_FMTQIK_API,
            params=params,
            headers=REQUEST_HEADERS,
            timeout=REQUEST_TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()
    except (requests.RequestException, ValueError) as e:
        logger.error(f"TWSE API 查詢失敗 {check_date}: {e}")
        return None
    
    # stat 不是 "OK" 表示該月份無任何資料 (例如查詢未來月份)
    if data.get("stat") != "OK":
        logger.warning(f"TWSE API 回應非 OK: {data.get('stat')}")
        return None
    
    rows = data.get("data", [])
    if not rows:
        return None
    
    # 資料格式: [["115/04/18", "成交股數", "成交金額", "成交筆數", "發行量加權指數", "漲跌點數"], ...]
    target_roc = f"{check_date.year - 1911}/{check_date.month:02d}/{check_date.day:02d}"
    
    for row in rows:
        if row and row[0] == target_roc:
            return True
    
    # 該月有資料,但沒找到指定日期 → 該日休市
    return False


def is_trading_day(check_date: Optional[date] = None) -> bool:
    """
    判斷指定日期台股是否有開盤。
    
    判斷順序:
    1. 週末直接回傳 False (不打 API)
    2. 檢查快取
    3. 打 TWSE API,結果寫入快取
    4. API 失敗時保守回傳 False (不快取,下次重試)
    
    Args:
        check_date: 要檢查的日期,預設為今天
    
    Returns:
        True  = 當日有開盤
        False = 休市 / 週末 / 國定假日 / API 失敗
    """
    if check_date is None:
        check_date = date.today()
    
    # 週末快速路徑:不浪費 API 配額
    if check_date.weekday() >= 5:  # 5=Sat, 6=Sun
        return False
    
    date_key = check_date.strftime("%Y-%m-%d")
    cache = _load_cache()
    
    # 命中快取
    if date_key in cache:
        return cache[date_key]
    
    # 查詢 API
    result = _query_twse_index(check_date)
    
    if result is None:
        # API 失敗或無法判斷 → 保守回傳 False,且不寫快取
        logger.warning(f"{date_key} 無法判斷交易日,保守視為休市")
        return False
    
    # 寫入快取 (歷史交易日結果不會變)
    cache[date_key] = result
    _save_cache(cache)
    
    return result


def require_trading_day(func):
    """
    Decorator: 包裝後的函式只在交易日執行,休市日直接 return None。
    
    Usage:
        @require_trading_day
        def scan_macd():
            ...
    """
    def wrapper(*args, **kwargs):
        today = date.today()
        if not is_trading_day(today):
            logger.info(f"[{func.__name__}] {today} 非交易日,略過執行")
            return None
        return func(*args, **kwargs)
    wrapper.__name__ = func.__name__
    wrapper.__doc__ = func.__doc__
    return wrapper


if __name__ == "__main__":
    # CLI 測試: python trading_day.py [YYYY-MM-DD]
    import sys
    
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    
    if len(sys.argv) > 1:
        target = datetime.strptime(sys.argv[1], "%Y-%m-%d").date()
    else:
        target = date.today()
    
    result = is_trading_day(target)
    print(f"{target} (週{'一二三四五六日'[target.weekday()]}): {'✓ 有開盤' if result else '✗ 休市'}")
