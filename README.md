# claude-weekly-worklog：Claude Code 工作週報

一個 Claude Code skill。它整理一段期間（預設過去一週）在本機 Claude Code 上的所有 session，產出一份單檔 HTML 工作週報；也能只做某一天的工作日誌。

報告內容：

1. **Session 總覽**：每個 session 一列，包括作業名稱、工作目錄、要求概述、交付概述、使用者輸入回合數與 token 數，以及總 token 數。有 Claude 桌面 App 時，作業名稱連到該 session。
2. **逐日用量圖**（週報才有）：每天用了多少 token，依 session 堆疊。
3. **本週剩餘用量**：5 小時、本週、各模型的週額度，各用了多少、何時重置。
4. **各 Session 詳細**：每個使用者回合的原文與對應的交付內容；token 依主控、子代理、workflow 與模型分列，分成輸入、快取輸入、輸出三欄。

數字與版面由程式從對話紀錄算出；要求與交付的文字摘要由 Claude 讀過對話後撰寫。回合多時，Claude 會把摘要分給子代理平行撰寫，合併前再抽查。

## 需求

| 項目 | 說明 |
|---|---|
| Claude Code | 必要。報告讀的是本機的 Claude Code 對話紀錄。 |
| Python 3.9 以上 | 必要。只用標準函式庫，不需要安裝套件。 |
| Claude 桌面 App | 選用。有它才有 session 連結、週用量、Cowork 模式的紀錄、在 App 內直接顯示報告與排程功能。只用終端機 CLI 也能產出報告，但少了這幾項。 |

Windows、macOS、Linux 都可以用。

## 安裝

把 `claude-weekly-worklog` 資料夾放進 Claude Code 的 skill 資料夾：

```bash
git clone https://github.com/ctshih/claude-weekly-worklog.git
cp -r claude-weekly-worklog/claude-weekly-worklog ~/.claude/skills/
```

Windows PowerShell：

```powershell
git clone https://github.com/ctshih/claude-weekly-worklog.git
Copy-Item -Recurse claude-weekly-worklog\claude-weekly-worklog $HOME\.claude\skills\
```

重新開啟 Claude Code，skill 清單裡出現 `claude-weekly-worklog` 就完成了。

想隨 repo 更新，可以改用符號連結，之後 `git pull` 就會生效。

## 使用

在 Claude Code 輸入：

```
/claude-weekly-worklog
```

也可以直接說「幫我做這週的工作週報」。常見用法：

| 說法 | 結果 |
|---|---|
| `/claude-weekly-worklog` | 到昨天為止的 7 天 |
| 「這週到現在」「含今天」 | 往前 7 天，含今天，算到現在 |
| 「過去一週到 10/20」 | 10/14–10/20 |
| 「今天的工作日誌」 | 今天 00:00 到現在 |
| 「2026-10-11 的日誌」 | 補產過去某一天 |
| 「每週一自動產出週報」 | 建立每週排程，需要桌面 App |

同一段期間可以重跑多次。已寫好的摘要會沿用，只補新的回合；期間內各天的單日摘要也會自動沿用。

## 設定

都用環境變數，沒設定時用預設值。

| 變數 | 用途 | 預設 |
|---|---|---|
| `WORKLOG_DIR` | 報告輸出資料夾 | `~/claude-worklog/` |
| `WORKLOG_TZ` | 時區，例如 `+08:00` | 本機時區 |
| `WORKLOG_USAGE_FALLBACK` | 取不到即時週用量時改讀的檔案，格式同 `usage_json.py` 的輸出 | 無 |
| `CLAUDE_CONFIG_DIR` | Claude Code 設定資料夾 | `~/.claude` |

舊版的 `DAILY_WORKLOG_*` 變數名仍然有效。中間資料放在 `~/.claude/worklog/` 底下，每段期間一個資料夾。

## 隱私

報告會**逐字列出你在期間內輸入的每一則要求**，也會寫出工作目錄路徑。分享報告之前請先看過內容。

session 連結只會叫醒本機的 Claude 桌面 App，別人拿到報告也打不開你的 session。

這個 repo 本身只有程式與說明，不含任何對話資料。

## 檔案

```
claude-weekly-worklog/
├── SKILL.md                # Claude 執行的步驟
├── assets/
│   ├── template.html       # 報告版型（深淺色自適應）
│   └── period-brief.md     # 分工寫摘要時給子代理的交辦範本
└── scripts/
    ├── worklog_stats.py    # 掃描對話紀錄，算回合與 token（含 Cowork 模式）
    ├── worklog_plan.py     # 沿用單日摘要，列出待寫的回合
    ├── dump_turns.py       # 唯讀讀取某段時間的對話
    ├── worklog_render.py   # 組成 HTML，並檢查摘要有無缺漏
    ├── usage_json.py       # 轉換桌面 App 的週用量
    └── selfcheck.py        # 檢查報告是否單檔自足、章節齊全
```

統計口徑寫在 `worklog_stats.py` 開頭的說明裡。

## 已知限制

- 使用者輸入的 token 數是估算值，以中日韓字元每字 1 token、其他字元每 4 字 1 token 計算。
- 只算本機 Claude Code 與桌面 App 的 Cowork 模式。claude.ai 網頁版、手機 App、其他電腦的對話不在內。
- 週用量是帳號層級，包含本機以外的用量，不能直接和報告裡的 token 數對應；帳號週額度的重置時間也不一定和報告期間對齊。
- 對話紀錄的格式由 Claude Code 決定，改版後統計程式可能需要調整。

## 授權

MIT License，見 [LICENSE](LICENSE)。
