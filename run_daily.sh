#!/bin/bash
# =============================================================================
# 每日任务：抓取 → 生成站点 → 提交并推送到 GitHub（触发 GitHub Pages 更新）
#
# 设计原则（沿用本机既有教训）：
#   * 失败必须留痕 + 非零退出码，**绝不静默失败**（本机曾有定时任务连报 13 天"退出码 0"却没产出）。
#   * 不使用 2>/dev/null 吞错误。
#   * 本项目位于 ~/.agents 下（**不在 ~/Documents**），因此无需 macOS TCC 包装器，
#     也不依赖 DSH Desktop 的安装路径 —— 定时任务更不易碎。
#
# 退出码：0 成功 ｜ 2 紫鸟环境未就绪 ｜ 3 全部站点抓取失败 ｜ 4 构建失败 ｜ 5 git 失败
# =============================================================================
set -uo pipefail

PROJ="$HOME/.agents/amazon-seller-news"
LOG="$PROJ/logs/daily-$(date +%Y-%m-%d).log"
mkdir -p "$PROJ/logs"

say() { printf '%s  %s\n' "$(date '+%H:%M:%S')" "$*" | tee -a "$LOG"; }

cd "$PROJ" || { echo "无法进入项目目录 $PROJ" >&2; exit 1; }
say "===== 每日任务开始 ====="

# --- 1) 抓取 ---------------------------------------------------------------
python3 -u fetch.py >>"$LOG" 2>&1
rc=$?
if [ "$rc" -ne 0 ]; then
  say "抓取失败（exit=$rc）——不发布，保留上次线上内容。详见 $LOG"
  exit "$rc"
fi

# --- 2) 生成站点 -----------------------------------------------------------
python3 build.py >>"$LOG" 2>&1
if [ $? -ne 0 ]; then
  say "站点生成失败——不发布"
  exit 4
fi
say "站点已重新生成"

# --- 3) 提交并推送 ---------------------------------------------------------
# 内容无变化时不产生空提交
if git diff --quiet && git diff --cached --quiet && [ -z "$(git status --porcelain)" ]; then
  say "内容无变化，跳过提交"
  exit 0
fi

git add -A >>"$LOG" 2>&1
git commit -m "每日更新：亚马逊各站点新闻与规则（$(date +%Y-%m-%d)）" >>"$LOG" 2>&1
if [ $? -ne 0 ]; then
  say "git commit 失败"
  exit 5
fi

# 限制重试次数，避免卡死；网络问题会在日志里留痕
for i in 1 2 3; do
  if git push origin HEAD >>"$LOG" 2>&1; then
    say "推送成功（第 $i 次尝试）"
    say "线上地址：https://monty8800.github.io/amazon-seller-news/"
    say "===== 完成 ====="
    exit 0
  fi
  say "推送失败，第 $i 次重试…"
  sleep 10
done

say "推送连续 3 次失败——本地已提交，等待下次运行重试"
exit 5
