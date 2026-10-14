# -*- coding: utf-8 -*-
"""
merge_basketball_logos.py —— 仅供 GitHub Actions 自动刷新用。

背景：basketball.py 在本地会用 WorkBuddy 客户端内部的图片上传脚本，
把队徽/背景图转存到 workbuddy-space-static 图床，得到稳定 URL。
但在 GitHub Actions（Linux runner）上该上传脚本不存在，subprocess 调用会失败，
导致 assets/basketball.json 里的 logos / bg / porLogo / player.photo 为空。

本脚本在 basketball.py 跑完之后执行：
  1. 读取刚生成的 assets/basketball.json（赛程/赛果/新闻是最新的，但图片字段可能为空）
  2. 拉取线上快照里已有的 basketball 字段
  3. 仅当「新数据为空、旧快照有值」时，把稳定的图片字段回填（不覆盖任何赛程/新闻数据）
  4. 写回 assets/basketball.json，供随后 refresh_snapshot.py 合并进每日快照

纯标准库，无需第三方依赖，无需任何密钥。
"""
import json
import os
import ssl
import urllib.request

CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE

SNAP = "https://textdb.dev/api/data/wb-c7d2f4a91b6e3805fa2d1c74e9b8a603"
ROOT = os.path.dirname(os.path.abspath(__file__))
BB_PATH = os.path.join(ROOT, "assets", "basketball.json")


def main():
    if not os.path.exists(BB_PATH):
        print("[skip] 未找到 %s，跳过回填" % BB_PATH)
        return

    with open(BB_PATH, encoding="utf-8") as f:
        bb = json.load(f)

    try:
        req = urllib.request.Request(SNAP, headers={"User-Agent": "Mozilla/5.0"})
        cur = json.loads(urllib.request.urlopen(req, timeout=30, context=CTX)
                         .read().decode("utf-8", "ignore"))
        old = cur.get("basketball") or {}
        print("[ok] 已读取线上快照篮球字段")
    except Exception as e:
        print("[warn] 读取线上快照失败，跳过回填: %s" % str(e)[:80])
        return

    changed = False

    # 队徽字典：key（球队缩写）一致，线上有的就回填
    if not bb.get("logos") and old.get("logos"):
        bb["logos"] = old["logos"]
        changed = True
        print("[ok] 回填队徽 %d 个" % len(old["logos"]))

    if not bb.get("bg") and old.get("bg"):
        bb["bg"] = old["bg"]
        changed = True
        print("[ok] 回填背景图")

    if not bb.get("porLogo") and old.get("porLogo"):
        bb["porLogo"] = old["porLogo"]
        changed = True
        print("[ok] 回填开拓者队徽")

    pp = bb.get("player") or {}
    opp = old.get("player") or {}
    if isinstance(pp, dict) and isinstance(opp, dict) and not pp.get("photo") and opp.get("photo"):
        pp["photo"] = opp["photo"]
        bb["player"] = pp
        changed = True
        print("[ok] 回填球员照片")

    if changed:
        with open(BB_PATH, "w", encoding="utf-8") as f:
            json.dump(bb, f, ensure_ascii=False, indent=1)
        print("[saved] 已回填图片字段并写回 %s" % BB_PATH)
    else:
        print("[ok] 无需回填（图片字段已存在或线上也无）")


if __name__ == "__main__":
    main()
