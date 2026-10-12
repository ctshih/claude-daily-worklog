"""把 get_usage 工具回傳的 JSON 轉成 worklog_render.py 用的 usage.json。

用法：python usage_json.py get_usage.json > usage.json
- get_usage.json：Claude 桌面 App 工具 mcp__ccd_session_mgmt__get_usage 的完整回傳，原樣存檔。
- fetched_at 取執行當下的本機時間，所以取得用量後要立刻轉換。
- plan.status 不是 ok 時以 exit 1 結束。
"""
import json, sys, datetime as dt

if len(sys.argv) < 2:
    sys.exit(__doc__)
src = json.load(open(sys.argv[1], encoding="utf-8"))
plan = src.get("plan", src)
if plan.get("status") != "ok":
    sys.stderr.write(f"plan.status = {plan.get('status')}：{plan.get('note', '')}\n")
    sys.exit(1)
windows = []
for w in plan["windows"]:
    label = w["label"]
    if "5-hour" in label:
        key, zh = "five_hour", "5 小時"
    elif "all models" in label:
        key, zh = "seven_day", "本週"
    elif "Weekly" in label:  # 各模型自己的週額度，例如「Weekly · Fable」
        m = label.split("·")[-1].strip()
        key, zh = "seven_day_" + m.lower().replace(" ", "_"), f"{m} 本週"
    else:
        key, zh = label, label
    windows.append({"key": key, "label": zh, "pct": w["percentUsed"], "resets_at": w["resetsAt"]})
json.dump({"ok": True, "fetched_at": dt.datetime.now().astimezone().isoformat(),
           "plan": "Claude " + str(plan.get("plan", "")), "windows": windows},
          sys.stdout, ensure_ascii=False, indent=1)
