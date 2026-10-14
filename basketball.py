# -*- coding: utf-8 -*-
"""
basketball.py —— 杨瀚森 / 开拓者 篮球数据抓取（数据源：ESPN 官方 API）

输出：<项目目录>/assets/basketball.json，供 refresh_snapshot.py 合并进每日快照的 basketball 字段。

数据来源与可靠性：
- 赛程 / 赛果 / 单场球员数据：ESPN 官方 API（site.api.espn.com）
  · 球队赛程   /sports/basketball/nba/teams/por/schedule
  · 比赛总览   /sports/basketball/nba/summary?event=<id>   （含官方 boxscore）
  · 球员生涯   /apis/common/v3/sports/basketball/nba/athletes/5217746/gamelog
  说明：新闻报道里的单场数据常有出入（例：2026-10-08 一役，部分媒体写「1篮板3助攻」），
        本脚本一律以 ESPN 官方 boxscore 为准。
- 新闻：中文主流媒体（新浪体育/腾讯体育/搜狐/7M/南都），由每日任务侧维护并保留，
  脚本只在快照里已存在 basketball.news 时原样保留，不覆盖。

用法：python basketball.py
"""
import json
import os
import re
import ssl
import subprocess
import sys
import urllib.request
from datetime import datetime, timedelta, timezone

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")
CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE
BJ = timezone(timedelta(hours=8))

ROOT = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(ROOT, "assets", "basketball.json")
SNAP_URL = "https://textdb.dev/api/data/wb-c7d2f4a91b6e3805fa2d1c74e9b8a603"

POR = "por"
YH_ID = "5217746"          # 杨瀚森 ESPN athlete id
FOCUS = ["开拓者", "中国男篮", "撕裂之城混音"]
# ↑ 关注的三支队伍（名称需与 upcoming[].team 一致，说明文字按它们逐条动态生成）

# v234 · 篮球页图片资源（均转存至图床直链）
COURT_BG = "https://workbuddy-space-static.codebuddy.work/image/LrfoGTrmsbRb4CmcJ3xNEx.jpeg"
# ↑ 杨瀚森 · 开拓者 BLAZERS 16 号（白色球衣，主场看台背景，用户提供 3200×1800）
#   用途：篮球页整页底图（v101 的 M.ball）+ 球员卡头像
PLAYER_PHOTO = "https://workbuddy-space-static.codebuddy.work/image/9TqyRCJKffvLY2WxMSS5AN.jpg"
# ↑ 杨瀚森早期照片（PDX 16 号，用户提供）——hero 已隐藏，此图暂未使用，保留备查

# ESPN 队名缩写 -> 中文（列表页只显示中文，避免 "Lions/Kings" 这样的英文缩写）
CN = {
    "POR": "开拓者", "GS": "勇士", "GSW": "勇士", "SAC": "国王", "LON": "伦敦雄狮",
    "LAL": "湖人", "LAC": "快船", "DEN": "掘金", "MIN": "森林狼", "OKC": "雷霆",
    "HOU": "火箭", "MEM": "灰熊", "NOP": "鹈鹕", "SAS": "马刺", "UTA": "爵士",
    "DAL": "独行侠", "PHX": "太阳", "PHO": "太阳", "BOS": "凯尔特人", "NYK": "尼克斯",
    "BKN": "篮网", "PHI": "76人", "TOR": "猛龙", "CHI": "公牛", "CLE": "骑士",
    "DET": "活塞", "IND": "步行者", "MIL": "雄鹿", "ATL": "老鹰", "CHA": "黄蜂",
    "MIA": "热火", "ORL": "魔术", "WAS": "奇才", "UTA ": "爵士", "MEM ": "灰熊",
    "BKN ": "篮网", "CHI ": "公牛", "DEN ": "掘金", "MIN ": "森林狼", "NYK ": "尼克斯",
    "DAL ": "独行侠", "PHI ": "76人", "TOR ": "猛龙", "CLE ": "骑士", "DET ": "活塞",
    "IND ": "步行者", "MIL ": "雄鹿", "ATL ": "老鹰", "CHA ": "黄蜂", "MIA ": "热火",
    "ORL ": "魔术", "WAS ": "奇才", "HOU ": "火箭", "SAS ": "马刺", "SAC ": "国王",
    "PHX ": "太阳", "LAL ": "湖人", "LAC ": "快船", "NOP ": "鹈鹕", "OKC ": "雷霆",
}

# v243 · 腾讯体育中文队名 -> ESPN 队徽缩写（ESPN CDN 用的就是这几个，除爵士是 utah）
#   用途：整季赛程卡的对手队徽。ESPN 无该队队徽时（如伦敦雄狮）页面回落显示缩写。
CN2AB = {
    "老鹰": "ATL", "凯尔特人": "BOS", "鹈鹕": "NO", "公牛": "CHI", "骑士": "CLE",
    "独行侠": "DAL", "掘金": "DEN", "活塞": "DET", "勇士": "GS", "火箭": "HOU",
    "步行者": "IND", "快船": "LAC", "湖人": "LAL", "热火": "MIA", "雄鹿": "MIL",
    "森林狼": "MIN", "篮网": "BKN", "尼克斯": "NY", "魔术": "ORL", "76人": "PHI",
    "太阳": "PHX", "开拓者": "POR", "国王": "SAC", "马刺": "SA", "雷霆": "OKC",
    "爵士": "UTAH", "奇才": "WSH", "猛龙": "TOR", "灰熊": "MEM", "黄蜂": "CHA",
    "伦敦雄狮": "LON",
}
# 腾讯 matchDesc -> 卡片上的短标签（"NBA杯小组赛西部C组" 太长会挤爆标签）
COMP_SHORT = {"NBA杯小组赛西部C组": "NBA杯", "NBA杯小组赛东部A组": "NBA杯",
              "NBA杯小组赛东部B组": "NBA杯", "NBA杯小组赛西部B组": "NBA杯"}

# v243 · 开拓者整季赛程（腾讯体育 matchweb）
#   为什么不用 ESPN：ESPN 的 /teams/por/schedule 目前只返回 4 场（常规赛赛程尚未下发到该接口），
#   而腾讯这份「开拓者赛程」是整季 84 场（季前赛 4 + 常规赛 76 + NBA 杯 4），北京时间、带队徽。
#   ⚠ 主客判定：腾讯把**主队放在右侧**（rightId=22 → 开拓者主场）——
#     已用 2026-10-08(主) / 10-13(主) / 10-14(客) 三场与 ESPN 官方交叉验证一致。
QQ_SCHEDULE = ("https://matchweb.sports.qq.com/team/matchList"
               "?teamId=22&competitionId=100000&callback=cb")
QQ_REFERER = "https://sports.qq.com/kbsweb/teams.htm?tid=22&cid=100000"


def get(url, timeout=25, tries=2):
    last = None
    for _ in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=timeout, context=CTX) as r:
                return json.loads(r.read().decode("utf-8", "ignore"))
        except Exception as e:
            last = e
    raise last


def get_qq(url, timeout=25, tries=2):
    """腾讯 matchweb 走 JSONP（callback=cb），剥掉包装后当 JSON 解析。"""
    last = None
    for _ in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Referer": QQ_REFERER})
            with urllib.request.urlopen(req, timeout=timeout, context=CTX) as r:
                t = r.read().decode("utf-8", "ignore")
            i, j = t.find("("), t.rfind(")")
            if i < 0 or j <= i:
                raise ValueError("JSONP 结构异常")
            return json.loads(t[i + 1:j])
        except Exception as e:
            last = e
    raise last


def bj(dt_iso):
    """UTC ISO -> (北京 date, 北京 time)"""
    d = datetime.fromisoformat(dt_iso.replace("Z", "+00:00")).astimezone(BJ)
    return d.strftime("%Y-%m-%d"), d.strftime("%H:%M")


def yang_stat(event_id):
    """取某场比赛杨瀚森的官方单场数据（ESPN boxscore）；未出场返回 {"dnp":True}，请求失败返回 None。"""
    try:
        sm = get("https://site.api.espn.com/apis/site/v2/sports/basketball/nba/summary?event=%s" % event_id)
        for tm in (sm.get("boxscore") or {}).get("players", []):
            if (tm.get("team") or {}).get("abbreviation", "").lower() != POR:
                continue
            for st in tm.get("statistics", []):
                names = st.get("names") or []
                for a in st.get("athletes", []):
                    nm = ((a.get("athlete") or {}).get("displayName") or "")
                    if "Yang" in nm or "Hansen" in nm:
                        if a.get("didNotPlay"):
                            return {"dnp": True}
                        vals = a.get("stats") or []
                        d = {k: v for k, v in zip(names, vals)}
                        d["starter"] = bool(a.get("starter"))
                        return d
        return {"dnp": True}
    except Exception:
        return None


# ---------- 队徽转存（ESPN CDN -> 图床，带本地缓存） ----------
# 理由：页面按「零外链」原则渲染，且国内直连 a.espncdn.com 可能不稳；
#      转存到图床后一次缓存、长期复用，失败则由页面用缩写徽标兜底，不影响功能。
LOGO_CACHE = os.path.join(ROOT, "assets", "ball-logos.json")
UPLOAD_PY = ("C:/Users/Administrator/AppData/Local/Programs/WorkBuddy/resources/app.asar.unpacked"
             "/resources/plugins/workbuddy-builtin/skills/library/manage/upload_image.py")


def load_logos():
    try:
        return json.load(open(LOGO_CACHE, encoding="utf-8")) or {}
    except Exception:
        return {}


def save_logos(cache):
    try:
        os.makedirs(os.path.dirname(LOGO_CACHE), exist_ok=True)
        with open(LOGO_CACHE, "w", encoding="utf-8") as f:
            json.dump(cache, f, ensure_ascii=False, indent=1)
    except Exception:
        pass


def ensure_logo(abbr, cache):
    ab = (abbr or "").strip().lower()
    if not ab:
        return ""
    if cache.get(ab):
        return cache[ab]
    tmp = os.path.join(ROOT, "assets", "_logo_%s.png" % ab)
    try:
        req = urllib.request.Request("https://a.espncdn.com/i/teamlogos/nba/500/%s.png" % ab,
                                     headers={"User-Agent": UA})
        data = urllib.request.urlopen(req, timeout=20, context=CTX).read()
        with open(tmp, "wb") as f:
            f.write(data)
        r = subprocess.run([sys.executable, UPLOAD_PY, tmp],
                           capture_output=True, text=True, timeout=150)
        m = re.search(r'"url"\s*:\s*"([^"]+)"', r.stdout or "")
        if m:
            cache[ab] = m.group(1)
            print("[ok] 队徽 %s -> %s" % (ab.upper(), m.group(1)))
            return cache[ab]
        print("[warn] 队徽 %s 上传无返回" % ab.upper())
    except Exception as e:
        print("[warn] 队徽 %s 转存失败: %s" % (ab.upper(), str(e)[:70]))
    finally:
        try:
            os.remove(tmp)
        except Exception:
            pass
    return ""


def main():
    now = datetime.now(BJ)
    today = now.date()
    fails = []
    LOGOS = load_logos()

    # ---------- 1. 开拓者赛程 ----------
    events = []
    try:
        sch = get("https://site.api.espn.com/apis/site/v2/sports/basketball/nba/teams/%s/schedule" % POR)
        for e in sch.get("events", []):
            c = (e.get("competitions") or [{}])[0]
            comps = c.get("competitors") or []
            me = next((x for x in comps if (x.get("team") or {}).get("abbreviation", "").lower() == POR), None)
            op = next((x for x in comps if x is not me), None)
            st = (e.get("seasonType") or {})
            stname = st.get("name") or st.get("abbreviation") or ""
            events.append({
                "id": e.get("id"),
                "utc": e.get("date"),
                "name": e.get("name") or "",
                "comp": ("NBA 季前赛" if "Preseason" in stname else
                         "NBA 常规赛" if "Regular" in stname else ("NBA " + str(stname)).strip()),
                "home": bool(me and me.get("homeAway") == "home"),
                "opp": CN.get(((op.get("team") or {}).get("abbreviation") or "").upper())
                        or (op.get("team") or {}).get("shortDisplayName")
                        or (op.get("team") or {}).get("displayName") or "?",
                "oppAbbr": (op.get("team") or {}).get("abbreviation") or "",
                "myScore": ((me or {}).get("score") or {}).get("displayValue") if me else None,
                "opScore": ((op or {}).get("score") or {}).get("displayValue") if op else None,
                "state": (c.get("status") or {}).get("type", {}).get("state") or "",
                "detail": (c.get("status") or {}).get("type", {}).get("detail") or "",
            })
        print("[ok] ESPN 开拓者赛程 %d 场" % len(events))
    except Exception as e:
        fails.append("espn-schedule")
        print("[fail] ESPN 赛程: %s" % str(e)[:90])

    # ---------- 2. 未来一周 / 前 7 天 ----------
    upcoming, recent_ids = [], []
    for ev in events:
        if not ev["utc"]:
            continue
        d, t = bj(ev["utc"])
        try:
            dd = datetime.strptime(d, "%Y-%m-%d").date()
        except Exception:
            continue
        delta = (dd - today).days
        if 0 <= delta <= 7 and ev["state"] == "pre":
            ab_op = (ev.get("oppAbbr") or "").strip().upper()
            upcoming.append({"d": d[5:], "bj": t, "comp": ev["comp"], "team": "开拓者",
                             "opp": ev["opp"], "home": ev["home"], "id": ev["id"],
                             "opAbbr": ab_op,
                             "meLogo": ensure_logo("POR", LOGOS),
                             "opLogo": (ensure_logo(ab_op, LOGOS) if ab_op else "")})
        elif -7 <= delta < 0 and ev["state"] == "post":
            recent_ids.append(ev)

    upcoming.sort(key=lambda x: (x["d"], x["bj"]))

    # ---------- 3. 杨瀚森逐场数据（官方 boxscore） ----------
    recent = []
    for ev in recent_ids:
        item = {"id": ev["id"], "d": bj(ev["utc"])[0][5:], "bj": bj(ev["utc"])[1], "comp": ev["comp"],
                "team": "开拓者", "opp": ev["opp"], "home": ev["home"],
                "score": "%s-%s" % (ev["myScore"], ev["opScore"]),
                "win": (ev["myScore"] is not None and ev["opScore"] is not None
                        and float(ev["myScore"]) > float(ev["opScore"])),
                "stat": None}
        try:
            sm = get("https://site.api.espn.com/apis/site/v2/sports/basketball/nba/summary?event=%s" % ev["id"])

            # --- 3a. 杨瀚森个人数据（官方 boxscore） ---
            for tm in (sm.get("boxscore") or {}).get("players", []):
                if (tm.get("team") or {}).get("abbreviation", "").lower() != POR:
                    continue
                for st in tm.get("statistics", []):
                    names = st.get("names") or []
                    for a in st.get("athletes", []):
                        nm = ((a.get("athlete") or {}).get("displayName") or "")
                        if "Yang" in nm or "Hansen" in nm:
                            if a.get("didNotPlay"):
                                item["stat"] = {"dnp": True}
                            else:
                                vals = a.get("stats") or []
                                item["stat"] = {k: v for k, v in zip(names, vals)}
                                item["stat"]["starter"] = bool(a.get("starter"))
                            break
            if item["stat"] is None:
                item["stat"] = {"dnp": True}

            # --- 3b. 战报详情：分节比分 / 队徽（供「单场战报」版式使用） ---
            comp0 = ((sm.get("header") or {}).get("competitions") or [{}])[0]
            comps = comp0.get("competitors") or []
            my = next((x for x in comps
                       if (x.get("team") or {}).get("abbreviation", "").lower() == POR), None)
            opp = next((x for x in comps if x is not my), None)
            labs, mine, theirs = [], [], []
            for i, ls in enumerate((my or {}).get("linescores") or []):
                try:
                    mine.append(int(float(ls.get("displayValue") or 0)))
                    labs.append("第%d节" % (i + 1))
                except Exception:
                    pass
            for ls in (opp or {}).get("linescores") or []:
                try:
                    theirs.append(int(float(ls.get("displayValue") or 0)))
                except Exception:
                    pass
            if mine and theirs:
                item["lines"] = {"labels": labs, "me": mine, "op": theirs,
                                 "meTotal": sum(mine), "opTotal": sum(theirs)}
            item["meAbbr"] = ((my or {}).get("team") or {}).get("abbreviation") or "POR"
            item["opAbbr"] = ((opp or {}).get("team") or {}).get("abbreviation") or ""
            item["meLogo"] = (ensure_logo(item["meAbbr"], LOGOS)
                              or ((my or {}).get("team") or {}).get("logo") or "")
            item["opLogo"] = (ensure_logo(item["opAbbr"], LOGOS)
                              or ((opp or {}).get("team") or {}).get("logo") or "")
            item["opCn"] = ev["opp"]

            # --- 3c. 双方球队技术统计（数据对比条的数据源） ---
            tstats_raw = {}
            for t in (sm.get("boxscore") or {}).get("teams", []):
                ab = ((t.get("team") or {}).get("abbreviation") or "").lower()
                tstats_raw[ab] = {st.get("name"): st.get("displayValue")
                                  for st in (t.get("statistics") or [])}
            md = tstats_raw.get(POR, {})
            od = tstats_raw.get((item["opAbbr"] or "").lower(), {})

            def _num(v):
                try:
                    return float(str(v).replace("%", ""))
                except Exception:
                    return None

            rows = []
            for k, cn, en in [("totalRebounds", "篮板", "REBOUNDS"), ("assists", "助攻", "ASSIST"),
                              ("steals", "抢断", "STEAL"), ("blocks", "盖帽", "BLOCK"),
                              ("turnovers", "失误", "TURNOVER")]:
                a, b = _num(md.get(k)), _num(od.get(k))
                if a is None and b is None:
                    continue
                rows.append({"cn": cn, "en": en, "me": a, "op": b})
            if rows:
                item["tstats"] = rows

            shoot = []
            for pk, mk, cn in [("fieldGoalPct", "fieldGoalsMade-fieldGoalsAttempted", "投篮命中率"),
                               ("threePointFieldGoalPct", "threePointFieldGoalsMade-threePointFieldGoalsAttempted", "三分命中率"),
                               ("freeThrowPct", "freeThrowsMade-freeThrowsAttempted", "罚球命中率")]:
                a, b = _num(md.get(pk)), _num(od.get(pk))
                if a is None and b is None:
                    continue
                shoot.append({"cn": cn, "en": "命中率", "me": a, "op": b,
                              "meSub": md.get(mk) or "", "opSub": od.get(mk) or ""})
            if shoot:
                item["shoot"] = shoot

            print("[ok] %s %s 杨瀚森数据: %s | 分节 %s | 对比项 %d 条"
                  % (item["d"], item["opp"], json.dumps(item["stat"], ensure_ascii=False)[:90],
                     item.get("lines", {}).get("me"), len(rows)))
        except Exception as e:
            fails.append("boxscore")
            print("[fail] %s boxscore: %s" % (item["d"], str(e)[:80]))
        recent.append(item)
    recent.sort(key=lambda x: x["d"], reverse=True)

    # ---------- 3.5 「开拓者比赛结果」列表（页面左列下方，默认露 3 条、可滚动） ----------
    #   与 recent 的区别：recent 只含近 7 天且带完整战报详情（分节/球队统计/命中率）；
    #   results 覆盖本赛季全部已结束比赛、字段精简（仅列表所需），避免快照体积膨胀。
    #   最新在前，最多 RESULTS_MAX 场；杨瀚森数据沿用 recent 已取到的，其余场次单独补取一次。
    RESULTS_MAX = 10
    stat_by_id = {it.get("id"): it.get("stat") for it in recent}
    results = []
    done = [ev for ev in events
            if ev.get("state") == "post" and ev.get("myScore") is not None and ev.get("opScore") is not None]
    done.sort(key=lambda e: e.get("utc") or "", reverse=True)
    for ev in done[:RESULTS_MAX]:
        d0, t0 = bj(ev["utc"])
        try:
            win = float(ev["myScore"]) > float(ev["opScore"])
        except Exception:
            win = False
        st = stat_by_id.get(ev["id"])
        if st is None:
            st = yang_stat(ev["id"])
            if st is None:
                fails.append("result-stat")
        ab_op = (ev.get("oppAbbr") or "").strip().upper()
        results.append({"d": d0[5:], "bj": t0, "comp": ev["comp"], "opp": ev["opp"],
                        "home": ev["home"], "me": ev["myScore"], "op": ev["opScore"],
                        "score": "%s-%s" % (ev["myScore"], ev["opScore"]),
                        "win": win, "stat": st,
                        "meAbbr": "POR", "opAbbr": ab_op,
                        "meLogo": ensure_logo("POR", LOGOS),
                        "opLogo": (ensure_logo(ab_op, LOGOS) if ab_op else "")})
    print("[ok] 比赛结果列表 %d 场（最多 %d）" % (len(results), RESULTS_MAX))

    # ---------- 3.8 整季赛程（腾讯体育：开拓者 84 场；这里只留「未开始」的做成赛程卡） ----------
    #   已结束的那场交给 results（它带杨瀚森官方 boxscore），赛程卡与赛果卡不重复。
    NO_LOGO = {"LON"}          # 伦敦雄狮：ESPN 无队徽，页面回落显示缩写
    season = []
    try:
        qq = get_qq(QQ_SCHEDULE)
        groups = qq.get("data") or {}
        raw = []
        for k in sorted(groups):
            raw += (groups[k] or [])
        raw.sort(key=lambda x: x.get("startTime") or "")
        for x in raw:
            st = x.get("startTime") or ""
            if len(st) < 16 or str(x.get("liveType")) == "4":
                continue
            home = str(x.get("rightId")) == "22"
            opp = (x.get("leftName") if home else x.get("rightName")) or ""
            season.append({"d": st[5:10], "bj": st[11:16],
                           "comp": COMP_SHORT.get(x.get("matchDesc") or "", x.get("matchDesc") or "NBA"),
                           "home": home, "opp": opp, "opAbbr": CN2AB.get(opp, "")})
        print("[ok] 腾讯整季赛程 %d 场（未开始）" % len(season))
    except Exception as e:
        fails.append("qq-schedule")
        print("[fail] 腾讯赛程: %s" % str(e)[:90])

    # 赛程对手队徽：一次性补齐并缓存（ESPN CDN -> 图床），页面靠 opAbbr 查 logos 表
    for s in season:
        ab = (s.get("opAbbr") or "").strip().upper()
        if ab and ab not in NO_LOGO and ab != "POR":
            ensure_logo(ab, LOGOS)
    logos = {}
    for s in season:
        ab = (s.get("opAbbr") or "").strip().upper()
        if ab and LOGOS.get(ab.lower()):
            logos[ab] = LOGOS[ab.lower()]
    por_logo = ensure_logo("POR", LOGOS)
    print("[ok] 赛程对手队徽 %d 个" % len(logos))

    # ---------- 4. 新闻：本地 basketball.json 优先（人工/每日任务维护），其次沿用快照 ----------
    #   注意：必须「本地优先」，否则一旦先跑脚本再去填新闻，本地会以快照里的空数组覆盖，把新闻冲掉。
    news, old_bb = [], {}
    try:
        nf = os.path.join(ROOT, "assets", "ball-news.json")
        if os.path.exists(nf):
            news = json.load(open(nf, encoding="utf-8")) or []
            print("[ok] 新闻文件 ball-news.json：%d 条" % len(news))
        if os.path.exists(OUT):
            local = json.load(open(OUT, encoding="utf-8"))
            if not news:
                news = local.get("news") or []
            old_bb = dict(local)
            print("[ok] 本地已有新闻 %d 条" % len(news))
    except Exception as e:
        print("[warn] 读本地篮球 json 失败: %s" % str(e)[:60])
    try:
        req = urllib.request.Request(SNAP_URL, headers={"User-Agent": UA})
        snap = json.loads(urllib.request.urlopen(req, timeout=25, context=CTX).read().decode("utf-8", "ignore"))
        sbb = snap.get("basketball") or {}
        if not news:
            news = sbb.get("news") or []
        if not old_bb.get("bg"):
            old_bb["bg"] = sbb.get("bg")
        print("[ok] 新闻合计 %d 条（本地优先）" % len(news))
    except Exception as e:
        fails.append("snapshot-read")
        print("[warn] 读取旧快照失败: %s" % str(e)[:80])

    # ---------- 5. 赛程说明：按关注队伍**动态生成**，不写死文案 ----------
    #   逻辑：future 里有该队的比赛 → 列出场次/时间/对手；没有 → 说明「无已公布赛事」。
    #   队伍名统一取 FOCUS；某队若一周内有新增/变动，第二天刷新时说明会自动跟着变。
    def _team_line(team):
        hit = [u for u in upcoming if u.get("team") == team]
        if hit:
            detail = "；".join("%s %s %s%s" % (u.get("d", ""), u.get("bj", ""),
                                             "vs " if u.get("home") else "@ ",
                                             u.get("opp", "")) for u in hit[:3])
            return "%s：未来一周 %d 场（%s）。" % (team, len(hit), detail)
        return "%s：未来一周无已公布赛事。" % team

    note = " ".join(_team_line(t) for t in FOCUS)

    out = {
        "updated": now.strftime("%Y-%m-%d %H:%M"),
        "player": {"name": "杨瀚森", "en": "Yang Hansen", "espnId": YH_ID,
                   "team": "波特兰开拓者", "pos": "中锋", "num": "16",
                   "photo": PLAYER_PHOTO},
        "bg": COURT_BG,
        "focus": FOCUS,
        "news": news,
        "upcoming": upcoming,
        "recent": recent,
        "results": results,
        "season": season,
        "porLogo": por_logo,
        "logos": logos,
        "fails": fails,
        "note": note,
    }
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    save_logos(LOGOS)
    print("\n[OUT] %s  整季赛程 %d 场 / 未来一周 %d 场 / 近 7 天 %d 场 / 结果列表 %d 场 / 新闻 %d 条 / 失败源: %s"
          % (OUT, len(season), len(upcoming), len(recent), len(results), len(news), fails or "无"))
    for u in upcoming:
        print("   upcoming: %s %s 北京 %s vs %s %s" % (u["d"], u["comp"], u["bj"], u["opp"], "(主)" if u["home"] else "(客)"))


if __name__ == "__main__":
    main()
