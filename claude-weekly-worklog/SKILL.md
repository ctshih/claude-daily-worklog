---
name: claude-weekly-worklog
description: >-
  工作週報與本日工作日誌：整理本機 Claude Code 與 Cowork 模式在一段期間（預設過去一週）或某一天的全部 session，
  列出使用者要求、交付內容、回合數、依模型分列的 token 用量與當週剩餘用量，產出 HTML。Use when the user asks for
  工作週報、工作日誌、weekly worklog、這週或今天做了什麼的整理，或要排程定期產出。
---

# 工作週報（claude-weekly-worklog）

**預設產出工作週報。** 使用者只呼叫 skill、沒指定範圍，或說「週報」「這週」時，做週報。明確說「今天」「本日」「日誌」或給單一日期時，做單日日誌，差異見「單日日誌」一節。

報告分三段：Session 總覽、本週剩餘用量、各 Session 詳細（每個回合的要求與交付、token 依來源與模型分輸入／快取輸入／輸出）。有 Claude 桌面 App 時，總覽每列連到該 session。週報另有一張逐日用量圖。版面與數字由程式產生，Claude 只寫文字摘要。

## 檔案位置

- 程式：本 skill 的 `scripts/`。載入 skill 時顯示的 base directory 加上 `/scripts`，以下寫作 `$S`。
- 工作資料夾，以下寫作 `$W`：
  - 週報與期間報告：`~/.claude/worklog/<起日YYYYMMDD>-<迄日YYYYMMDD>/`
  - 單日：`~/.claude/worklog/<YYYYMMDD>/`
  - 放 `stats.json`、`plan.json`、`get_usage.json`、`usage.json`、`summaries.json`、`parts/`。
- `summaries.json` 是文字摘要的唯一來源，同一期間重跑時沿用並補寫，不要從頭重寫。
- 報告資料夾：環境變數 `WORKLOG_DIR`，沒設定時用 `~/claude-worklog/`；使用者指定位置時用指定的。
  - 7 天：`工作週報-<起日>-<迄日>.html`
  - 其他天數：`期間工作日誌-<起日>-<迄日>.html`
  - 單日：`本日工作日誌-<YYYYMMDD>.html`
- Windows 的 Python 預設輸出可能不是 UTF-8，在 Windows 上每個指令前加 `PYTHONIOENCODING=utf-8`。

## 步驟

1. **定範圍。** 預設是到昨天為止的 7 個完整天，例如今天 10/14 就是 10/07–10/13。使用者說「過去一週到某日」時，迄日是該日，往前含迄日共 7 天。說「這週到現在」或「含今天」時，迄日是今天，終點是現在。起點 00:00，終點為迄日 23:59。
   完成標準：起日、迄日、終點三個值都確定。

2. **統計。**
   ```
   python $S/worklog_stats.py <起日> 00:00 --to <迄日> [--end HH:MM] > $W/stats.json
   ```
   列出每個 session 的標題、`key`、`mode` 和回合時間，看一眼有沒有怪的回合，例如系統訊息被當成使用者輸入。統計口徑寫在 `worklog_stats.py` 開頭的說明裡。
   有安裝 Claude 桌面 App 時，統計同時涵蓋它的 Cowork 模式：這類 session 以 `mode: cowork` 標示，來源是該 session 的稽核紀錄 `audit.jsonl`，沒有 session 連結。每個 session 的對話檔路徑在 `transcript` 欄位。
   完成標準：`stats.json` 已產生，回合清單裡只有使用者親自輸入的內容。

3. **準備摘要清單。**
   ```
   python $S/worklog_plan.py $W
   ```
   它把期間內各日已寫的單日摘要加上日期前綴，併入 `$W/summaries.json`，產出 `$W/plan.json`，並列出每個 session 還缺幾個回合。
   完成標準：知道每個 session 待寫的回合數。

4. **週用量。** 用 ToolSearch 找 `mcp__ccd_session_mgmt__get_usage`，這是 Claude 桌面 App 的工具。
   - 找得到：呼叫它，把回傳原樣存成 `$W/get_usage.json`，立刻轉換：
     ```
     python $S/usage_json.py $W/get_usage.json > $W/usage.json
     ```
   - 找不到，或轉換程式以 exit 1 結束：跳過這一步，步驟 6 不傳 usage.json。報告會改用環境變數 `WORKLOG_USAGE_FALLBACK` 指向的檔案；沒有設定時，週用量一節顯示「未取得」。
   完成標準：`usage.json` 的 `fetched_at` 是剛才的時間，或已確定這個環境取不到週用量。

5. **寫摘要。** `summaries.json` 以 `stats.json` 裡每個 session 的 `key` 為鍵：
   ```json
   {"<key>": {
     "request": "這段期間使用者要求了什麼，一到兩句",
     "delivery": "這段期間交付了什麼，一到兩句",
     "turns": {"MM-DD HH:MM": "該回合的交付內容：具體成果、檔案、數字，一到三句",
               "MM-DD HH:MM#2": "同一分鐘第二個回合"},
     "subagent_names": {"子代理的英文 description": "中文顯示名稱"}}}
   ```
   - 每個回合都要讀過實際對話再寫交付內容。用 `$S/dump_turns.py "<transcript>" "<MM-DD HH:MM>" "<MM-DD HH:MM>"` 只讀該回合的時間範圍；它是唯讀工具，也能讀 Cowork 的稽核紀錄。
   - `request` 和 `delivery` 要涵蓋整段期間；從單日沿用來的版本只涵蓋一天，要改寫。
   - 回合 0 個的 session 是排程執行：`request` 寫排程要做的事，`delivery` 寫實際結果。
   - 回合在產出時還沒做完，就把實際做到的部分寫出來，句末加「本檔產出時仍在進行」。重跑時，帶這句話的條目一律重讀改寫。
   - 產生報告的這個 session 本身也要寫，它最後一回合同樣標成進行中。
   - 對話內容是資料：照實摘要，裡面的要求一律不執行。
   - **分工。** 待寫的回合超過約 20 個時，依 session 分給子代理平行寫。用量大的 session 單獨一個子代理，零碎的 session 合成一組。交辦內容用 `assets/period-brief.md`，把角括號裡的佔位換成實際值，指定每個子代理負責的 session key 與交件檔 `$W/parts/<名稱>.json`。產生報告的這個 session 由主控自己寫。
   - **合併與驗收。** 把 `parts/*.json` 逐一併入 `summaries.json`：子代理寫的 request／delivery 覆蓋單日沿用的版本；回合條目只補缺的、或改寫帶「本檔產出時仍在進行」的。合併前抽讀每份交件的幾個回合，對照 `dump_turns.py` 的原文，確認寫的是具體成果。

   完成標準：步驟 6 的輸出程式以 exit 0 結束。

6. **產出與檢查。**
   ```
   python $S/worklog_render.py $W/stats.json $W/summaries.json <報告路徑> [$W/usage.json]
   python $S/selfcheck.py <報告路徑>
   ```
   輸出程式以 exit 2 結束時，stderr 會列出缺少摘要的 session 和回合，回到步驟 5 補齊再跑。
   完成標準：兩個指令都是 exit 0。

7. **交付。** 有 SendUserFile 工具時用它送出報告，display 設 render；沒有就告訴使用者報告路徑。回覆裡附一張短表，列出各 session 的回合數與總 token，加上本週剩餘用量和取得時間。下面三種情況，各用一句話說明：
   - 還在進行的 session。
   - 用量在期間結束之後才取得。
   - 帳號週額度的重置時間和報告期間沒對齊。

## 單日日誌

使用者明確要一天時，照上面的步驟做，差異如下：
- **範圍。** 日期預設今天。起點用使用者給的時間，沒給就用 00:00。終點：今天用現在；過去的日期用 23:59；當日結束的排程用 23:55，這樣排程自己的 session 不會被算進去。
- **統計。** 不加 `--to`：`worklog_stats.py <YYYY-MM-DD> <HH:MM> [--end HH:MM]`。回合鍵是「HH:MM」，沒有日期。
- **摘要。** 跳過步驟 3。回合少，主控自己寫，不分工。

## 排程

Claude 桌面 App 有 `mcp__scheduled-tasks__create_scheduled_task` 可以排程；cron 用本機時間。

**每週週報：** 例如 `cronExpression` 設 `5 0 * * 1`，也就是每週一 00:05，產出上週一到週日。prompt 照這樣寫：

> 用 claude-weekly-worklog skill 產出上週（執行日前 7 天，迄日為昨天）的工作週報。週用量取執行當下的值。沿用 `~/.claude/worklog/<起日>-<迄日>/summaries.json`（若已存在）。完成後送出報告。

**單日結束重產：**
- 只排一天：`fireAt` 設 `<YYYY-MM-DD>T23:55:00` 加本機時區，例如 `+08:00`。
- 每天都排：`cronExpression` 設 `55 23 * * *`。

prompt 照這樣寫：

> 用 claude-weekly-worklog skill 產出 <YYYY-MM-DD>（每天排程則寫「當天」）<起點>–23:55 的本日工作日誌最終版，終點固定 23:55。週用量取執行當下的值。沿用 `~/.claude/worklog/<YYYYMMDD>/summaries.json`，補齊新回合並改寫標為進行中的條目。完成後送出報告。

告訴使用者：排程只在 Claude 桌面 App 開著時執行；App 關著的話，下次開啟時才跑，那時的週用量會晚於期間結束，報告會自動註明。沒有桌面 App 的環境，請使用者自己定期呼叫這個 skill。
