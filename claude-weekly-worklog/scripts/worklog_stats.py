"""本日工作日誌統計：掃描本機 Claude Code 對話紀錄，輸出各 session 的回合與 token 用量（JSON）。

用法：python worklog_stats.py <YYYY-MM-DD> <HH:MM> [--end HH:MM] [--to YYYY-MM-DD] > stats.json
- --to 給定時統計跨日期間（週報），終點是該日的 --end，預設 23:59；時間欄位改成「MM-DD HH:MM」，
  每個 session 另附 usage_by_day（日期 → token 數）。
- 時區用本機時區；要指定時設環境變數 WORKLOG_TZ，例如 +08:00。
- 對話紀錄位置：$CLAUDE_CONFIG_DIR/projects，未設定時為 ~/.claude/projects。
- 起點時刻正在進行的回合（起點前 6 小時內下達、起點後仍在執行）整個計入。
- 計為使用者回合：親自輸入的訊息、工作中途插入的訊息、斜線指令（還原成「/指令 參數」）。
  不計：本機指令（/model 等）、子代理與背景任務的完成通知、對話壓縮摘要、skill 載入內容、工具結果。
- 子代理（<session>/subagents/*.jsonl）的用量併入母 session，另列明細；
  workflow 的 agent（<session>/subagents/workflows/<runId>/*.jsonl）依 workflow 彙總。
- 同一個 API 回應會以多筆串流紀錄寫入，依 message.id 去重，取最後一筆的 usage。
- 使用者輸入 token 數為估算：中日韓字元每字 1 token，其餘字元每 4 字 1 token。
- 另外讀 Claude 桌面 App Cowork 模式的 session（local-agent-mode-sessions/*/*/local_*/audit.jsonl），mode 標為 cowork。
- 每個 session 輸出 key：有 Claude 桌面 App 的 session ID（local_...）就用它，否則用對話檔 ID。
"""
import json, os, glob, re, sys, platform, datetime as dt


def local_tz():
    v = os.environ.get("WORKLOG_TZ") or os.environ.get("DAILY_WORKLOG_TZ")  # 舊名仍可用
    if v:
        sign = -1 if v.startswith("-") else 1
        hh, mm = v.lstrip("+-").split(":")
        return dt.timezone(sign * dt.timedelta(hours=int(hh), minutes=int(mm)))
    return dt.datetime.now().astimezone().tzinfo


TZ = local_tz()
CONFIG = os.environ.get("CLAUDE_CONFIG_DIR") or os.path.expanduser("~/.claude")
PROJ = os.path.join(CONFIG, "projects")


def app_dir():
    """Claude 桌面 App 的 session 設定檔位置；沒有安裝桌面 App 時找不到，連結欄會留空。"""
    sysname = platform.system()
    if sysname == "Windows":
        base = os.environ.get("APPDATA", "")
    elif sysname == "Darwin":
        base = os.path.expanduser("~/Library/Application Support")
    else:
        base = os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")
    return os.path.join(base, "Claude", "claude-code-sessions")


LOCAL_COMMANDS = {"/model", "/clear", "/config", "/permissions", "/fast", "/effort", "/status", "/cost", "/usage",
                  "/help", "/resume", "/login", "/logout", "/mcp", "/memory", "/hooks", "/doctor", "/theme",
                  "/vim", "/exit", "/rename", "/output-style", "/agents", "/plugin", "/workflows", "/tasks"}
CJK = re.compile(r"[　-〿぀-ヿ㐀-鿿가-힯豈-﫿＀-￯]")


def est_tokens(s):
    n_cjk = len(CJK.findall(s))
    return n_cjk + round((len(s) - n_cjk) / 4)


def ts(o):
    t = o.get("timestamp")
    return dt.datetime.fromisoformat(t.replace("Z", "+00:00")) if t else None


MULTI_DAY = False


def hm(t):
    return t.astimezone(TZ).strftime("%m-%d %H:%M" if MULTI_DAY else "%H:%M")


def tokens_by_day(entries, start, end):
    """依回應 ID 去重後，把每次回應的 token 總數歸到它的日期（MM-DD）。"""
    last = {}
    for o in entries:
        t = ts(o)
        if o.get("type") != "assistant" or not t or t < start or t > end:
            continue
        m = o.get("message", {})
        if m.get("model") in (None, "<synthetic>"):
            continue
        last[m.get("id") or o.get("uuid")] = (t, m.get("usage") or {})
    out = {}
    for t, u in last.values():
        d = t.astimezone(TZ).strftime("%m-%d")
        out[d] = out.get(d, 0) + sum(u.get(k, 0) for k in ("input_tokens", "cache_creation_input_tokens",
                                                             "cache_read_input_tokens", "output_tokens"))
    return out


def merge_days(a, b):
    for k, v in b.items():
        a[k] = a.get(k, 0) + v
    return a


def user_text(o):
    """回傳使用者親自輸入的文字；工具結果、系統注入、完成通知回傳 None。"""
    m = o.get("message", {}).get("content")
    if isinstance(m, list):
        if any(isinstance(c, dict) and c.get("type") == "tool_result" for c in m):
            return None
        m = " ".join(c.get("text", "") for c in m if isinstance(c, dict) and c.get("type") == "text")
    if not isinstance(m, str):
        return None
    m = re.sub(r"<system-reminder>.*?</system-reminder>", "", m, flags=re.S).strip()
    if "<task-notification>" in m or m.startswith("Another Claude session sent a message"):
        return None
    if m.startswith("This session is being continued from a previous conversation"):
        return None  # 對話壓縮後系統插入的摘要
    cmd = re.search(r"<command-name>(.*?)</command-name>", m, flags=re.S)
    if cmd and (m.startswith("<command-message>") or m.startswith("<command-name>")):
        name = cmd.group(1).strip()
        if name in LOCAL_COMMANDS:
            return None
        args = re.search(r"<command-args>(.*?)</command-args>", m, flags=re.S)
        return (name + " " + (args.group(1).strip() if args else "")).strip()
    if not m or m.startswith("<"):
        return None
    if o.get("isMeta") or m.startswith("Base directory for this skill"):
        return None
    return m


def lp(p):
    """Windows 路徑超過 260 字元時要加 \\\\?\\ 前綴才能開檔；Cowork 模式的路徑常超過。"""
    p = os.path.abspath(p)
    return "\\\\?\\" + p if os.name == "nt" and not p.startswith("\\\\?\\") else p


def load(f):
    out = []
    with open(lp(f), encoding="utf-8", errors="ignore") as fh:
        for line in fh:
            try:
                out.append(json.loads(line))
            except Exception:
                pass
    return out


def empty_usage():
    return {"calls": 0, "input": 0, "cache_write": 0, "cache_read": 0, "output": 0}


def usage_by_model(entries, start, end):
    last = {}
    for o in entries:
        if o.get("type") != "assistant":
            continue
        t = ts(o)
        if not t or t < start or t > end:
            continue
        m = o.get("message", {})
        if m.get("model") in (None, "<synthetic>"):
            continue
        last[m.get("id") or o.get("uuid")] = m
    agg = {}
    for m in last.values():
        u = m.get("usage") or {}
        a = agg.setdefault(m["model"], empty_usage())
        a["calls"] += 1
        a["input"] += u.get("input_tokens", 0)
        a["cache_write"] += u.get("cache_creation_input_tokens", 0)
        a["cache_read"] += u.get("cache_read_input_tokens", 0)
        a["output"] += u.get("output_tokens", 0)
    return agg


def app_index():
    idx = {}
    for f in glob.glob(os.path.join(app_dir(), "*", "*", "local_*.json")):
        try:
            d = json.load(open(f, encoding="utf-8"))
        except Exception:
            continue
        cli = d.get("cliSessionId") or d.get("claudeSessionId")
        if not cli:
            mm = re.search(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", json.dumps(d))
            cli = mm.group(0) if mm else None
        if cli:
            idx[cli] = {"local_id": os.path.basename(f)[:-5], "title": d.get("title")}
    return idx


def turn_start_of(entries, start):
    """起點時正在進行的回合從它的使用者輸入算起；否則從起點算起。"""
    prev = None
    for o in entries:
        t = ts(o)
        if t and t < start and o.get("type") == "user" and user_text(o):
            prev = t
    first_after = next((o for o in entries if ts(o) and ts(o) >= start), None)
    opens_new_turn = first_after is not None and first_after.get("type") == "user" and user_text(first_after)
    if prev and not opens_new_turn and start - prev <= dt.timedelta(hours=6):
        return prev
    return start


def user_turns(entries, turn_start, end):
    turns, seen = [], set()
    for o in entries:
        t = ts(o)
        if not t or not (turn_start <= t <= end):
            continue
        txt = None
        if o.get("type") == "user":
            txt = user_text(o)
        elif o.get("type") == "attachment" and (o.get("attachment") or {}).get("type") == "queued_command":
            txt = user_text({"message": {"content": (o.get("attachment") or {}).get("prompt") or ""}})
        if txt and (hm(t), txt) not in seen:
            seen.add((hm(t), txt))
            turns.append({"time": hm(t), "text": txt, "est_tokens": est_tokens(txt)})
    return turns


def subagent_usage(sess_dir, turn_start, end, days):
    subs = []
    for sf in glob.glob(os.path.join(sess_dir, "subagents", "*.jsonl")):
        se = load(sf)
        su = usage_by_model(se, turn_start, end)
        if not su:
            continue
        merge_days(days, tokens_by_day(se, turn_start, end))
        meta = {}
        try:
            meta = json.load(open(sf[:-6] + ".meta.json", encoding="utf-8"))
        except Exception:
            pass
        times = [ts(o) for o in se if ts(o) and turn_start <= ts(o) <= end]
        subs.append({"id": os.path.basename(sf)[:-6], "description": meta.get("description"),
                     "from": hm(min(times)), "to": hm(max(times)), "usage": su})
    for wdir in glob.glob(os.path.join(sess_dir, "subagents", "workflows", "*")):
        run_id = os.path.basename(wdir)
        agg, times, n_agents = {}, [], 0
        for sf in glob.glob(os.path.join(wdir, "*.jsonl")):
            se = load(sf)
            su = usage_by_model(se, turn_start, end)
            if not su:
                continue
            merge_days(days, tokens_by_day(se, turn_start, end))
            n_agents += 1
            times += [ts(o) for o in se if ts(o) and turn_start <= ts(o) <= end]
            for m_, u_ in su.items():
                a_ = agg.setdefault(m_, empty_usage())
                for k in a_:
                    a_[k] += u_[k]
        if not agg:
            continue
        try:
            script = json.load(open(os.path.join(sess_dir, "workflows", run_id + ".json"), encoding="utf-8")).get("script", "")
            name = re.search(r"name:\s*'([^']+)'", script).group(1)
        except Exception:  # 仍在執行的 workflow 還沒有結果檔，改從腳本檔名 <name>-<runId>.js 取名稱
            js = glob.glob(os.path.join(sess_dir, "workflows", "scripts", f"*-{run_id}.js"))
            name = os.path.basename(js[0])[: -len(run_id) - 4] if js else run_id
        subs.append({"id": run_id, "description": f"workflow {name}（{run_id}，{n_agents} 個 agent）",
                     "from": hm(min(times)), "to": hm(max(times)), "usage": agg})
    return subs


def session_record(entries, start, end, sess_dir):
    """一個 session 在期間內的回合與用量；期間內沒有助理回應時回傳 None。"""
    active = [o for o in entries if ts(o) and start <= ts(o) <= end]
    if not any(o.get("type") == "assistant" for o in active):
        return None
    t0 = turn_start_of(entries, start)
    times = [ts(o) for o in active]
    days = tokens_by_day(entries, t0, end)
    subs = subagent_usage(sess_dir, t0, end, days) if sess_dir else []
    return {"cwd": next((o.get("cwd") for o in entries if o.get("cwd")), None),
            "turn_start": hm(t0), "from": hm(min(times)), "to": hm(max(times)),
            "user_turns": user_turns(entries, t0, end),
            "usage_main": usage_by_model(entries, t0, end),
            "subagents": subs, "usage_by_day": dict(sorted(days.items()))}


def cowork_sessions(start):
    """Claude 桌面 App Cowork 模式的 session：每個有一個設定檔 local_*.json 和完整稽核紀錄 audit.jsonl。
    標準對話檔不一定存在，稽核紀錄才是完整來源；它的時間欄位叫 _audit_timestamp。"""
    base = os.path.join(os.path.dirname(app_dir()), "local-agent-mode-sessions")
    for cfg_file in glob.glob(os.path.join(base, "*", "*", "local_*.json")):
        audit = os.path.join(cfg_file[:-5], "audit.jsonl")
        try:
            if dt.datetime.fromtimestamp(os.path.getmtime(lp(audit)), TZ) < start:
                continue
            cfg = json.load(open(lp(cfg_file), encoding="utf-8"))
        except OSError:
            continue
        yield cfg_file, cfg, audit


def main():
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    global MULTI_DAY
    day, hhmm = sys.argv[1], sys.argv[2]
    end_hhmm = sys.argv[sys.argv.index("--end") + 1] if "--end" in sys.argv else None
    to_day = sys.argv[sys.argv.index("--to") + 1] if "--to" in sys.argv else None
    start = dt.datetime.fromisoformat(f"{day}T{hhmm}:00").replace(tzinfo=TZ)
    if to_day:
        MULTI_DAY = to_day != day
        end = dt.datetime.fromisoformat(f"{to_day}T{end_hhmm or '23:59'}:59").replace(tzinfo=TZ)
    else:
        end = dt.datetime.fromisoformat(f"{day}T{end_hhmm}:00").replace(tzinfo=TZ) if end_hhmm else dt.datetime.now(TZ)
    apps = app_index()
    result = []
    for f in glob.glob(os.path.join(PROJ, "*", "*.jsonl")):
        if dt.datetime.fromtimestamp(os.path.getmtime(f), TZ) < start:
            continue
        sid = os.path.basename(f)[:-6]
        entries = load(f)
        sess_dir = f[:-6]
        title = None
        try:
            title = json.load(open(os.path.join(sess_dir, "custom-title.json"), encoding="utf-8")).get("customTitle")
        except Exception:
            pass
        app = apps.get(sid, {})
        rec = session_record(entries, start, end, sess_dir)
        if rec:
            rec.update({"key": app.get("local_id") or sid, "cli_session_id": sid, "local_id": app.get("local_id"),
                        "mode": "code", "transcript": os.path.abspath(f),
                        "title": title or app.get("title") or os.path.basename(rec["cwd"] or sid)})
            result.append(rec)
    for cfg_file, cfg, audit in cowork_sessions(start):
        entries = []
        for o in load(audit):
            if o.get("_audit_timestamp"):
                o["timestamp"] = o["_audit_timestamp"]
                entries.append(o)
        rec = session_record(entries, start, end, None)
        if rec:
            local_id = os.path.basename(cfg_file)[:-5]
            rec.update({"key": local_id, "cli_session_id": cfg.get("cliSessionId") or local_id, "local_id": None,
                        "mode": "cowork", "transcript": os.path.abspath(audit),
                        "title": cfg.get("title") or local_id,
                        "cwd": "、".join(cfg.get("userSelectedFolders") or []) or rec["cwd"]})
            result.append(rec)
    result.sort(key=lambda r: r["turn_start"])
    json.dump({"start": start.isoformat(), "end": end.isoformat(), "multi_day": MULTI_DAY, "sessions": result},
              sys.stdout, ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
