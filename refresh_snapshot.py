# -*- coding: utf-8 -*-
import urllib.request, urllib.parse, json, time, sys, os
from datetime import datetime

URL = "https://textdb.dev/api/data/wb-c7d2f4a91b6e3805fa2d1c74e9b8a603"
UA  = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
fails = []

def fetch(url, timeout=20, tries=3, headers=None, data=None, method=None):
    h = {"User-Agent": UA, "Accept": "application/json,text/plain,*/*"}
    if headers: h.update(headers)
    last = None
    for i in range(tries):
        try:
            req = urllib.request.Request(url, data=data, headers=h, method=method)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read().decode("utf-8", "ignore")
        except Exception as e:
            last = e; time.sleep(1.5 * (i + 1))
    raise last

def jget(url, timeout=20, tries=3):
    return json.loads(fetch(url, timeout=timeout, tries=tries))

now = datetime.now()
collected_at = now.strftime("%Y-%m-%d %H:%M")
date_str = now.strftime("%Y-%m-%d")
today_key = "%d-%d" % (now.month, now.day)

old = {}
try:
    old = json.loads(fetch(URL, timeout=30, tries=2))
    if not isinstance(old, dict): old = {}
    print("[ok] 旧快照 date=%s" % old.get("date"))
except Exception as e:
    print("[warn] 旧快照不可用: %s" % str(e)[:80])

# 1. 新闻 60s
news = []
try:
    d = jget("https://60s.viki.moe/v2/60s")
    news = [x for x in ((d.get("data") or {}).get("news") or []) if isinstance(x, str)][:8]
    print("[ok] 60s news=%d" % len(news))
except Exception as e:
    fails.append("60s"); news = old.get("news") or []; print("[fail] 60s: %s" % str(e)[:80])

# 2. AI 简报（修正 src/u 映射）
ai = []
try:
    d = jget("https://aihot.news/api/v1/items?mode=selected&window=24h&limit=12")
    for it in (d.get("items") or d.get("data") or []):
        if not isinstance(it, dict): continue
        src = it.get("src")
        if not isinstance(src, dict):
            s0 = it.get("source")
            if isinstance(s0, dict): src = {"name": s0.get("name") or ""}
            elif isinstance(s0, str): src = {"name": s0}
            else: src = {"name": ""}
        links = it.get("links") if isinstance(it.get("links"), dict) else {}
        ai.append({"t": it.get("t") or it.get("title") or "",
                   "s": it.get("s") or it.get("summary") or "",
                   "u": it.get("u") or links.get("original") or links.get("aihot") or "",
                   "src": src})
    ai = ai[:12]
    print("[ok] AI items=%d" % len(ai))
except Exception as e:
    fails.append("ai"); ai = old.get("ai") or []; print("[fail] ai: %s" % str(e)[:80])

# 3. 知乎热榜（多次重试，上游偶发空数组）
zhihu = []
for attempt in range(6):
    try:
        d = jget("https://60s.viki.moe/v2/zhihu", timeout=15, tries=2)
        for it in (d.get("data") or []):
            if isinstance(it, str): zhihu.append(it)
            elif isinstance(it, dict):
                t = it.get("title") or it.get("name") or it.get("word")
                if not t and isinstance(it.get("target"), dict): t = it["target"].get("title")
                if t: zhihu.append(t)
        zhihu = zhihu[:30]
        if zhihu: break
        print("[retry] 知乎第%d次为空" % (attempt + 1)); time.sleep(4)
    except Exception as e:
        print("[retry] 知乎异常: %s" % str(e)[:60]); time.sleep(4)
print("[ok] 知乎=%d" % len(zhihu))
if not zhihu: fails.append("zhihu")

# 4. 微博热搜
weibo = []
try:
    d = jget("https://60s.viki.moe/v2/weibo")
    for it in (d.get("data") or []):
        if not isinstance(it, dict): continue
        t = it.get("title") or it.get("word") or ""
        if not t: continue
        weibo.append({"t": t, "h": str(it.get("hot_value") or it.get("hot") or ""),
                      "u": it.get("link") or it.get("url") or ("https://s.weibo.com/weibo?q=" + urllib.parse.quote(t))})
    print("[ok] 微博=%d" % len(weibo))
except Exception as e:
    print("[fail] 微博: %s" % str(e)[:80])
if not weibo:
    try:
        d = jget("https://api.pearktrue.cn/api/dailyhot/?title=" + urllib.parse.quote("微博"), timeout=15, tries=2)
        for it in (d.get("data") or []):
            if isinstance(it, dict) and (it.get("title") or it.get("name")):
                t = it.get("title") or it.get("name")
                weibo.append({"t": t, "h": str(it.get("hot") or it.get("hotValue") or ""),
                              "u": it.get("url") or ("https://s.weibo.com/weibo?q=" + urllib.parse.quote(t))})
        print("[ok] 微博(备用)=%d" % len(weibo))
    except Exception as e:
        print("[fail] 微博备用: %s" % str(e)[:80])
if not weibo:
    weibo = old.get("weibo") or []; fails.append("weibo"); print("[keep] 微博沿用旧值 n=%d" % len(weibo))

# 5. 百度热搜
baidu = []
try:
    d = jget("https://v2.xxapi.cn/api/baiduhot", timeout=15, tries=3)
    for it in (d.get("data") or []):
        if not isinstance(it, dict): continue
        t = it.get("title") or it.get("word") or ""
        if not t: continue
        baidu.append({"t": t, "h": str(it.get("hot") or ""),
                      "u": it.get("url") or ("https://www.baidu.com/s?wd=" + urllib.parse.quote(t))})
    print("[ok] 百度=%d" % len(baidu))
except Exception as e:
    print("[fail] 百度: %s" % str(e)[:80])
if not baidu:
    try:
        d = jget("https://api.pearktrue.cn/api/dailyhot/?title=" + urllib.parse.quote("百度"), timeout=15, tries=2)
        for it in (d.get("data") or []):
            if isinstance(it, dict) and (it.get("title") or it.get("name")):
                t = it.get("title") or it.get("name")
                baidu.append({"t": t, "h": str(it.get("hot") or it.get("hotValue") or ""),
                              "u": it.get("url") or ("https://www.baidu.com/s?wd=" + urllib.parse.quote(t))})
        print("[ok] 百度(备用)=%d" % len(baidu))
    except Exception as e:
        print("[fail] 百度备用: %s" % str(e)[:80])
if not baidu:
    baidu = old.get("baidu") or []; fails.append("baidu"); print("[keep] 百度沿用旧值 n=%d" % len(baidu))

# 6. opinion.rows
NEG = ["去世","逝世","遇难","事故","爆炸","坠","塌","暴跌","崩盘","被查","落马","曝光","争议","欺诈",
       "造假","起诉","判刑","伤亡","核","地震","台风","暴雨","疫情","裁员","破产","违约","塌方","失联",
       "车祸","致死","身亡","袭击","枪击","坍塌","泄漏","故障"]
def judge(t):
    for kw in NEG:
        if kw in t: return "负面", True, "命中负面线索「%s」" % kw
    return "中性", False, ""
rows = []
def add(title, plat, link):
    if not title: return
    emo, warn, why = judge(title)
    rows.append({"平台": plat, "标题": title, "热度值": "", "链接": {"link": link},
                 "情感": emo, "负面预警": warn, "理由": why, "排序": len(rows) + 1})
for t in zhihu: add(t, "知乎热榜", "https://www.zhihu.com/search?type=content&q=" + urllib.parse.quote(t))
for t in news:  add(t, "60s要闻", "https://www.baidu.com/s?wd=" + urllib.parse.quote(t))
for it in ai:   add(it.get("t") or "", "AI简报", it.get("u") or ("https://www.baidu.com/s?wd=" + urllib.parse.quote(it.get("t") or "")))

plat_cnt, sent_cnt = {}, {}
for r in rows:
    plat_cnt[r["平台"]] = plat_cnt.get(r["平台"], 0) + 1
    sent_cnt[r["情感"]] = sent_cnt.get(r["情感"], 0) + 1
total = len(rows)
pct = {k: round(v * 100.0 / total, 1) for k, v in sent_cnt.items()} if total else {}
summary = {"collected_at": collected_at, "total": total, "platforms": plat_cnt,
           "sentiment": sent_cnt, "sentiment_pct": pct}

# 7. 历史上的今天（安全事件）
BAD = ["出生","诞生","诞辰","生辰","逝世","去世","死亡","身亡","病逝","牺牲","遇难","享年","生于","死于","被杀","刺杀","枪杀","自尽"]
today = []
BAD_TYPE = ("birth", "death", "出生", "逝世", "去世", "死亡")
for api in ["https://60s.viki.moe/v2/today_in_history", "https://api.vvhan.com/api/history/today?type=json"]:
    try:
        d = jget(api, timeout=12, tries=2)
        data = d.get("data")
        if isinstance(data, dict): items = data.get("items") or data.get("list") or []
        elif isinstance(data, list): items = data
        else: items = d.get("items") or d.get("list") or []
        tmp = []
        for it in items:
            if isinstance(it, str):
                y, txt, et = "", it, ""
            elif isinstance(it, dict):
                et = str(it.get("event_type") or it.get("type") or "").lower()
                y = str(it.get("year") or it.get("y") or "")
                txt = it.get("title") or it.get("event") or it.get("desc") or it.get("text") or ""
            else:
                continue
            if et in BAD_TYPE: continue                     # 按事件类型剔除出生/逝世
            if not txt or any(b in txt for b in BAD): continue  # 再按关键词兜底剔除
            tmp.append([y, txt])
        if tmp:
            today = tmp[:3]; print("[ok] 历史上的今天=%d <- %s" % (len(today), api)); break
    except Exception as e:
        print("[fail] history: %s" % str(e)[:70])
if not today:
    today = [["1936", "红一、红四方面军在甘肃会宁胜利会师"],
             ["1874", "万国邮政联盟在瑞士伯尔尼成立"],
             ["1962", "乌干达宣布独立"]]
    print("[fallback] 历史上的今天=内置安全事件 x%d" % len(today))

# 8. 当日封面图（首页背景图的数据源）
#    每日任务先生成并上传图床，把 URL 存到 assets/hero_<date>.url；
#    本脚本只负责把它写进快照的 hero 字段，供首页背景图读取。
#    找不到当日文件时沿用旧快照的 hero，绝不留空（避免首页背景图掉回默认图）。
hero = ""
try:
    hf = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "hero_%s.url" % date_str)
    if os.path.exists(hf):
        hero = open(hf, encoding="utf-8").read().strip()
        print("[ok] 当日封面 hero=%s" % hero)
except Exception as e:
    print("[warn] 读当日封面失败: %s" % str(e)[:60])
if not hero:
    hero = old.get("hero") or ""
    print("[keep] 沿用旧封面 hero=%s" % (hero or "(空)"))

# 9. 篮球模块数据（杨瀚森/开拓者，由 basketball.py 从 ESPN 官方抓取）
bb = None
try:
    bf = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "basketball.json")
    if os.path.exists(bf):
        bb = json.load(open(bf, encoding="utf-8"))
        print("[ok] 篮球数据：未来一周 %d 场 / 近 7 天 %d 场 / 新闻 %d 条"
              % (len(bb.get("upcoming") or []), len(bb.get("recent") or []), len(bb.get("news") or [])))
except Exception as e:
    print("[warn] 读篮球数据失败: %s" % str(e)[:70])

# 9.5 虎扑热榜（hupu.py 抓取：开拓者专区 24小时榜，标题+正文+亮评+评论）
#     写进快照前做裁剪 —— 完整数据留在 assets/hupu.json，快照只放页面够用的量，
#     避免 payload 过大导致写入失败（textdb 对体积敏感）。
HP_LIST_MAX   = 50      # 榜单条数
HP_BODY       = 500     # 每帖正文保留字数
HP_LIGHT_MAX  = 12      # 每帖亮评条数
HP_CMT_MAX    = 12      # 每帖评论条数
HP_TEXT       = 130     # 亮评/评论每条保留字数


def _cut(s, n):
    s = (s or "").replace("\n", " ").strip()
    return s if len(s) <= n else s[:n] + "…"


hp = None
try:
    hf = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "hupu.json")
    if os.path.exists(hf):
        raw = json.load(open(hf, encoding="utf-8"))
        lst = []
        for i, t in enumerate((raw.get("list") or [])[:HP_LIST_MAX], 1):
            lst.append({"i": i, "tid": t.get("tid"), "t": t.get("title") or "", "u": t.get("url") or "",
                        "light": t.get("lights"), "rep": t.get("replies"), "read": t.get("read"),
                        "au": t.get("author") or "", "time": t.get("time") or ""})
        dets = []
        for t in (raw.get("threads") or []):
            dets.append({
                "tid": t.get("tid"), "t": t.get("title") or "", "u": t.get("url") or "",
                "au": t.get("author") or "", "time": t.get("time") or "", "loc": t.get("location") or "",
                "stat": t.get("stat") or {},
                "body": _cut(t.get("content"), HP_BODY),
                "lights": [{"c": _cut(x.get("content"), HP_TEXT), "n": x.get("light"), "au": x.get("author") or ""}
                           for x in (t.get("lights") or [])[:HP_LIGHT_MAX]],
                "cmts": [{"c": _cut(x.get("content"), HP_TEXT), "n": x.get("light"), "au": x.get("author") or "",
                          "op": bool(x.get("isStarter"))} for x in (t.get("comments") or [])[:HP_CMT_MAX]],
                "cmtTotal": t.get("commentTotal"),
            })
        hp = {"updated": raw.get("updated") or "", "topic": raw.get("topic") or "",
              "source": raw.get("source") or "", "total": (raw.get("listMeta") or {}).get("count"),
              "list": lst, "details": dets}
        print("[ok] 虎扑热榜：榜单 %d 条 / 详情 %d 帖" % (len(lst), len(dets)))
except Exception as e:
    print("[warn] 读虎扑数据失败: %s" % str(e)[:70])
if hp is None:
    hp = old.get("hupu")
    print("[keep] 沿用旧虎扑数据" if hp else "[warn] 无虎扑数据")

# 10. payload + POST（Content-Type 必须是 application/json，带 charset 会 500）
payload = {"ts": int(time.time() * 1000), "date": date_str, "hero": hero, "weibo": weibo, "news": news,
           "ai": ai, "todayKey": today_key, "today": today,
           "opinion": {"batch": collected_at, "summary": summary, "rows": rows}, "baidu": baidu,
           "basketball": bb or old.get("basketball"), "hupu": hp}
body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
print("\nPAYLOAD bytes=%d news=%d ai=%d weibo=%d baidu=%d zhihu=%d rows=%d today=%d" %
      (len(body), len(news), len(ai), len(weibo), len(baidu), len(zhihu), len(rows), len(today)))
print("FAILS:", fails or "无")

ok = False
for ct in ["application/json", "text/plain"]:
    for k in range(3):
        try:
            resp = fetch(URL, timeout=60, tries=1, method="POST", headers={"Content-Type": ct}, data=body)
            print("[POST OK ct=%s] %s" % (ct, resp[:100])); ok = True; break
        except Exception as e:
            print("[POST retry ct=%s #%d] %s" % (ct, k + 1, str(e)[:80])); time.sleep(2)
    if ok: break
if not ok: sys.exit(1)

try:
    chk = json.loads(fetch(URL, timeout=30, tries=2))
    s = (chk.get("opinion") or {}).get("summary") or {}
    print("[VERIFY] date=%s batch=%s total=%s platforms=%s weibo=%d baidu=%d todayKey=%s today=%d ai0.src=%s" % (
        chk.get("date"), (chk.get("opinion") or {}).get("batch"), s.get("total"), s.get("platforms"),
        len(chk.get("weibo") or []), len(chk.get("baidu") or []), chk.get("todayKey"),
        len(chk.get("today") or []), json.dumps((chk.get("ai") or [{}])[0].get("src"), ensure_ascii=False)))
except Exception as e:
    print("[VERIFY FAIL]", str(e)[:120])

print("RESULT_JSON=" + json.dumps({"date": date_str, "collected_at": collected_at, "total": total,
      "platforms": plat_cnt, "sentiment": sent_cnt, "sentiment_pct": pct, "fails": fails,
      "news": len(news), "ai": len(ai), "weibo": len(weibo), "baidu": len(baidu), "zhihu": len(zhihu),
      "today": len(today)}, ensure_ascii=False))
