# 工作台每日快照自动刷新（GitHub Actions）

把「全网舆情 + 篮球数据」的刷新从「手动喊一声」变成「每天自动跑」，无需本地开电脑。

数据源：`refresh_snapshot.py` / `basketball.py` 抓取后写入 textdb 快照，工作台页面直接读取该快照。

## 这个仓库包含什么

- `refresh_snapshot.py` —— 抓取 60s 要闻 / AI 简报 / 微博 / 百度 / 知乎 热榜，生成 `opinion` 舆情字段，并合并篮球数据，POST 整份快照。
- `basketball.py` —— 从 ESPN 官方 API 抓杨瀚森/开拓者赛程、赛果、新闻，写出 `assets/basketball.json`。
- `merge_basketball_logos.py` —— **仅用于云端自动化**：本地客户端能把队徽转存到图床得到 URL，但 GitHub 的 Linux runner 上没有这个上传脚本，队徽字段会为空；本脚本用线上快照里已有的稳定图片字段（logos/bg/porLogo/球员照）回填，避免刷新后图片变空。
- `.github/workflows/daily-refresh.yml` —— 每天 23:00 UTC（北京 07:00）自动执行上面的三步；也支持在 Actions 页面手动触发。

无需任何第三方依赖（全是 Python 标准库），无需任何密钥（textdb 快照为免密读写）。

## 部署步骤（一次性）

1. 在 GitHub 新建一个**私有**仓库（例如 `workbench-daily-refresh`）。
2. 把本文件夹全部内容（含 `.github/`）推上去：
   ```bash
   cd wb_github_actions
   git init
   git add .
   git commit -m "init: 每日舆情+篮球自动刷新"
   git branch -M main
   git remote add origin https://github.com/<你的用户名>/<仓库名>.git
   git push -u origin main
   ```
3. 打开仓库的 **Actions** 标签页，启用 Workflow（首次推送后默认可能需点一下 "I understand..." 启用）。
4. 之后每天北京 07:00 自动刷新；想立刻看效果，去 Actions 页面点 **Run workflow** 手动触发一次。

## 验证

本地也可直接复现云端逻辑（需本机装了 WorkBuddy 客户端才有队徽上传，否则队徽为空但脚本不崩）：

```bash
python basketball.py
python merge_basketball_logos.py
python refresh_snapshot.py
```

## 注意事项

- 虎扑热榜（`hupu.py`）未纳入自动刷新：本仓的 `refresh_snapshot.py` 在找不到 `assets/hupu.json` 时会**沿用线上旧数据**，不会清空。如需每日刷新虎扑，把 `hupu.py` 也加进仓库并在 workflow 里 `basketball.py` 之前跑一步 `python hupu.py` 即可。
- 若日后改了 `refresh_snapshot.py` / `basketball.py`，请在本仓库里改并推送，云端才会用新版。本仓库是自动化脚本的「唯一真源」。
- 想改刷新时间：编辑 `daily-refresh.yml` 里的 `cron`（注意是 UTC）。
