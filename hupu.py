# -*- coding: utf-8 -*-
"""
hupu.py —— 虎扑热榜抓取（可直接放进 DarrenCD/workbuddy-daily-refresh 仓库）
====================================================================
用途：补上该仓库当前缺失的一环——虎扑热榜（repo 的 refresh_snapshot.py 在找不到
      assets/hupu.json 时会沿用线上旧数据，所以虎扑其实是**不刷新**的）。

输出：<项目目录>/assets/hupu.json，字段与 refresh_snapshot.py 期望的输入完全对齐：
  {
    "source","topic","updated","total","listMeta":{"count":N},
    "list":   [{tid,title,url,lights,replies,read,author,time}],
    "threads":[{tid,title,url,author,time,location,stat,content,
                lights:[{content,light,author}],
                comments:[{content,light,author,isStarter}],
                commentTotal}]
  }

部署（一次）：
  1. 把本文件保存为仓库根目录的 hupu.py
  2. 在 .github/workflows/daily-refresh.yml 里 `python basketball.py` 之前加一步：
       - name: 抓取虎扑热榜（开拓者专区 24 小时榜）
         run: python hupu.py
  3. 仓库的 .gitignore 已忽略 assets/，无需改动

依赖：仅 Python 标准库。无需任何密钥。

⚠️ 反爬（必读）：
  bbs.hupu.com 走阿里云 WAF，裸请求会返回约 16KB 验证页（含 aliyun_waf）。
  本脚本的对策：① 先打一次普通版块页换 Cookie（acw_tc / csrfToken）；② 带完整浏览器头；
  ③ 请求间隔 ≥1s；④ 命中验证页退避重试。
  GitHub Actions 的机房 IP 比家用宽带更容易被 WAF 拦，所以：
  - 若连续命中验证页导致榜单条数 < MIN_LIST，脚本**不写 assets/hupu.json** 并退出码 1，
    此时 refresh_snapshot.py 会沿用线上旧虎扑数据（不会清空），workflow 里用
    `continue-on-error: true` 即可让后续步骤照常跑。

用法：
  python hupu.py             # 抓取并写 assets/hupu.json
  python hupu.py --dry       # 只抓取并打印统计，不写文件
  python hupu.py --out x.json
"""
import json
import os
import random
import re
import sys
import time
import html as _html
import http.cookiejar
import urllib.error
import urllib.request

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124 Safari/537.36")
HUPU_LIST = "https://bbs.hupu.com/blazers-hot"
HUPU_WARM = "https://bbs.hupu.com/blazers"
TOPIC = "开拓者专区 · 24小时榜"
ROOT = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(ROOT, "assets", "hupu.json")

TOP_DETAIL = 8        # 抓详情的前 N 帖
MAX_PER_LIST = 12     # 每帖最多保留的亮评 / 评论条数
GAP = 1.2             # 请求间隔（秒）
MIN_LIST = 8          # 榜单条数下限，低于此值判为被拦/结构变更，不写文件
WAF_MARK = ("aliyun_waf", "aliyunCaptcha", "captcha-content-container")

COOKIES = http.cookiejar.CookieJar()

BROWSER_HEADERS = {
    "User-Agent": UA,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,"
              "image/avif,image/webp,image/apng,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9",
    "Upgrade-Insecure-Requests": "1",
    "sec-ch-ua": '"Chromium";v="124", "Google Chrome";v="124", "Not-A.Brand";v="99"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"Windows"',
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "same-origin",
    "Sec-Fetch-User": "?1",
}


def _opener():
    return urllib.request.build_opener(
        urllib.request.ProxyHandler({}),
        urllib.request.HTTPCookieProcessor(COOKIES),
    )


def _is_waf(text):
    return any(m in (text or "") for m in WAF_MARK)


def get(url, tries=4, waf_wait=25.0, referer="https://bbs.hupu.com/"):
    last = None
    for i in range(tries):
        try:
            hdrs = dict(BROWSER_HEADERS)
            hdrs["Referer"] = referer
            req = urllib.request.Request(url, headers=hdrs)
            with _opener().open(req, timeout=30) as r:
                text = r.read().decode("utf-8", "ignore")
            if _is_waf(text):
                last = "WAF 验证页"
                print("    [waf] %s，%.0fs 后重试" % (url, waf_wait), flush=True)
                time.sleep(waf_wait)
                continue
            return text
        except urllib.error.HTTPError as e:
            last = "HTTP %s" % e.code
            if e.code in (429, 500, 502, 503, 504):
                time.sleep(2.5 * (i + 1))
                continue
            break
        except Exception as e:  # noqa
            last = repr(e)
            time.sleep(1.5)
    print("  [fail] %s -> %s" % (url, last), flush=True)
    return None


def warmup():
    for u in (HUPU_WARM, "https://bbs.hupu.com/"):
        t = get(u, tries=2, waf_wait=8.0)
        if t:
            print("[ok] 预热成功（%s），Cookie=%s" % (u, [c.name for c in COOKIES]), flush=True)
            return True
        time.sleep(2.0)
    return bool(list(COOKIES))


def txt(s):
    s = re.sub(r"<!--.*?-->", "", s or "")
    s = re.sub(r"<br\s*/?>", "\n", s)
    s = re.sub(r"</p>", "\n", s)
    s = re.sub(r"<img[^>]*>", " [图] ", s)
    s = re.sub(r"<[^>]+>", "", s)
    s = _html.unescape(s)
    s = re.sub(r"[ \t\u00a0]+", " ", s)
    s = re.sub(r"\n\s*\n+", "\n", s)
    return s.strip()


def parse_list(h):
    out = []
    for m in re.finditer(r'<li class="bbs-sl-web-post-body">(.*?)</li>', h, re.S):
        blk = m.group(1)
        a = (re.search(r'<a href="/(\d+)\.html"[^>]*class="p-title"[^>]*>(.*?)</a>', blk, re.S)
             or re.search(r'class="p-title"[^>]*href="/(\d+)\.html"[^>]*>(.*?)</a>', blk, re.S))
        if not a:
            continue
        tid, title = a.group(1), txt(a.group(2))
        dm = re.search(r'<div class="post-datum">\s*(\d+)\s*/\s*(\d+)\s*</div>', blk)
        am = re.search(r'<div class="post-auth">(.*?)</div>', blk, re.S)
        tm = re.search(r'<div class="post-time">(.*?)</div>', blk, re.S)
        out.append({
            "tid": tid, "title": title, "url": "https://bbs.hupu.com/%s.html" % tid,
            "replies": int(dm.group(1)) if dm else None,
            "read": int(dm.group(2)) if dm else None,
            "author": txt(am.group(1)) if am else "",
            "time": txt(tm.group(1)) if tm else "",
            "lights": None,
        })
    return out


def _replies(seg):
    out = []
    for b in re.split(r'<div class="post-reply-list\s*">', seg)[1:]:
        b = b.split('<div class="post-reply-list ')[0]
        cm = re.findall(r'<div class="thread-content-detail">(.*?)</div>', b, re.S)
        c = txt(cm[-1]) if cm else ""
        if not c:
            continue
        au = re.search(r'class="post-reply-list-user-info-top-name"[^>]*>(.*?)</a>', b, re.S)
        nm = re.search(r'todo-list-text bold">亮了\(\s*(?:<!-- -->)?\s*(\d+)', b)
        out.append({"content": c, "light": int(nm.group(1)) if nm else 0,
                    "author": txt(au.group(1)) if au else ""})
    return out


def parse_thread(h, it):
    stat = {
        "replies": _num(h, r'class="index_reply__[^"]*">\s*(?:<!-- -->)?\s*(\d+)'),
        "lights": _num(h, r'class="index_light__[^"]*">\s*/\s*(?:<!-- -->)?\s*(\d+)'),
        "read": _num(h, r'class="index_read__[^"]*">\s*(?:<!-- -->)?\s*(\d+)'),
    }
    mt = re.search(r'<h1 class="index_name__[^"]*"[^>]*>(.*?)</h1>', h, re.S)
    mb = re.search(r'<div class="thread-content-detail">(.*?)</div>', h, re.S)

    li, ai = h.find("这些回帖亮了"), h.find("全部回帖")
    if li >= 0 and ai > li:
        light_seg, all_seg = h[li:ai], h[ai:]
    elif li >= 0:
        light_seg, all_seg = h[li:], h[li:]
    else:
        light_seg, all_seg = "", h

    lights = sorted(_replies(light_seg), key=lambda x: -x["light"])[:MAX_PER_LIST]
    cmts = _replies(all_seg)[:MAX_PER_LIST]
    for c in cmts:
        c["isStarter"] = bool(it.get("author") and c["author"] == it["author"])

    return {
        "tid": it["tid"],
        "title": (txt(mt.group(1)) if mt else "") or it["title"],
        "url": it["url"],
        "author": it["author"],
        "time": it["time"],
        "location": "",
        "stat": stat,
        "content": txt(mb.group(1)) if mb else "",
        "lights": lights,
        "comments": cmts,
        "commentTotal": stat.get("replies"),
    }


def _num(h, pat):
    m = re.search(pat, h)
    return int(m.group(1)) if m else None


def scrape():
    print("[1/3] 预热会话 …", flush=True)
    warmup()

    print("[2/3] 抓榜单 …", flush=True)
    h = get(HUPU_LIST)
    if not h:
        raise RuntimeError("榜单页抓取失败")
    lst = parse_list(h)
    print("[ok] 榜单条数=%d" % len(lst), flush=True)
    if len(lst) < MIN_LIST:
        raise RuntimeError("榜单条数异常(%d < %d)，疑似被 WAF 拦截或页面结构变更"
                           % (len(lst), MIN_LIST))

    print("[3/3] 抓前 %d 帖详情 …" % TOP_DETAIL, flush=True)
    threads, blocked = [], 0
    for idx, it in enumerate(lst):
        if idx:
            time.sleep(GAP + random.uniform(0, 0.4))
        th = get(it["url"], tries=2, waf_wait=12.0)
        if not th:
            blocked += 1
            continue
        d = parse_thread(th, it)
        # 用帖子页的官方统计回填榜单行
        s = d.get("stat") or {}
        if s.get("replies") is not None:
            it["replies"] = s["replies"]
        if s.get("read") is not None:
            it["read"] = s["read"]
        it["lights"] = s.get("lights")
        if idx < TOP_DETAIL:
            threads.append(d)
        if idx % 5 == 0 or idx == len(lst) - 1:
            print("  已抓 %d/%d" % (idx + 1, len(lst)), flush=True)

    if blocked:
        print("[warn] %d 帖未取到（被拦或失败），其亮评数留空" % blocked, flush=True)

    return {
        "source": HUPU_LIST,
        "topic": TOPIC,
        "updated": time.strftime("%Y-%m-%d %H:%M"),
        "total": len(lst),
        "listMeta": {"count": len(lst)},
        "list": lst,
        "threads": threads,
    }


def main():
    dry = "--dry" in sys.argv
    out = OUT
    if "--out" in sys.argv:
        out = sys.argv[sys.argv.index("--out") + 1]

    data = scrape()
    print("[ok] 榜单 %d 条 / 详情 %d 帖 / updated=%s"
          % (len(data["list"]), len(data["threads"]), data["updated"]), flush=True)

    if dry:
        print("[dry] 跳过写文件")
        return 0

    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    print("[saved] %s（%d 字节）" % (out, os.path.getsize(out)), flush=True)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:  # noqa
        print("失败: %s" % e, flush=True)
        sys.exit(1)
