"""
trading_day.py 單元測試

用已知的 2026 年日期驗證判斷邏輯:
- 交易日:  2026/04/01 (一般週間,確定有開盤)
- 休市日:  2026/04/02 (兒童節連假)
- 休市日:  2026/04/04 (連假 + 週六)
- 週末:    2026/04/11 (週六)
- 週末:    2026/04/12 (週日)

Run: python -m pytest test_trading_day.py -v
"""
import json
import tempfile
from datetime import date
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

import trading_day


@pytest.fixture
def temp_cache(monkeypatch):
    """每個測試用獨立的臨時快取,避免互相干擾"""
    with tempfile.TemporaryDirectory() as tmpdir:
        cache_path = Path(tmpdir) / "trading_days.json"
        monkeypatch.setattr(trading_day, "CACHE_PATH", cache_path)
        yield cache_path


def test_weekend_saturday_returns_false(temp_cache):
    """週六不打 API,直接回傳 False"""
    with patch.object(trading_day, "_query_twse_index") as mock_query:
        result = trading_day.is_trading_day(date(2026, 4, 11))  # 週六
        assert result is False
        mock_query.assert_not_called()


def test_weekend_sunday_returns_false(temp_cache):
    """週日不打 API,直接回傳 False"""
    with patch.object(trading_day, "_query_twse_index") as mock_query:
        result = trading_day.is_trading_day(date(2026, 4, 12))  # 週日
        assert result is False
        mock_query.assert_not_called()


def test_trading_day_hits_api_and_caches(temp_cache):
    """交易日第一次查 API,第二次用快取"""
    with patch.object(trading_day, "_query_twse_index", return_value=True) as mock_query:
        # 第一次
        assert trading_day.is_trading_day(date(2026, 4, 1)) is True
        assert mock_query.call_count == 1
        
        # 第二次應該命中快取
        assert trading_day.is_trading_day(date(2026, 4, 1)) is True
        assert mock_query.call_count == 1  # 沒有再打 API
        
    # 確認快取檔存在且內容正確
    assert temp_cache.exists()
    with open(temp_cache) as f:
        cache = json.load(f)
    assert cache == {"2026-04-01": True}


def test_holiday_cached_as_false(temp_cache):
    """休市日 (國定假日) 結果要寫入快取"""
    with patch.object(trading_day, "_query_twse_index", return_value=False):
        result = trading_day.is_trading_day(date(2026, 4, 2))  # 兒童節
        assert result is False
    
    with open(temp_cache) as f:
        cache = json.load(f)
    assert cache["2026-04-02"] is False


def test_api_failure_returns_false_without_caching(temp_cache):
    """API 失敗時回傳 False,但不寫快取(下次會重試)"""
    with patch.object(trading_day, "_query_twse_index", return_value=None):
        result = trading_day.is_trading_day(date(2026, 4, 15))
        assert result is False
    
    # 不應該有快取檔,或快取裡不該有這個日期
    if temp_cache.exists():
        with open(temp_cache) as f:
            cache = json.load(f)
        assert "2026-04-15" not in cache


def test_default_date_is_today(temp_cache):
    """不傳參數時應該用今天"""
    with patch.object(trading_day, "_query_twse_index", return_value=True) as mock_query:
        trading_day.is_trading_day()
        # 被呼叫時的日期應該是今天
        called_date = mock_query.call_args[0][0]
        assert called_date == date.today()


def test_require_trading_day_decorator_skips_on_holiday(temp_cache):
    """@require_trading_day 在休市日應該跳過函式執行"""
    calls = []
    
    @trading_day.require_trading_day
    def my_scanner():
        calls.append("executed")
        return "result"
    
    with patch.object(trading_day, "is_trading_day", return_value=False):
        result = my_scanner()
        assert result is None
        assert calls == []  # 函式完全沒被執行


def test_require_trading_day_decorator_runs_on_trading_day(temp_cache):
    """@require_trading_day 在交易日應該正常執行"""
    @trading_day.require_trading_day
    def my_scanner():
        return "scanned"
    
    with patch.object(trading_day, "is_trading_day", return_value=True):
        result = my_scanner()
        assert result == "scanned"


def test_roc_date_format_parsing(temp_cache):
    """驗證民國年格式組裝正確: 2026/04/18 → 115/04/18"""
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "stat": "OK",
        "data": [
            ["115/04/17", "20000", "20100", "19900", "20050"],
            ["115/04/18", "20050", "20200", "20000", "20150"],
            ["115/04/21", "20150", "20300", "20100", "20250"],
        ],
    }
    mock_response.raise_for_status = MagicMock()
    
    with patch.object(trading_day.requests, "get", return_value=mock_response):
        # 有資料的日期
        assert trading_day._query_twse_index(date(2026, 4, 18)) is True
        # 沒有資料的日期 (假設是 4/20,週一但沒出現在 data 中)
        assert trading_day._query_twse_index(date(2026, 4, 20)) is False
