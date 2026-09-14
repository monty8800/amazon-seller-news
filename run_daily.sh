#!/bin/bash
# =============================================================================
# 每日任务：抓取 → 生成站点 → 提交并推送到 GitHub（GitHub Pages 随之更新）
#
# 设计原则（沿用本机既有教训）：
#   * 失败必须留痕 + 非零退出码，**绝不静默失败**
#     （本机曾有定时任务连续 13 天报「退出码 0」却毫无产出）。
#   * 不使用 2>/dev/null 吞掉错误。
#   * 本项目位于 ~/.agents 下（**不在 ~/Documents**），故无需 macOS TCC 包装器，
#     也不依赖 DSH Desktop 的安装路径 —— 定时任务更不易碎。
#   * launchd 的默认 PATH 只有 /usr/bin:/bin，**ziniao-cli 与 gh 都不在其中**，
#     且 python3 会落到系统 3.9；因此本脚本显式钉死 PATH 并做前置自检。
#
# 退出码：0 成功 ｜ 2 紫鸟环境未就绪 ｜ 3 全部站点抓取失败 ｜ 4 构建失败
#         ｜ 5 git 失败 ｜ 6 环境缺命令 ｜ 7 项目目录缺失
# =============================================================================
set -uo pipefail

PROJ="$HOME/.agents/amazon-seller-news"
LOGDIR="$PROJ/logs"
LOG="$LOGDIR/daily-$(date +%Y-%m-%d).log"

[ -d "$PROJ" ] || { echo "ERROR 项目目录不存在：$PROJ" >&2; exit 7; }
mkdir -p "$LOGDIR" || { echo "ERROR 无法创建日志目录 $LOGDIR" >&2; exit 6; }

say() { printf '%s  %s\n' "$(date '+%H:%M:%S')" "$*" | tee -a "$LOG"; }

# --- 0) 环境前置自检 -------------------------------------------------------
export PATH="/opt/homebrew/bin:/Library/Frameworks/Python.framework/Versions/3.13/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
MISSING=""
for c in python3 ziniao-cli git gh; do
  command -v "$c" >/dev/null 2>&1 || MISSING="$MISSING $c"
done
if [ -n "$MISSING" ]; then
  say "ERROR 缺少必要命令:$MISSING（当前 PATH=$PATH）——中止，不做任何改动"
  exit 6
fi
say "===== 每日任务开始（python3 $(python3 -V 2>&1 | awk '{print $2}')）====="

cd "$PROJ" || { say "ERROR 无法进入 $PROJ"; exit 7; }

# --- 1) 抓取 ---------------------------------------------------------------
python3 -u fetch.py >>"$LOG" 2>&1
rc=$?
if [ "$rc" -ne 0 ]; then
  say "抓取失败（exit=$rc）—— 不发布，线上保留上一次内容。详见 $LOG"
  exit "$rc"
fi

# --- 2) AI 翻译（带内容哈希缓存，只翻新内容，省费用）------------------------
python3 -u translate.py >>"$LOG" 2>&1
TRANSLATE_RC=$?
if [ "$TRANSLATE_RC" -eq 0 ]; then
  say "翻译完成（全部成功）"
else
  say "翻译部分失败（exit=$TRANSLATE_RC）—— 仍继续发布，未译条目会自动回退显示原文；详见 $LOG"
fi

# --- 3) 生成站点 -----------------------------------------------------------
python3 build.py >>"$LOG" 2>&1
if [ $? -ne 0 ]; then
  say "站点生成失败 —— 不发布"
  exit 4
fi
say "站点已重新生成：index.html"

# --- 4) 无变化则不产生空提交 ----------------------------------------------
if [ -z "$(git status --porcelain)" ]; then
  say "内容无变化，跳过提交与推送"
  say "===== 完成（无变更）====="
  exit 0
fi

git add -A >>"$LOG" 2>&1
if ! git commit -m "每日更新：亚马逊各站点新闻与规则（$(date +%Y-%m-%d)）" >>"$LOG" 2>&1; then
  say "git commit 失败"
  exit 5
fi

# --- 5) 推送（有限重试，避免卡死）------------------------------------------
for i in 1 2 3; do
  if git push origin HEAD >>"$LOG" 2>&1; then
    say "推送成功（第 $i 次尝试）"
    say "线上地址：https://monty8800.github.io/amazon-seller-news/"
    if [ "$TRANSLATE_RC" -ne 0 ]; then
      say "===== 完成（但翻译有失败项，见上）====="
      exit 8
    fi
    say "===== 完成 ====="
    exit 0
  fi
  say "推送失败，第 $i 次重试…"
  sleep 10
done

say "推送连续 3 次失败 —— 本地已提交，等下次运行会重试"
exit 5
