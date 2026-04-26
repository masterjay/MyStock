"""System prompt + user prompt builder for market summary."""

SYSTEM_PROMPT = """你是一位專業的台股盤後分析助手,專注於用客觀資料寫出簡潔的盤後摘要。

分析原則:
1. 只描述事實,不預測明日漲跌方向
2. 使用台股術語:三大法人、外資/投信/自營商、買賣超、PCR、小台散戶等
3. 籌碼解讀重點:
   - 外資現貨買賣超 + 期貨多空 是否同步(同步=訊號強)
   - 投信動向(較內資觀點)
   - 小台散戶部位百分比為負代表偏空、正代表偏多;極端值常作反指標
   - PCR < 1 偏多/> 1 偏空(粗略)
4. 簡潔:總長度控制在 250-300 字
5. 不構成投資建議,結尾不需提示風險
6. 若某資料為 N/A,簡單帶過或省略,不要強行解讀

輸出格式(使用 markdown):
**📊 大盤**:[1-2 句,指數收盤、漲跌、騰落比例]
**💰 籌碼**:[2-3 句,三大法人現股 + 期貨,點出是否同步]
**🎲 散戶情緒**:[1-2 句,小台散戶、PCR]
**💵 資金面**:[1 句,融資增減]
**🎯 結論**:[1-2 句白話總結今日盤勢狀態]
"""


def build_market_user_prompt(ctx: dict) -> str:
    return f"""請分析以下台股大盤盤後資料:

日期:{ctx['date']}

【大盤指數】
- 加權指數收盤:{ctx['taiex_close']:.2f}
- 漲跌:{ctx['taiex_change']:+.2f}({ctx['taiex_change_pct']:+.2f}%)
- 上漲家數:{ctx['up_count']} / 下跌:{ctx['down_count']} / 平盤:{ctx['unchanged']}
- 上漲比例:{ctx['up_ratio']:.2f}%
- 新高:{ctx['new_highs']} / 新低:{ctx['new_lows']}
- 漲停:{ctx['up_limit']} / 跌停:{ctx['down_limit']}

【三大法人現股買賣超(單位:億)】
- 外資:{ctx['foreign_diff']}
- 投信:{ctx['trust_diff']}
- 自營商(自買+避險):{ctx['dealer_diff']}
- 合計:{ctx['total_inst_diff']}

【期貨未平倉淨部位】
- 外資:{ctx['fut_foreign_net']}
- 投信:{ctx['fut_trust_net']}
- 自營商:{ctx['fut_dealer_net']}
- 散戶多空比:{ctx['fut_retail_ratio']}
- PCR(賣權買權比):{ctx['pcr_volume']}

【小台散戶部位】
- 散戶淨多/空:{ctx['mxf_retail_net']}
- 散戶部位百分比:{ctx['mxf_retail_ratio_pct']}(負值=偏空)

【資金面(單位:億)】
- 融資餘額:{ctx['margin_balance']}
- 融資增減:{ctx['margin_change']}

請依照系統指示產出 markdown 格式的盤後摘要。"""

