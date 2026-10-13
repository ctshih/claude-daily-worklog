"""把 worklog_stats.py 的統計、摘要檔與週用量組成工作週報或本日工作日誌 HTML。

用法：python worklog_render.py stats.json summaries.json out.html [usage.json]
- 期間超過一天時產出週報（7 天）或期間工作日誌，另加逐日用量圖；單日產出本日工作日誌。
- usage.json 省略或讀不到時，改讀環境變數 WORKLOG_USAGE_FALLBACK 指向的檔案（同格式）；
  兩者都沒有時，週用量一節顯示「未取得」。
- 版型取自同一個 skill 的 assets/template.html；時區跟隨 stats.json 的起點。
- 摘要檔以 stats.json 裡每個 session 的 key 為鍵。任何 session 或回合缺摘要時，照樣寫出 HTML，
  但在 stderr 列出缺漏並以 exit 2 結束。
"""
import json, os, re, sys, html, platform, datetime as dt

HERE = os.path.dirname(os.path.abspath(__file__))
TEMPLATE = os.path.join(HERE, "..", "assets", "template.html")
TZ = None  # 由 main() 依 stats.json 設定


def load_usage(path):
    for p in (path, os.environ.get("WORKLOG_USAGE_FALLBACK") or os.environ.get("DAILY_WORKLOG_USAGE_FALLBACK")):
        if p and os.path.exists(p):
            try:
                return json.load(open(p, encoding="utf-8"))
            except Exception:
                pass
    return None


def parse_t(v):
    return dt.datetime.fromisoformat(v.replace("Z", "+00:00"))
MODEL_NAME = {"claude-opus-5-5": "Opus 5.5", "claude-opus-5": "Opus 5", "claude-fable-5-1": "Fable 5.1",
              "claude-sonnet-5-5": "Sonnet 5.5", "claude-sonnet-5": "Sonnet 5", "claude-haiku-4-5-20251001": "Haiku 4.5",
              "claude-opus-4-7": "Opus 4.7", "claude-opus-4-6": "Opus 4.6", "claude-sonnet-4-6": "Sonnet 4.6"}
e = html.escape


def n(x):
    return f"{x:,}"


def mega(x):
    return f"{x/1e6:.2f}M" if x >= 1e6 else (f"{x/1e3:.1f}K" if x >= 1e3 else str(x))


def three(u):
    """使用者要求的三欄：輸入（未快取，含快取寫入）／快取輸入／輸出。"""
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


def total(u):
    return sum(three(u))


def head_css():
    t = open(TEMPLATE, encoding="utf-8").read()
    return t[: t.index("</style>")]


def daily_chart(sessions, start, end):
    """逐日 token 堆疊長條：用量前五大的 session 各一色，其餘併成「其他」。"""
    days = [(start + dt.timedelta(days=i)).strftime("%m-%d") for i in range((end.date() - start.date()).days + 1)]
    tot = {s["key"]: sum(s.get("usage_by_day", {}).values()) for s in sessions}
    top = sorted(sessions, key=lambda s: -tot[s["key"]])[:5]
    groups = [(s["title"] or s["cli_session_id"][:8], [s]) for s in top]
    rest = [s for s in sessions if s not in top]
    if rest:
        groups.append((f"其他 {len(rest)} 個", rest))
    per = [[sum(s.get("usage_by_day", {}).get(d, 0) for s in g) for d in days] for _, g in groups]
    day_tot = [sum(p[i] for p in per) for i in range(len(days))]
    vmax = max(day_tot) or 1
    X0, X1, Y0, Y1 = 70, 680, 30, 250
    bw = (X1 - X0) / len(days) * 0.6
    css = ["#fig3 .axis{stroke:var(--soft);stroke-width:1}#fig3 .grid{stroke:var(--border);stroke-width:1}",
           "#fig3 .lbl{fill:var(--text);font:12px -apple-system,\"Noto Sans TC\",\"Microsoft JhengHei\",sans-serif}",
           "#fig3 .tick{fill:var(--soft);font:11px -apple-system,\"Noto Sans TC\",sans-serif}"]
    fills = ["var(--accent)", "var(--warn)", "var(--ok)", "var(--err)", "var(--text)", "var(--soft)"]
    ops = [1, 1, 1, 1, .55, .45]
    for i in range(len(groups)):
        css.append(f"#fig3 .g{i}{{fill:{fills[i]};opacity:{ops[i]}}}")
    out = [f"<figure><svg id=\"fig3\" viewBox=\"0 0 700 {320 + 22 * ((len(groups) + 2) // 3)}\" xmlns=\"http://www.w3.org/2000/svg\" role=\"img\" aria-label=\"逐日 token 用量\">",
           "<style>" + "".join(css) + "</style>"]
    for k in range(5):
        y = Y1 - (Y1 - Y0) * k / 4
        out.append(f"<line class=\"grid\" x1=\"{X0}\" y1=\"{y:.1f}\" x2=\"{X1}\" y2=\"{y:.1f}\"/>"
                   f"<text class=\"tick\" x=\"{X0-6}\" y=\"{y+4:.1f}\" text-anchor=\"end\">{mega(int(vmax*k/4))}</text>")
    for i, d in enumerate(days):
        cx = X0 + (X1 - X0) * (i + .5) / len(days)
        y = Y1
        for gi, p in enumerate(per):
            h = (Y1 - Y0) * p[i] / vmax
            if h > 0:
                out.append(f"<rect class=\"g{gi}\" x=\"{cx-bw/2:.1f}\" y=\"{y-h:.1f}\" width=\"{bw:.1f}\" height=\"{h:.1f}\"/>")
            y -= h
        out.append(f"<text class=\"tick\" x=\"{cx:.1f}\" y=\"{y-5:.1f}\" text-anchor=\"middle\">{mega(day_tot[i])}</text>"
                   f"<text class=\"tick\" x=\"{cx:.1f}\" y=\"{Y1+16}\" text-anchor=\"middle\">{d}（{'一二三四五六日'[(start + dt.timedelta(days=i)).weekday()]}）</text>")
    out.append(f"<line class=\"axis\" x1=\"{X0}\" y1=\"{Y1}\" x2=\"{X1}\" y2=\"{Y1}\"/>")
    for gi, (name, _) in enumerate(groups):
        lx, ly = X0 + (gi % 3) * 205, 300 + 22 * (gi // 3)
        out.append(f"<rect class=\"g{gi}\" x=\"{lx}\" y=\"{ly-10}\" width=\"12\" height=\"12\"/>"
                   f"<text class=\"lbl\" x=\"{lx+18}\" y=\"{ly}\">{e(name[:14])}</text>")
    out.append("</svg><figcaption><b>圖 2</b>：逐日 token 用量。每根長條是一天的總用量（上方數字），依 session 堆疊；"
               "用量前五大的 session 各一色，其餘併成「其他」。可以看出哪幾天、哪些作業吃掉最多用量。</figcaption></figure>\n")
    return "\n".join(out)


def main():
    global TZ
    if len(sys.argv) < 4:
        sys.exit(__doc__)
    stats = json.load(open(sys.argv[1], encoding="utf-8"))
    summ = json.load(open(sys.argv[2], encoding="utf-8"))
    out = sys.argv[3]
    usage = load_usage(sys.argv[4] if len(sys.argv) > 4 else None)
    start = dt.datetime.fromisoformat(stats["start"])
    end = dt.datetime.fromisoformat(stats["end"])
    TZ = start.tzinfo
    day = start.strftime("%Y-%m-%d")
    wd = "一二三四五六日"[start.weekday()]
    multi = stats.get("multi_day", False)
    n_days = (end.date() - start.date()).days + 1
    doc = ("工作週報" if n_days == 7 else "期間工作日誌") if multi else "本日工作日誌"
    period = "期間" if multi else "當日"
    now = dt.datetime.now(TZ)
    if multi:
        range_txt = (f"{day}（{wd}）至 {end.strftime('%Y-%m-%d')}（{'一二三四五六日'[end.weekday()]}）· 本機 Claude Code · 共 {n_days} 天")
    else:
        range_txt = f"{day}（{wd}）· 本機 Claude Code · {start.strftime('%H:%M')} 至 {end.strftime('%H:%M')}"
    start_lbl = start.strftime("%m-%d %H:%M" if multi else "%H:%M")
    sessions = stats["sessions"]
    for s_ in sessions:
        s_["span_from"] = s_["turn_start"] if s_["turn_start"] != start_lbl else s_["from"]
        s_.setdefault("key", s_["local_id"])
        s_["link"] = f"claude://claude.ai/epitaxy/{s_['local_id']}" if s_.get("local_id") else None
        s_["mode_note"] = "Cowork 模式" if s_.get("mode") == "cowork" else ""
    sessions.sort(key=lambda s_: s_["span_from"])

    grand = {}
    for s in sessions:
        for m, u in session_models(s).items():
            add(grand.setdefault(m, {}), u)
    g_tot = sum(total(u) for u in grand.values())
    g_turns = sum(len(s["user_turns"]) for s in sessions)
    g_utok = sum(t["est_tokens"] for s in sessions for t in s["user_turns"])

    H = [head_css().replace("__標題__", f"{doc} {day}" + (f"–{end.strftime('%m-%d')}" if multi else "")), """
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
    H.append(f"<h1>📒 {doc}</h1>\n<p class=\"sub\">{range_txt}</p>\n")
    H.append(f"<div class=\"byline\">由 Claude Code 於 {now.strftime('%m-%d %H:%M')} 產出。統計取自本機 Claude Code 全部對話紀錄（含子代理）與 Cowork 模式的稽核紀錄，"
             + (f"週用量於 {parse_t(usage['fetched_at']).astimezone(TZ).strftime('%m-%d %H:%M')} 取得。" if usage else "週用量未取得。") +
             "要求與交付摘要由 Claude 閱讀對話後撰寫。</div>\n")
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
        name_html = e(s['title'] or s['cli_session_id'][:8])
        name_html = f"<a href=\"{e(s['link'])}\">{name_html}</a>" if s["link"] else name_html
        if s["mode_note"]:
            name_html += f" <span class=\"badge\">{s['mode_note']}</span>"
        ut = sum(t["est_tokens"] for t in s["user_turns"])
        tot = sum(total(u) for u in session_models(s).values())
        H.append(f"<tr><td>{name_html}<br>"
                 f"<span class=\"note\">{s['span_from']}–{s['to']}</span></td>"
                 f"<td class=\"mono\">{e(s['cwd'] or '')}</td><td class=\"req\">{e(sm.get('request',''))}</td>"
                 f"<td class=\"req\">{e(sm.get('delivery',''))}</td>"
                 f"<td class=\"num\">{len(s['user_turns'])} 回合<br>約 {n(ut)}</td><td class=\"num\">{n(tot)}</td></tr>\n")
    H.append(f"<tr class=\"totrow\"><td colspan=\"4\">合計</td><td class=\"num\">{g_turns} 回合<br>約 {n(g_utok)}</td>"
             f"<td class=\"num\">{n(g_tot)}</td></tr>\n</table></div>\n")
    H.append("<p class=\"note\">作業名稱若是連結，點了會在 Claude 桌面 App 打開該 session。總使用 token ＝ 輸入＋快取輸入＋輸出，含子代理。</p>\n")

    # 圖 1：各 session token 組成（百分比堆疊）
    rows = []
    for s in sessions:
        agg = {"input": 0, "cache_write": 0, "cache_read": 0, "output": 0}
        for u in session_models(s).values():
            add(agg, u)
        rows.append((s["title"] or s["cli_session_id"][:8], agg))
    y = 30
    svg = ["<figure><svg id=\"fig1\" viewBox=\"0 0 700 %d\" xmlns=\"http://www.w3.org/2000/svg\" role=\"img\" aria-label=\"各 session token 組成\">" % (60 + 46 * len(rows)),
           "<style>#fig1 .lbl{fill:var(--text);font:12.5px -apple-system,\"Noto Sans TC\",\"Microsoft JhengHei\",sans-serif}"
           "#fig1 .tick{fill:var(--soft);font:11px -apple-system,\"Noto Sans TC\",sans-serif}"
           "#fig1 .cr{fill:var(--accent);opacity:.35}#fig1 .in{fill:var(--warn)}#fig1 .out{fill:var(--accent)}</style>"]
    W = 440
    for name, a in rows:
        inp = a["input"] + a["cache_write"]
        tot = inp + a["cache_read"] + a["output"]
        x = 170
        svg.append(f"<text class=\"lbl\" x=\"10\" y=\"{y+15}\">{e(name)}</text>")
        for cls, v in (("cr", a["cache_read"]), ("in", inp), ("out", a["output"])):
            w = W * v / tot if tot else 0
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
               "長條內依比例分成快取輸入（淺藍）、未快取輸入（橘）、輸出（深藍）。長時間、多工具呼叫的作業，每次呼叫都會重讀整段對話，"
               "所以快取輸入佔絕大多數；真正新產生的輸出只佔一小部分。</figcaption></figure>\n")
    H.append("\n".join(svg))
    if multi:
        H.append(daily_chart(sessions, start, end))

    # ---------- 2. 週用量 ----------
    H.append("<h2 id=\"s2\">2. 本週剩餘用量</h2>\n")
    if not usage:
        H.append("<div class=\"card\"><p><b>未取得週用量。</b>這個環境沒有 Claude 桌面 App 的用量工具，"
                 "也沒有設定 WORKLOG_USAGE_FALLBACK。</p></div>\n")
    else:
        fetched = parse_t(usage["fetched_at"]).astimezone(TZ)
        day_end = end.replace(hour=23, minute=59, second=59)
        if fetched < day_end.replace(minute=50, second=0):
            H.append(f"<div class=\"card\"><p><b>{period}還沒結束，下表是 {fetched.strftime('%m-%d %H:%M')} 的數值，不是{period}結束時的數值。</b>"
                     f"{period}結束時重新產生報告，這一節會換成當時的數值。</p></div>\n")
        elif fetched > day_end:
            H.append(f"<div class=\"card\"><p><b>下表是 {fetched.strftime('%m-%d %H:%M')} 的數值，晚於{period}結束（{day_end.strftime('%m-%d %H:%M')}）。</b>"
                     f"這段時間的用量會讓剩餘比例比{period}結束時低。</p></div>\n")
        H.append("<div class=\"tablewrap\"><table><tr><th>額度</th><th>已用</th><th>剩餘</th><th>重置時間</th></tr>\n")
        for w in usage["windows"]:
            r = parse_t(w["resets_at"]).astimezone(TZ)
            H.append(f"<tr><td>{e(w['label'])}</td><td class=\"num\">{w['pct']:.0f}%</td><td class=\"num\">{100-w['pct']:.0f}%</td>"
                     f"<td>{r.strftime('%m-%d（')}{'一二三四五六日'[r.weekday()]}）{r.strftime('%H:%M')}</td></tr>\n")
        H.append(f"</table></div>\n<p class=\"note\">方案：{e(usage.get('plan',''))}。</p>\n")
        svg = ["<figure><svg id=\"fig2\" viewBox=\"0 0 700 %d\" xmlns=\"http://www.w3.org/2000/svg\" role=\"img\" aria-label=\"用量額度\">" % (40 + 44 * len(usage["windows"])),
               "<style>#fig2 .lbl{fill:var(--text);font:12.5px -apple-system,\"Noto Sans TC\",\"Microsoft JhengHei\",sans-serif}"
               "#fig2 .tick{fill:var(--soft);font:11px -apple-system,\"Noto Sans TC\",sans-serif}"
               "#fig2 .bg{fill:var(--border)}#fig2 .used{fill:var(--accent)}</style>"]
        y = 20
        for w in usage["windows"]:
            svg.append(f"<text class=\"lbl\" x=\"10\" y=\"{y+15}\">{e(w['label'])}</text>"
                       f"<rect class=\"bg\" x=\"130\" y=\"{y}\" width=\"480\" height=\"20\" rx=\"4\"/>"
                       f"<rect class=\"used\" x=\"130\" y=\"{y}\" width=\"{480*w['pct']/100:.1f}\" height=\"20\" rx=\"4\"/>"
                       f"<text class=\"tick\" x=\"620\" y=\"{y+15}\">剩 {100-w['pct']:.0f}%</text>")
            y += 44
        svg.append(f"</svg><figcaption><b>圖 {3 if multi else 2}</b>：各額度的使用比例。整條是 100% 額度，深藍是已用的部分，右側是剩餘百分比。"
                   "「本週」是全模型共用的週額度，標有模型名的是該模型另外的週額度，「5 小時」是滾動的短期額度。</figcaption></figure>\n")
        H.append("\n".join(svg))

    # ---------- 3. 詳細 ----------
    H.append("<h2 id=\"s3\">3. 各 Session 詳細</h2>\n")
    for i, s in enumerate(sessions, 1):
        sm = summ.get(s["key"], {})
        t_html = e(s['title'] or '')
        t_html = f"<a href=\"{e(s['link'])}\">{t_html}</a>" if s["link"] else t_html
        if s["mode_note"]:
            t_html += f" <span class=\"badge\">{s['mode_note']}</span>"
        H.append(f"<h3>3.{i} {t_html}</h3>\n")
        link_cell = (f"<a href=\"{e(s['link'])}\">在 Claude App 中開啟</a>" if s["link"] else
                     "（Cowork 模式的 session，請在桌面 App 的 Cowork 分頁找）" if s["mode_note"] else "（沒有連結）")
        H.append("<div class=\"tablewrap\"><table>"
                 f"<tr><th>工作目錄</th><td class=\"mono\">{e(s['cwd'] or '')}</td></tr>"
                 f"<tr><th>時段</th><td>{s['span_from']}–{s['to']}</td></tr>"
                 f"<tr><th>使用者輸入</th><td>{len(s['user_turns'])} 回合，約 {n(sum(t['est_tokens'] for t in s['user_turns']))} tokens（估算）</td></tr>"
                 f"<tr><th>Session 連結</th><td>{link_cell}</td></tr>"
                 "</table></div>\n")
        H.append("<h4>使用者要求與交付內容</h4>\n<div class=\"tablewrap\"><table><tr><th>時間</th><th>使用者要求（原文）</th><th>輸入 token（估）</th><th>交付內容概述</th></tr>\n")
        cnt = {}
        for t in s["user_turns"]:
            cnt[t["time"]] = cnt.get(t["time"], 0) + 1
            key = t["time"] if cnt[t["time"]] == 1 else f"{t['time']}#{cnt[t['time']]}"
            txt = t["text"] if len(t["text"]) <= 300 else t["text"][:300] + "…"
            H.append(f"<tr><td>{t['time']}</td><td class=\"req\">{e(txt).replace(chr(10), '<br>')}</td><td class=\"num\">{n(t['est_tokens'])}</td>"
                     f"<td class=\"req\">{e(sm.get('turns', {}).get(key, ''))}</td></tr>\n")
        H.append("</table></div>\n")
        H.append("<h4>Token 用量（依來源與模型）</h4>\n<div class=\"tablewrap\"><table>"
                 "<tr><th>來源</th><th>模型</th><th>API 呼叫</th><th>輸入</th><th>快取輸入</th><th>輸出</th><th>合計</th></tr>\n")
        srcs = [("主控 session", f"{s['span_from']}–{s['to']}", s["usage_main"])]
        for sub in s["subagents"]:
            nm = sm.get("subagent_names", {}).get(sub["description"], "子代理：" + (sub["description"] or sub["id"]))
            srcs.append((nm, f"{sub['from']}–{sub['to']}", sub["usage"]))
        for nm, span, us in srcs:
            for m, u in us.items():
                a, b, c = three(u)
                H.append(f"<tr><td>{e(nm)}<br><span class=\"note\">{span}</span></td><td>{e(MODEL_NAME.get(m, m))}</td>"
                         f"<td class=\"num\">{n(u['calls'])}</td><td class=\"num\">{n(a)}<br><span class=\"note\">快取寫入 {n(u['cache_write'])}</span></td>"
                         f"<td class=\"num\">{n(b)}</td><td class=\"num\">{n(c)}</td><td class=\"num\">{n(a+b+c)}</td></tr>\n")
        for m, u in session_models(s).items():
            a, b, c = three(u)
            H.append(f"<tr class=\"subrow\"><td>小計</td><td>{e(MODEL_NAME.get(m, m))}</td><td class=\"num\">{n(u['calls'])}</td>"
                     f"<td class=\"num\">{n(a)}</td><td class=\"num\">{n(b)}</td><td class=\"num\">{n(c)}</td><td class=\"num\">{n(a+b+c)}</td></tr>\n")
        st = session_models(s)
        A = sum(three(u)[0] for u in st.values()); B = sum(three(u)[1] for u in st.values()); C = sum(three(u)[2] for u in st.values())
        H.append(f"<tr class=\"totrow\"><td colspan=\"2\">Session 合計</td><td class=\"num\">{n(sum(u['calls'] for u in st.values()))}</td>"
                 f"<td class=\"num\">{n(A)}</td><td class=\"num\">{n(B)}</td><td class=\"num\">{n(C)}</td><td class=\"num\">{n(A+B+C)}</td></tr>\n</table></div>\n")

    # 全日依模型
    H.append(f"<h3>{'全期' if multi else '全日'}合計（依模型）</h3>\n<div class=\"tablewrap\"><table><tr><th>模型</th><th>API 呼叫</th><th>輸入</th><th>快取輸入</th><th>輸出</th><th>合計</th></tr>\n")
    for m, u in grand.items():
        a, b, c = three(u)
        H.append(f"<tr><td>{e(MODEL_NAME.get(m, m))}</td><td class=\"num\">{n(u['calls'])}</td><td class=\"num\">{n(a)}</td>"
                 f"<td class=\"num\">{n(b)}</td><td class=\"num\">{n(c)}</td><td class=\"num\">{n(a+b+c)}</td></tr>\n")
    A = sum(three(u)[0] for u in grand.values()); B = sum(three(u)[1] for u in grand.values()); C = sum(three(u)[2] for u in grand.values())
    H.append(f"<tr class=\"totrow\"><td>合計</td><td class=\"num\">{n(sum(u['calls'] for u in grand.values()))}</td><td class=\"num\">{n(A)}</td>"
             f"<td class=\"num\">{n(B)}</td><td class=\"num\">{n(C)}</td><td class=\"num\">{n(A+B+C)}</td></tr>\n</table></div>\n")

    # ---------- 4. 限制 ----------
    H.append("""<h2 id="s4">4. 統計方法與限制</h2>
<ul>
<li><b>欄位定義。</b>「輸入」是未命中快取的輸入，包含寫入快取的部分，格內小字另列快取寫入量。「快取輸入」是命中快取、直接讀取的部分。三欄相加為合計。</li>
<li><b>使用者輸入 token 是估算值。</b>以中日韓字元每字 1 token、其他字元每 4 字 1 token 估算，只算使用者親自打的字，不含系統附加內容。</li>
<li><b>涵蓋本機 Claude Code 與桌面 App 的 Cowork 模式。</b>Cowork 模式取自它的稽核紀錄，標有「Cowork 模式」。claude.ai 網頁版、手機 App、其他電腦與其他工具的對話不在內。子代理交件訊息不算使用者回合。</li>
<li><b>起點前開始的回合整個計入。</b>若某回合在起點前下達、起點後仍在執行，該回合的全部用量都算進來；排程任務若在起點前就結束則不列入。</li>
<li><b>同一 API 回應去重。</b>對話紀錄會把一次回應拆成多筆串流紀錄，統計時依回應 ID 只取最後一筆。</li>
<li><b>產出本檔的回合仍在進行中。</b>本 session 最後一回合的 token 只計到統計當下，之後產生本檔的用量不在內。</li>
<li><b>週用量是帳號層級。</b>它包含本機以外的用量，不能直接和上面的 token 數對應。</li>
</ul>
""")
    H.append(f"<div class=\"foot\">本報告：<span class=\"mono\">{e(os.path.abspath(out))}</span><br>"
             "產生方式：<span class=\"mono\">claude-weekly-worklog</span> skill<br>"
             f"報告生成：{now.strftime('%Y-%m-%d %H:%M')} · {e(platform.system())} · Claude Code</div>\n</div>\n</body>\n</html>\n")
    open(out, "w", encoding="utf-8").write("".join(H))
    missing = []
    for s in sessions:
        sm = summ.get(s["key"], {})
        for f in ("request", "delivery"):
            if not sm.get(f):
                missing.append(f"{s['key']}  {f}")
        cnt = {}
        for t in s["user_turns"]:
            cnt[t["time"]] = cnt.get(t["time"], 0) + 1
            key = t["time"] if cnt[t["time"]] == 1 else f"{t['time']}#{cnt[t['time']]}"
            if not sm.get("turns", {}).get(key):
                missing.append(f"{s['key']}  turns[{key}]  {t['text'][:40]}")
    if missing:
        sys.stderr.write("摘要缺漏：\n" + "\n".join(missing) + "\n")
        sys.exit(2)
    print(f"OK：{len(sessions)} 個 session、{sum(len(s['user_turns']) for s in sessions)} 個回合，摘要齊全")


if __name__ == "__main__":
    main()
