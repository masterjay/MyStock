import requests
import json
import os
from datetime import datetime

WATCHLIST_PAGES = {
    "輝達Rubin供應鏈": "326786bf-fb4b-8101-b885-ffa61bf19b2b",
    "Feynman架構相關": "326786bf-fb4b-81a6-a930-efda029e5ac4",
}

def get_headers():
    token = os.environ.get("NOTION_TOKEN")
    if not token:
        raise Exception("❌ NOTION_TOKEN 未設定")
    return {
        "Authorization": f"Bearer {token}",
        "Notion-Version": "2022-06-28"
    }

def fetch_blocks(block_id):
    all_results = []
    headers = get_headers()
    url = f"https://api.notion.com/v1/blocks/{block_id}/children"
    while url:
        res = requests.get(url, headers=headers).json()
        all_results.extend(res.get("results", []))
        cursor = res.get("next_cursor")
        url = f"https://api.notion.com/v1/blocks/{block_id}/children?start_cursor={cursor}" if cursor else None
    return all_results

def find_code_column(header_row):
    """自動找代號/代碼欄的 index"""
    for i, cell in enumerate(header_row):
        if cell:
            text = cell[0]["plain_text"].strip()
            if any(k in text for k in ["代號", "代碼", "股票代", "Code"]):
                return i
    return None

def extract_codes(page_id):
    codes = []
    blocks = fetch_blocks(page_id)
    for block in blocks:
        if block["type"] == "table":
            rows = fetch_blocks(block["id"])
            if not rows:
                continue
            # 用第一行（header）找代號欄位
            header_cells = rows[0].get("table_row", {}).get("cells", [])
            code_col = find_code_column(header_cells)
            if code_col is None:
                print(f"  ⚠️ 找不到代號欄位，header: {[c[0]['plain_text'] if c else '' for c in header_cells]}")
                continue
            for row in rows[1:]:
                cells = row.get("table_row", {}).get("cells", [])
                if len(cells) > code_col and cells[code_col]:
                    code = cells[code_col][0]["plain_text"].strip()
                    if code.isdigit():
                        codes.append(code)
    return codes

def build_watchlist():
    result = {
        "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "themes": {}
    }
    for name, page_id in WATCHLIST_PAGES.items():
        codes = extract_codes(page_id)
        result["themes"][name] = codes
        print(f"✅ {name}: {len(codes)} 檔 → {codes}")

    out = os.path.join(os.path.dirname(__file__), "../watchlist_notion.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"\n📁 已輸出：{os.path.abspath(out)}")

if __name__ == "__main__":
    build_watchlist()
