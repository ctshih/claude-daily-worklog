"""期間報告（週報）的準備：沿用每日摘要，並列出每個 session 待寫的回合。

用法：python worklog_plan.py <工作資料夾>
- 讀 <工作資料夾>/stats.json（worklog_stats.py --to 的輸出）。
- 期間內每一天若有 ~/.claude/worklog/<YYYYMMDD>/summaries.json，把它的回合鍵加上「MM-DD 」前綴，
  併入 <工作資料夾>/summaries.json；已存在的條目不覆蓋。每日的 request／delivery 只在週報還沒有時才沿用。
- 輸出 <工作資料夾>/plan.json：每個 session 的對話檔路徑、活動時段、回合鍵、使用者原文、既有摘要、子代理描述。
- 印出每個 session 還缺幾個回合摘要。
"""
import json, os, glob, sys, datetime as dt

W = sys.argv[1]
stats = json.load(open(os.path.join(W, "stats.json"), encoding="utf-8"))
sp = os.path.join(W, "summaries.json")
summ = json.load(open(sp, encoding="utf-8")) if os.path.exists(sp) else {}

start = dt.datetime.fromisoformat(stats["start"]).date()
end = dt.datetime.fromisoformat(stats["end"]).date()
day = start
while day <= end:
    f = os.path.expanduser(f"~/.claude/worklog/{day:%Y%m%d}/summaries.json")
    if os.path.exists(f):
        for key, v in json.load(open(f, encoding="utf-8")).items():
            dst = summ.setdefault(key, {})
            for k in ("request", "delivery"):
                dst.setdefault(k, v.get(k, ""))
            for tk, tv in v.get("turns", {}).items():
                dst.setdefault("turns", {}).setdefault(f"{day:%m-%d} {tk}", tv)
            for sk, sv in v.get("subagent_names", {}).items():
                dst.setdefault("subagent_names", {}).setdefault(sk, sv)
    day += dt.timedelta(days=1)
json.dump(summ, open(sp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

plan = {}
for s in stats["sessions"]:
    cnt, keys = {}, []
    for t in s["user_turns"]:
        cnt[t["time"]] = cnt.get(t["time"], 0) + 1
        k = t["time"] if cnt[t["time"]] == 1 else f"{t['time']}#{cnt[t['time']]}"
        keys.append({"key": k, "text": t["text"], "existing_summary": summ.get(s["key"], {}).get("turns", {}).get(k)})
    found = [s["transcript"]] if s.get("transcript") else glob.glob(os.path.join(
        os.environ.get("CLAUDE_CONFIG_DIR") or os.path.expanduser("~/.claude"), "projects", "*", f"{s['cli_session_id']}.jsonl"))
    plan[s["key"]] = {"title": s["title"], "cwd": s["cwd"],
                      "transcript": os.path.abspath(found[0]).replace(os.sep, "/") if found else None,
                      "active": f"{s['from']}~{s['to']}", "turns": keys,
                      "subagent_descriptions": [a["description"] for a in s["subagents"]],
                      "existing_request": summ.get(s["key"], {}).get("request"),
                      "existing_delivery": summ.get(s["key"], {}).get("delivery")}
json.dump(plan, open(os.path.join(W, "plan.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
for k, p in plan.items():
    todo = sum(1 for t in p["turns"] if not t["existing_summary"] or "本檔產出時仍在進行" in t["existing_summary"])
    print(f"{k}  {p['title'][:20]:20}  回合 {len(p['turns']):3}  待寫 {todo:3}  子代理 {len(p['subagent_descriptions'])}")
