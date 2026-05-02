#!/usr/bin/env python3
"""
[助手] 從 cmoney_themes_all.json 自動找出 themes_config_cmoney.json 該填的 ID

讀入: data/cmoney_themes_all.json (1b 產出)
讀入: config/themes_config_cmoney.json (你想要的題材清單)
輸出: 列印對照表 + 半自動更新 config 檔

用法:
  python3 4b_match_cmoney_ids.py            # 只列印對照, 不寫入
  python3 4b_match_cmoney_ids.py --apply    # 自動填回 config 檔
"""
import json
import os
import sys
import argparse

THEMES_PATH = "data/cmoney_themes_all.json"
CONFIG_PATH = "config/themes_config_cmoney.json"


def find_match(target: str, themes: dict) -> list:
    """從 themes 中找出名稱含 target (或部分匹配) 的所有 ID"""
    target_lower = target.lower()
    matches = []
    for cid, name in themes.items():
        name_lower = name.lower()
        # 完全相等
        if name_lower == target_lower:
            return [(cid, name, "完全匹配")]
        # 包含
        if target_lower in name_lower or name_lower in target_lower:
            matches.append((cid, name, "部分匹配"))
    return matches


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true",
                        help="自動填回 config 檔 (僅更新 ID 為空字串的項目)")
    args = parser.parse_args()

    if not os.path.exists(THEMES_PATH):
        print(f"❌ 找不到 {THEMES_PATH}, 請先執行 1b_fetch_cmoney_themes.py")
        sys.exit(1)
    if not os.path.exists(CONFIG_PATH):
        print(f"❌ 找不到 {CONFIG_PATH}")
        sys.exit(1)

    with open(THEMES_PATH, encoding="utf-8") as f:
        themes = json.load(f)["themes"]

    with open(CONFIG_PATH, encoding="utf-8") as f:
        config = json.load(f)

    raw = config["themes"]
    print(f"=== 為 {len(raw)} 個 config 項目查找對應 CMoney ID ===")
    print(f"  (CMoney 全部 {len(themes)} 個概念股)\n")

    updates = {}
    ambiguous = {}

    for theme_key, current_id in raw.items():
        if theme_key.startswith("_"):
            continue
        if current_id and current_id.startswith("C"):
            print(f"  ✓ {theme_key:<25s} 已設定 = {current_id}")
            continue

        matches = find_match(theme_key, themes)
        if not matches:
            print(f"  ❌ {theme_key:<25s} 找不到匹配")
        elif len(matches) == 1:
            cid, name, kind = matches[0]
            print(f"  🎯 {theme_key:<25s} {kind} → {cid} ({name})")
            updates[theme_key] = cid
        else:
            # 多個候選: 優先選完全匹配, 否則列出所有候選讓用戶決定
            exact = [m for m in matches if m[2] == "完全匹配"]
            if exact:
                cid, name, _ = exact[0]
                updates[theme_key] = cid
                print(f"  🎯 {theme_key:<25s} 完全匹配 → {cid} ({name})")
            else:
                print(f"  ⚠️  {theme_key:<25s} 多個候選:")
                for cid, name, kind in matches[:5]:
                    print(f"        {cid}  {name}  ({kind})")
                ambiguous[theme_key] = matches

    # 寫回
    if args.apply and updates:
        print(f"\n=== 寫入 {len(updates)} 個自動匹配項目 ===")
        for k, v in updates.items():
            config["themes"][k] = v
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
        print(f"已更新: {CONFIG_PATH}")

    if ambiguous:
        print(f"\n⚠️  {len(ambiguous)} 個項目需手動決定, 請編輯 {CONFIG_PATH}")
        print("    (手動把對應 C50XXX ID 填到該題材的 value)")

    if updates and not args.apply:
        print(f"\n💡 確認無誤後加 --apply 自動寫入 config 檔")


if __name__ == "__main__":
    main()
