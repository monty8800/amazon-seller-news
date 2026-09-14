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
紫鸟浏览器(ZClaw, 只读, 按站点母语抓取)
      ↓  fetch.py          抓取各站点 → data/news.json + data/history/YYYY-MM-DD.json
      │                              + data/raw/YYYY-MM-DD/<站点>.txt（原始页面证据，仅存本机）
      ↓  translate.py      AI 译为中文（DeepSeek，按内容哈希缓存，只翻新内容）
      ↓  build.py          渲染 → index.html（单文件，无外部依赖）
      ↓  run_daily.sh      git commit + push → GitHub Pages 自动更新
```

由 macOS **launchd** 每日定时执行（`com.monty.amazon-seller-news`）。

> **为什么脚本放在 `~/.agents/` 而不是 `~/Documents/`**：`~/Documents` 受 macOS TCC 保护，
> launchd 直接启动的脚本会被拒绝访问（`open() Operation not permitted`）。
> 放在 `~/.agents/` 下，定时任务就是普通 bash，**无需 TCC 包装器，也不依赖其他应用的安装路径**。

## 语言与翻译

**按站点抓母语原文，再统一译成中文，页面上「中文为主 + 原文可对照」。**

| 站点 | 抓取语言 | 实现 |
|---|---|---|
| 美国 / 英国 / 澳洲 | 英文 | `?mons_sel_locale=en_US / en_GB / en_AU` |
| 日本 | **日文** | `?mons_sel_locale=ja_JP` |
| 德国 | **德文** | `?mons_sel_locale=de_DE` |
| 阿联酋 | 站点默认语言 | ⚠️ **不强制** —— 见下 |

- **翻译**：`translate.py` 调 DeepSeek（Key 从 `~/.dsh/.credentials.yaml` 读，**不入库**）。
  以 `sha1(headline+summary)` 为键做**内容哈希缓存**（`data/translations.json`），
  **只有内容变了的条目才重新翻译**，避免每天为相同内容重复付费。
  已是中文原生的内容会跳过（标记 `zh_native`），不做「中文翻中文」。
- **页面上**：标题中文在上、原文小字在下；点「显示原文（日文/德文…）」展开该条原语言摘要。
  翻译失败或缺失的条目会**自动回退显示原文**，不会出现空白。

### ⚠️ 阿联酋站为什么不强制语言

实测 Amazon.ae 的卖家新闻**没有阿拉伯文版**（`ar_AE` 无内容）；
更关键的是**一旦给该站带上 `mons_sel_locale`（`ar_AE`/`en_US`/`en_GB` 都试过），
该页就取不到任何条目**（等 48 秒仍为 0 链接）。故 AE 留空、用账号默认语言（当前为中文）。

## ⚠️ 几个容易踩的坑（均实测得出）

### 1. 公开政策页必须用「没有该站点登录态」的店铺去取

`/help/hub/reference/external/...` 本是无须登录的公开页，但**如果所用紫鸟店铺恰好有该站点的登录态，
它会被重定向到登录版帮助中心，正文反而取不到**（表现为页面只剩导航）。

- ❌ 用有 DE 登录态的店铺取 DE 公开页 → 重定向、取不到正文
- ✅ 用只有 AE 登录态的店铺取 DE 公开页 → 正常拿到完整正文

所以 `fetch.py` 里 **DE 走 `SC-AE` 店铺**，US/JP/UK/AU 走 `SZB-US`。**改站点配置时务必留意这一条。**

### 2. `mons_sel_locale` 会持久化，必须恢复

该参数**会写进紫鸟店铺的语言偏好**。若不处理，每天跑任务就会把店铺界面语言改掉。
因此 `fetch.py` 每次运行结束会调 `restore_locale()` 把两个店铺恢复为**中文**。

### 3. 不能用固定 `sleep` 等页面 —— 各站渲染速度差异极大

实测 AE 站在 9 秒时文章链接数为 **0**、20 秒后才是 **20 条**；用固定 sleep 会产生
「明明有内容却抓到 0 条」的**假失败**。因此改为**轮询直到内容出现**
（`wait_for_count` / `wait_for_marker`，超时 60 秒）。

### 4. launchd 的默认 PATH 只有 `/usr/bin:/bin`

该环境下实测 **`ziniao-cli` 与 `gh` 都找不到**，且 `python3` 会落到**系统 3.9**。
因此 plist 里显式设置了 `EnvironmentVariables.PATH`，**`run_daily.sh` 内还再钉死一次并做前置自检**
（缺命令则 `exit 6` 并留痕），避免定时任务静默跑偏。

### 5. 让模型返回 JSON 时要容错键名

实测 DeepSeek 在 `json_object` 模式下，即使提示词要求 `headline_zh`/`summary_zh`，
有时仍会返回 `headline`/`summary` —— 解析器若只认前者，会把成功当失败。
`translate.py` 现在**两种键名都接受**。



## 抓取失败时的行为

- **绝不静默失败**：脚本在日志中留下可读错误，并以非零退出码结束。
- 单个站点失败 → 该站点在页面上标注「**沿用上次**」，并给出失败原因；其余站点照常更新。
- **全部站点失败** → 不发布，保留线上上一次的内容。
- 紫鸟客户端未就绪 → 会尝试唤起一次，仍失败则中止并留痕。
- **翻译部分失败** → 仍然发布（未译条目自动回退显示原文），但最终以 **exit 8** 结束并在日志中报出。

退出码：`0` 成功 ｜ `2` 紫鸟环境未就绪 ｜ `3` 全部站点抓取失败 ｜ `4` 构建失败
｜ `5` git 失败 ｜ `6` 环境缺命令 ｜ `7` 项目目录缺失 ｜ `8` 翻译有失败项（已发布）

运行日志：`logs/daily-YYYY-MM-DD.log`　｜　逐站点状态：`data/status.json`
翻译缓存：`data/translations.json`（只增不减，删掉会导致下次全量重译）

## 手动运行

```bash
bash ~/.agents/amazon-seller-news/run_daily.sh
```

## 免责声明

本项目**非 Amazon 官方项目**，与 Amazon 无关联。页面内容来自 Amazon 公开发布的页面，
仅作内部信息汇总参考；不构成任何官方声明或建议。
**中文译文由 AI 生成，可能存在偏差，以页面「显示原文」中的官方原文为准。**
页面视觉风格为自建，**未使用 Amazon 的任何 logo 或商标**。
