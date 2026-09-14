# amazon-seller-news

> 亚马逊各站点**官方新闻与规则变更**的每日看板 —— 自动抓取、自动发布。
>
> 🌐 线上地址：**https://monty8800.github.io/amazon-seller-news/**

## 这是什么

每天自动抓取 Amazon 卖家平台的公开信息，汇总成一个静态页面：

| 站点 | 数据源 | 需要登录 |
|---|---|---|
| 美国 US / 日本 JP / 阿联酋 AE | Seller Central **卖家新闻** `/seller-news/articles` | ✅ 需要 |
| 英国 UK / 德国 DE / 澳洲 AU | Amazon **计划政策变更**页 `/help/hub/reference/external/GQHQGBTD7XB7EECN` | ❌ 公开 |

**页面只包含 Amazon 公开发布的新闻与政策变更**，不含任何店铺名、账号、账户状况或其他业务信息。

## 自动化流程

```
紫鸟浏览器(ZClaw, 只读)
      ↓  fetch.py          抓取各站点 → data/news.json + data/history/YYYY-MM-DD.json
      ↓  build.py          渲染 → index.html（单文件，无外部依赖）
      ↓  run_daily.sh      git commit + push → GitHub Pages 自动更新
```

由 macOS **launchd** 每日定时执行（`com.monty.amazon-seller-news`）。

> **为什么脚本放在 `~/.agents/` 而不是 `~/Documents/`**：`~/Documents` 受 macOS TCC 保护，
> launchd 直接启动的脚本会被拒绝访问（`open() Operation not permitted`）。
> 放在 `~/.agents/` 下，定时任务就是普通 bash，**无需 TCC 包装器，也不依赖其他应用的安装路径**。

## 抓取失败时的行为

- **绝不静默失败**：脚本在日志中留下可读错误，并以非零退出码结束。
- 单个站点失败 → 该站点在页面上标注「**沿用上次**」，并给出失败原因；其余站点照常更新。
- **全部站点失败** → 不发布，保留线上上一次的内容。
- 紫鸟客户端未就绪 → 会尝试唤起一次，仍失败则中止并留痕。

运行日志：`logs/daily-YYYY-MM-DD.log`　｜　逐站点状态：`data/status.json`

## 手动运行

```bash
bash ~/.agents/amazon-seller-news/run_daily.sh
```

## 免责声明

本项目**非 Amazon 官方项目**，与 Amazon 无关联。页面内容来自 Amazon 公开发布的页面，
仅作内部信息汇总参考；不构成任何官方声明或建议。
页面视觉风格为自建，**未使用 Amazon 的任何 logo 或商标**。
