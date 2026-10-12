# -*- coding: utf-8 -*-
"""selfcheck.py — html-report 產出的機械自檢。用法：python selfcheck.py <report.html>
檢查：占位符殘留、外部資源載入（MathJax 為唯一例外，過但警告）、嵌入圖存在、
限制章節、TOC 錨點對應。全過 exit 0，否則 exit 1。"""
import re
import sys

for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8", errors="replace")

if len(sys.argv) != 2:
    sys.exit("用法：python selfcheck.py <report.html>")

html = open(sys.argv[1], encoding="utf-8").read()
problems, warnings = [], []

# 1) 占位符——排除 <script>/<pre>/<code>（程式碼裡的 __init__ 之類不是模板占位符）；
#    允許占位符內含空白與全形字、長度放寬到 80（模板的「__一行副標：主題 · 日期__」也要抓得到）
prose = re.sub(r"<script.*?</script>|<pre.*?</pre>|<code.*?</code>", "", html, flags=re.S | re.I)
m = re.search(r"__[^_<>\n]{1,80}?__", prose)
if m:
    problems.append("殘留模板占位符：%s" % m.group(0))

# 2) 外部資源——<a href> 連外允許（先移除 a 開標籤再掃）；
#    涵蓋屬性載入（src/srcset/href/poster/data）、協定相對 //、單雙引號、CSS @import 與 url()
no_anchor = re.sub(r"<a\b[^>]*>", "", html, flags=re.I)
EXT_PATTERNS = [
    r'\b(?:src|srcset|href|poster|data)\s*=\s*["\']\s*(?:https?:)?//[^"\']*',
    r'@import\s+(?:url\()?\s*["\']?\s*(?:https?:)?//[^"\')\s;]*',
    r'\burl\(\s*["\']?\s*(?:https?:)?//[^"\')\s]*',
]
hits = [h for pat in EXT_PATTERNS for h in re.findall(pat, no_anchor, re.I)]
mathjax_hits = [h for h in hits if "mathjax" in h.lower()]
other_hits = [h for h in hits if "mathjax" not in h.lower()]
if other_hits:
    problems.append("載入外部資源（單檔自足鐵則）：%s…" % other_hits[0][:70])
elif mathjax_hits:
    warnings.append("MathJax CDN 例外：數學式需連網才會渲染——確認報告「限制」節已註明")

# 3) 嵌入圖
if "<svg" not in html and "data:image/" not in html:
    problems.append("沒有任何嵌入圖（inline SVG 或 data URI）——結果數據必須視覺化")

# 4) 限制章節（取 h2/h3 內文、剝巢狀標籤後比對，允許 <h2><span>限制</span></h2> 這種寫法）
headings = [re.sub(r"<[^>]+>", "", h) for h in re.findall(r"<h[23][^>]*>(.*?)</h[23]>", html, re.S | re.I)]
if not any(re.search(r"限制|注意事項|limitations", h, re.I) for h in headings):
    problems.append("缺「限制／注意事項」章節標題")

# 5) TOC 錨點（class 含 toc token 即可，如 class=\"toc top\"）
navs = re.findall(r'<nav[^>]*class="[^"]*\btoc\b[^"]*"[^>]*>(.*?)</nav>', html, re.S | re.I)
missing = []
for nav in navs:
    for anchor in re.findall(r'href="#([^"]+)"', nav):
        if not re.search(r'id="%s"' % re.escape(anchor), html):
            missing.append(anchor)
if missing:
    problems.append("TOC 錨點缺對應章節 id：%s" % "、".join(missing))
if not navs:
    warnings.append("找不到 class 含 toc 的 <nav>——確認報告有目錄（短報告可省略）")

for w in warnings:
    print("[warn]", w)
if problems:
    for p in problems:
        print("[fail]", p)
    sys.exit(1)
print("自檢通過：無占位符、無外部資源、有嵌入圖、有限制章節、TOC 錨點齊")
