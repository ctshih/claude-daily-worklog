"""印出對話檔在某段時間內的使用者訊息、助理文字與工具呼叫（只讀）。
用法：python dump_turns.py <transcript.jsonl> <MM-DD HH:MM> <MM-DD HH:MM> [--full] [--year YYYY]
時間用本機時區，年份預設今年。--full 時助理文字不截斷。"""
import json, os, sys, datetime as dt
TZ = dt.datetime.now().astimezone().tzinfo
f, a, b = sys.argv[1], sys.argv[2], sys.argv[3]
full = "--full" in sys.argv
year = sys.argv[sys.argv.index("--year") + 1] if "--year" in sys.argv else str(dt.date.today().year)
p = lambda s: dt.datetime.strptime(f"{year}-" + s, "%Y-%m-%d %H:%M").replace(tzinfo=TZ)
t0, t1 = p(a), p(b) + dt.timedelta(seconds=59)
LONG = "\\\\?\\"  # Windows 長路徑前綴 \\?\
if os.name == "nt" and not f.startswith(LONG):
    f = LONG + os.path.abspath(f)  # Cowork 模式的路徑常超過 260 字元
for line in open(f, encoding="utf-8", errors="ignore"):
    try: o = json.loads(line)
    except Exception: continue
    t = o.get("timestamp") or o.get("_audit_timestamp")  # Cowork 稽核紀錄用 _audit_timestamp
    if not t: continue
    t = dt.datetime.fromisoformat(t.replace("Z", "+00:00")).astimezone(TZ)
    if not (t0 <= t <= t1): continue
    lt = t.strftime("%m-%d %H:%M")
    typ = o.get("type")
    if typ == "attachment" and (o.get("attachment") or {}).get("type") == "queued_command":
        print(f"[{lt}] USER(插入): {o['attachment'].get('prompt','')[:800]}"); continue
    if typ not in ("user", "assistant"): continue
    m = o.get("message", {}).get("content")
    if isinstance(m, str):
        print(f"[{lt}] {typ.upper()}: {m[:1500]}"); continue
    for c in m or []:
        if not isinstance(c, dict): continue
        if c.get("type") == "text" and c["text"].strip():
            print(f"[{lt}] {typ.upper()}: {c['text'] if full else c['text'][:2500]}")
        elif c.get("type") == "tool_use":
            i = c.get("input", {})
            print(f"[{lt}]   tool {c['name']}: {str(i.get('description') or i.get('file_path') or i.get('prompt','')[:150] or '')[:200]}")
