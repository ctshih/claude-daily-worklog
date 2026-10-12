"""把 worklog_stats.py 的統計、摘要檔與週用量組成本日工作日誌 HTML。

用法：python worklog_render.py stats.json summaries.json out.html [usage.json]
- usage.json 省略或讀不到時，改讀環境變數 DAILY_WORKLOG_USAGE_FALLBACK 指向的檔案（同格式）；
  兩者都沒有時，週用量一節顯示「未取得」。
- 版型取自同一個 skill 的 assets/template.html。
- 摘要檔以 stats.json 裡每個 session 的 key 為鍵。任何 session 或回合缺摘要時，照樣寫出 HTML，
  但在 stderr 列出缺漏並以 exit 2 結束。
"""
import json, os, sys, html, platform, datetime as dt

HERE = os.path.dirname(os.path.abspath(__file__))
TEMPLATE = os.path.join(HERE, "..", "assets", "template.html")
MODEL_NAME = {"claude-fable-5-1": "Fable 5.1", "claude-opus-5-5": "Opus 5.5", "claude-opus-5": "Opus 5",
              "claude-sonnet-5-5": "Sonnet 5.5", "claude-sonnet-5": "Sonnet 5",
              "claude-haiku-4-5-20251001": "Haiku 4.5"}
WD = "一二三四五六日"
e = html.escape


def n(x):
    return f"{x:,}"


def mega(x):
    return f"{x/1e6:.2f}M" if x >= 1e6 else (f"{x/1e3:.1f}K" if x >= 1e3 else str(x))


def model(m):
    return MODEL_NAME.get(m, m)


def three(u):
    """三欄：輸入（未命中快取，含快取寫入）／快取輸入／輸出。"""
    return u["input"] + u["cache_write"], u["cache_read"], u["output"]


def add(a, b):
    for k in ("calls", "input", "cache_write", "cache_read", "output"):
        a[k] = a.get(k, 0) + b.get(k, 0)
    return a


def session_models(s):
    agg = {}
    for m, u in s["usage_main"].items():
        add(agg.setdefault(m, {}), u)
    for sub in s["subagents"]:
        for m, u in sub["usage"].items():
            add(agg.setdefault(m, {}), u)
    return agg


def turn_keys(s):
    """回合在摘要檔裡的鍵：HH:MM；同一分鐘第二個以後加 #2、#3。"""
    cnt, out = {}, []
    for t in s["user_turns"]:
        cnt[t["time"]] = cnt.get(t["time"], 0) + 1
        out.append((t, t["time"] if cnt[t["time"]] == 1 else f"{t['time']}#{cnt[t['time']]}"))
    return out


def load_usage(path):
    for p in (path, os.environ.get("DAILY_WORKLOG_USAGE_FALLBACK")):
        if p and os.path.exists(p):
            try:
                return json.load(open(p, encoding="utf-8"))
            except Exception:
                pass
    return None


def usage_table(rows, tz):
    out = []
    for nm, span, us in rows:
        for m, u in us.items():
            a, b, c = three(u)
            out.append(f"<tr><td>{e(nm)}<br><span class=\"note\">{span}</span></td><td>{e(model(m))}</td>"
                       f"<td class=\"num\">{n(u['calls'])}</td><td class=\"num\">{n(a)}<br><span class=\"note\">快取寫入 {n(u['cache_write'])}</span></td>"
                       f"<td class=\"num\">{n(b)}</td><td class=\"num\">{n(c)}</td><td class=\"num\">{n(a+b+c)}</td></tr>\n")
    return "".join(out)


def total_row(label, agg, colspan=1):
    A = sum(three(u)[0] for u in agg.values()); B = sum(three(u)[1] for u in agg.values()); C = sum(three(u)[2] for u in agg.values())
    return (f"<tr class=\"totrow\"><td colspan=\"{colspan}\">{label}</td><td class=\"num\">{n(sum(u['calls'] for u in agg.values()))}</td>"
            f"<td class=\"num\">{n(A)}</td><td class=\"num\">{n(B)}</td><td class=\"num\">{n(C)}</td><td class=\"num\">{n(A+B+C)}</td></tr>\n")


def main():
    if len(sys.argv) < 4:
        sys.exit(__doc__)
    stats = json.load(open(sys.argv[1], encoding="utf-8"))
    summ = json.load(open(sys.argv[2], encoding="utf-8"))
    out = sys.argv[3]
    usage = load_usage(sys.argv[4] if len(sys.argv) > 4 else None)
    start = dt.datetime.fromisoformat(stats["start"])
    end = dt.datetime.fromisoformat(stats["end"])
    tz = start.tzinfo
    day = start.strftime("%Y-%m-%d")
    sessions = stats["sessions"]
    for s in sessions:
        s["span_from"] = s["turn_start"] if s["turn_start"] != start.strftime("%H:%M") else s["from"]
        s["link"] = f"claude://claude.ai/epitaxy/{s['local_id']}" if s.get("local_id") else None

    grand = {}
    for s in sessions:
        for m, u in session_models(s).items():
            add(grand.setdefault(m, {}), u)
    g_tot = sum(sum(three(u)) for u in grand.values())
    g_turns = sum(len(s["user_turns"]) for s in sessions)
    g_utok = sum(t["est_tokens"] for s in sessions for t in s["user_turns"])

    tpl = open(TEMPLATE, encoding="utf-8").read()
    H = [tpl[: tpl.index("</style>")].replace("__標題__", f"本日工作日誌 {day}"), """
.num{text-align:right;font-family:var(--mono);font-size:13px;white-space:nowrap}
.subrow td{color:var(--soft);font-size:13px}
.totrow td{font-weight:700;background:var(--accent-soft)}
.note{font-size:12.5px;color:var(--soft)}
td.req{min-width:220px}
</style>
</head>
<body>
<div class="wrap">
"""]
    H.append(f"<h1>📒 本日工作日誌</h1>\n<p class=\"sub\">{day}（{WD[start.weekday()]}）· 本機 Claude Code · "
             f"{start.strftime('%H:%M')} 至 {end.strftime('%H:%M')}</p>\n")
    u_src = (f"週用量於 {dt.datetime.fromisoformat(usage['fetched_at']).astimezone(tz).strftime('%m-%d %H:%M')} 取得。"
             if usage else "週用量未取得。")
    H.append(f"<div class=\"byline\">由 Claude Code 於 {end.strftime('%H:%M')} 產出。統計取自本機 Claude Code 全部對話紀錄（含子代理）。"
             f"{u_src}要求與交付摘要由 Claude 閱讀對話後撰寫。</div>\n")
    wk = next((w for w in (usage or {}).get("windows", []) if w["key"] == "seven_day"), None)
    H.append("<div class=\"badges\">")
    H.append(f"<span class=\"badge\">{len(sessions)} 個 session</span>")
    H.append(f"<span class=\"badge\">{g_turns} 個使用者回合</span>")
    H.append(f"<span class=\"badge\">總計 {mega(g_tot)} tokens</span>")
    if wk:
        H.append(f"<span class=\"badge g\">本週剩餘 {100-wk['pct']:.0f}%</span>")
    H.append("</div>\n<nav class=\"toc\"><a href=\"#s1\">1 Session 總覽</a><a href=\"#s2\">2 本週剩餘用量</a>"
             "<a href=\"#s3\">3 各 Session 詳細</a><a href=\"#s4\">4 統計方法與限制</a></nav>\n")

    # ---------- 1. 總覽 ----------
    H.append("<h2 id=\"s1\">1. Session 總覽</h2>\n<div class=\"tablewrap\"><table>\n"
             "<tr><th>作業名稱</th><th>工作目錄</th><th>使用者要求概述</th><th>交付內容概述</th>"
             "<th>使用者輸入<br>回合／token（估）</th><th>總使用 token</th></tr>\n")
    for s in sessions:
        sm = summ.get(s["key"], {})
        name = e(s["title"] or s["cli_session_id"][:8])
        name = f"<a href=\"{e(s['link'])}\">{name}</a>" if s["link"] else name
        tot = sum(sum(three(u)) for u in session_models(s).values())
        H.append(f"<tr><td>{name}<br><span class=\"note\">{s['span_from']}–{s['to']}</span></td>"
                 f"<td class=\"mono\">{e(s['cwd'] or '')}</td><td class=\"req\">{e(sm.get('request',''))}</td>"
                 f"<td class=\"req\">{e(sm.get('delivery',''))}</td>"
                 f"<td class=\"num\">{len(s['user_turns'])} 回合<br>約 {n(sum(t['est_tokens'] for t in s['user_turns']))}</td>"
                 f"<td class=\"num\">{n(tot)}</td></tr>\n")
    H.append(f"<tr class=\"totrow\"><td colspan=\"4\">合計</td><td class=\"num\">{g_turns} 回合<br>約 {n(g_utok)}</td>"
             f"<td class=\"num\">{n(g_tot)}</td></tr>\n</table></div>\n")
    H.append("<p class=\"note\">作業名稱若是連結，點了會在 Claude 桌面 App 打開該 session。總使用 token ＝ 輸入＋快取輸入＋輸出，含子代理。</p>\n")

    # 圖 1：各 session token 組成
    y, W = 30, 440
    svg = ["<figure><svg id=\"fig1\" viewBox=\"0 0 700 %d\" xmlns=\"http://www.w3.org/2000/svg\" role=\"img\" aria-label=\"各 session token 組成\">" % (60 + 46 * max(len(sessions), 1)),
           "<style>#fig1 .lbl{fill:var(--text);font:12.5px -apple-system,\"Noto Sans TC\",\"Microsoft JhengHei\",sans-serif}"
           "#fig1 .tick{fill:var(--soft);font:11px -apple-system,\"Noto Sans TC\",sans-serif}"
           "#fig1 .cr{fill:var(--accent);opacity:.35}#fig1 .in{fill:var(--warn)}#fig1 .out{fill:var(--accent)}</style>"]
    for s in sessions:
        a = {"input": 0, "cache_write": 0, "cache_read": 0, "output": 0}
        for u in session_models(s).values():
            add(a, u)
        inp = a["input"] + a["cache_write"]
        tot = inp + a["cache_read"] + a["output"] or 1
        x = 170
        svg.append(f"<text class=\"lbl\" x=\"10\" y=\"{y+15}\">{e((s['title'] or s['cli_session_id'][:8])[:14])}</text>")
        for cls, v in (("cr", a["cache_read"]), ("in", inp), ("out", a["output"])):
            w = W * v / tot
            svg.append(f"<rect class=\"{cls}\" x=\"{x:.1f}\" y=\"{y}\" width=\"{w:.1f}\" height=\"20\"/>")
            x += w
        svg.append(f"<text class=\"tick\" x=\"{170+W+8}\" y=\"{y+15}\">{mega(tot)}</text>")
        svg.append(f"<text class=\"tick\" x=\"170\" y=\"{y+34}\">快取輸入 {a['cache_read']/tot*100:.1f}% · 輸入 {inp/tot*100:.1f}% · 輸出 {a['output']/tot*100:.1f}%</text>")
        y += 46
    ly = y + 6
    svg.append(f"<rect class=\"cr\" x=\"170\" y=\"{ly}\" width=\"12\" height=\"10\"/><text class=\"tick\" x=\"188\" y=\"{ly+9}\">快取輸入</text>"
               f"<rect class=\"in\" x=\"260\" y=\"{ly}\" width=\"12\" height=\"10\"/><text class=\"tick\" x=\"278\" y=\"{ly+9}\">輸入（未快取）</text>"
               f"<rect class=\"out\" x=\"380\" y=\"{ly}\" width=\"12\" height=\"10\"/><text class=\"tick\" x=\"398\" y=\"{ly+9}\">輸出</text>")
    svg.append("</svg><figcaption><b>圖 1</b>：各 session 的 token 組成。每條長條代表該 session 的總用量（右側數字），"
               "長條內依比例分成快取輸入（淺藍）、未快取輸入（橘）、輸出（深藍）。每次 API 呼叫都會重讀整段對話，"
               "所以長時間、多工具呼叫的作業以快取輸入佔絕大多數。</figcaption></figure>\n")
    H.append("\n".join(svg))

    # ---------- 2. 週用量 ----------
    H.append("<h2 id=\"s2\">2. 本週剩餘用量</h2>\n")
    if not usage:
        H.append("<div class=\"card\"><p><b>未取得週用量。</b>這個環境沒有 Claude 桌面 App 的用量工具，"
                 "也沒有設定 DAILY_WORKLOG_USAGE_FALLBACK。</p></div>\n")
    else:
        fetched = dt.datetime.fromisoformat(usage["fetched_at"]).astimezone(tz)
        day_end = start.replace(hour=23, minute=59, second=59)
        if fetched < day_end.replace(minute=50, second=0):
            H.append(f"<div class=\"card\"><p><b>這一天還沒結束，下表是 {fetched.strftime('%H:%M')} 的數值，不是當日結束時的數值。</b>"
                     "當日結束時重新產生日誌，這一節會換成當時的數值。</p></div>\n")
        elif fetched > day_end:
            H.append(f"<div class=\"card\"><p><b>下表是 {fetched.strftime('%m-%d %H:%M')} 的數值，晚於當日結束。</b>"
                     "這段期間的用量會讓剩餘比例比當日結束時低。</p></div>\n")
        H.append("<div class=\"tablewrap\"><table><tr><th>額度</th><th>已用</th><th>剩餘</th><th>重置時間</th></tr>\n")
        for w in usage["windows"]:
            r = dt.datetime.fromisoformat(w["resets_at"].replace("Z", "+00:00")).astimezone(tz)
            H.append(f"<tr><td>{e(w['label'])}</td><td class=\"num\">{w['pct']:.0f}%</td><td class=\"num\">{100-w['pct']:.0f}%</td>"
                     f"<td>{r.strftime('%m-%d（')}{WD[r.weekday()]}）{r.strftime('%H:%M')}</td></tr>\n")
        H.append(f"</table></div>\n<p class=\"note\">方案：{e(usage.get('plan',''))}。</p>\n")
        y = 20
        svg = ["<figure><svg id=\"fig2\" viewBox=\"0 0 700 %d\" xmlns=\"http://www.w3.org/2000/svg\" role=\"img\" aria-label=\"用量額度\">" % (40 + 44 * len(usage["windows"])),
               "<style>#fig2 .lbl{fill:var(--text);font:12.5px -apple-system,\"Noto Sans TC\",\"Microsoft JhengHei\",sans-serif}"
               "#fig2 .tick{fill:var(--soft);font:11px -apple-system,\"Noto Sans TC\",sans-serif}"
               "#fig2 .bg{fill:var(--border)}#fig2 .used{fill:var(--accent)}</style>"]
        for w in usage["windows"]:
            svg.append(f"<text class=\"lbl\" x=\"10\" y=\"{y+15}\">{e(w['label'])}</text>"
                       f"<rect class=\"bg\" x=\"130\" y=\"{y}\" width=\"480\" height=\"20\" rx=\"4\"/>"
                       f"<rect class=\"used\" x=\"130\" y=\"{y}\" width=\"{480*w['pct']/100:.1f}\" height=\"20\" rx=\"4\"/>"
                       f"<text class=\"tick\" x=\"620\" y=\"{y+15}\">剩 {100-w['pct']:.0f}%</text>")
            y += 44
        svg.append("</svg><figcaption><b>圖 2</b>：各額度的使用比例。整條是 100% 額度，深藍是已用的部分，右側是剩餘百分比。"
                   "「本週」是全模型共用的週額度，標有模型名的是該模型另外的週額度，「5 小時」是滾動的短期額度。</figcaption></figure>\n")
        H.append("\n".join(svg))

    # ---------- 3. 詳細 ----------
    H.append("<h2 id=\"s3\">3. 各 Session 詳細</h2>\n")
    for i, s in enumerate(sessions, 1):
        sm = summ.get(s["key"], {})
        title = e(s["title"] or "")
        H.append(f"<h3>3.{i} " + (f"<a href=\"{e(s['link'])}\">{title}</a>" if s["link"] else title) + "</h3>\n")
        link_cell = f"<a href=\"{e(s['link'])}\">在 Claude App 中開啟</a>" if s["link"] else "（非 Claude 桌面 App 的 session，沒有連結）"
        H.append("<div class=\"tablewrap\"><table>"
                 f"<tr><th>工作目錄</th><td class=\"mono\">{e(s['cwd'] or '')}</td></tr>"
                 f"<tr><th>時段</th><td>{s['span_from']}–{s['to']}</td></tr>"
                 f"<tr><th>使用者輸入</th><td>{len(s['user_turns'])} 回合，約 {n(sum(t['est_tokens'] for t in s['user_turns']))} tokens（估算）</td></tr>"
                 f"<tr><th>Session 連結</th><td>{link_cell}</td></tr></table></div>\n")
        H.append("<h4>使用者要求與交付內容</h4>\n<div class=\"tablewrap\"><table><tr><th>時間</th><th>使用者要求（原文）</th><th>輸入 token（估）</th><th>交付內容概述</th></tr>\n")
        for t, key in turn_keys(s):
            txt = t["text"] if len(t["text"]) <= 300 else t["text"][:300] + "…"
            H.append(f"<tr><td>{t['time']}</td><td class=\"req\">{e(txt).replace(chr(10), '<br>')}</td><td class=\"num\">{n(t['est_tokens'])}</td>"
                     f"<td class=\"req\">{e(sm.get('turns', {}).get(key, ''))}</td></tr>\n")
        H.append("</table></div>\n<h4>Token 用量（依來源與模型）</h4>\n<div class=\"tablewrap\"><table>"
                 "<tr><th>來源</th><th>模型</th><th>API 呼叫</th><th>輸入</th><th>快取輸入</th><th>輸出</th><th>合計</th></tr>\n")
        rows = [("主控 session", f"{s['span_from']}–{s['to']}", s["usage_main"])]
        for sub in s["subagents"]:
            nm = sm.get("subagent_names", {}).get(sub["description"], "子代理：" + (sub["description"] or sub["id"]))
            rows.append((nm, f"{sub['from']}–{sub['to']}", sub["usage"]))
        H.append(usage_table(rows, tz))
        for m, u in session_models(s).items():
            a, b, c = three(u)
            H.append(f"<tr class=\"subrow\"><td>小計</td><td>{e(model(m))}</td><td class=\"num\">{n(u['calls'])}</td>"
                     f"<td class=\"num\">{n(a)}</td><td class=\"num\">{n(b)}</td><td class=\"num\">{n(c)}</td><td class=\"num\">{n(a+b+c)}</td></tr>\n")
        H.append(total_row("Session 合計", session_models(s), 2) + "</table></div>\n")

    H.append("<h3>全日合計（依模型）</h3>\n<div class=\"tablewrap\"><table><tr><th>模型</th><th>API 呼叫</th><th>輸入</th><th>快取輸入</th><th>輸出</th><th>合計</th></tr>\n")
    for m, u in grand.items():
        a, b, c = three(u)
        H.append(f"<tr><td>{e(model(m))}</td><td class=\"num\">{n(u['calls'])}</td><td class=\"num\">{n(a)}</td>"
                 f"<td class=\"num\">{n(b)}</td><td class=\"num\">{n(c)}</td><td class=\"num\">{n(a+b+c)}</td></tr>\n")
    H.append(total_row("合計", grand) + "</table></div>\n")

    # ---------- 4. 限制 ----------
    H.append("""<h2 id="s4">4. 統計方法與限制</h2>
<ul>
<li><b>欄位定義。</b>「輸入」是未命中快取的輸入，包含寫入快取的部分，格內小字另列快取寫入量。「快取輸入」是命中快取、直接讀取的部分。三欄相加為合計。</li>
<li><b>使用者輸入 token 是估算值。</b>以中日韓字元每字 1 token、其他字元每 4 字 1 token 估算，只算使用者親自打的字，不含系統附加內容。</li>
<li><b>只涵蓋本機 Claude Code。</b>claude.ai 網頁版、手機 App、其他電腦與其他工具的對話不在內。子代理的交件訊息不算使用者回合。</li>
<li><b>起點前開始的回合整個計入。</b>若某回合在起點前下達、起點後仍在執行，該回合的全部用量都算進來。</li>
<li><b>同一 API 回應去重。</b>對話紀錄會把一次回應拆成多筆串流紀錄，統計時依回應 ID 只取最後一筆。</li>
<li><b>產出本檔的回合仍在進行中。</b>產生日誌的 session 最後一回合，token 只計到統計當下。</li>
<li><b>週用量是帳號層級。</b>它包含本機以外的用量，不能直接和上面的 token 數對應。</li>
</ul>
""")
    H.append(f"<div class=\"foot\">本報告：<span class=\"mono\">{e(os.path.abspath(out))}</span><br>"
             "產生方式：<span class=\"mono\">daily-worklog</span> skill<br>"
             f"報告生成：{end.strftime('%Y-%m-%d %H:%M')} · {e(platform.system())} · Claude Code</div>\n</div>\n</body>\n</html>\n")
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    open(out, "w", encoding="utf-8").write("".join(H))

    missing = []
    for s in sessions:
        sm = summ.get(s["key"], {})
        for f in ("request", "delivery"):
            if not sm.get(f):
                missing.append(f"{s['key']}  {f}")
        for t, key in turn_keys(s):
            if not sm.get("turns", {}).get(key):
                missing.append(f"{s['key']}  turns[{key}]  {t['text'][:40]}")
    if missing:
        sys.stderr.write("摘要缺漏：\n" + "\n".join(missing) + "\n")
        sys.exit(2)
    print(f"OK：{len(sessions)} 個 session、{g_turns} 個回合，摘要齊全")


if __name__ == "__main__":
    main()
