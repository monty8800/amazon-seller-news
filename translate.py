#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
把各站点母语内容用 AI 翻译成中文（简体），带内容哈希缓存。

为什么要缓存：每天运行都会重复抓到大部分相同文章。用 `sha1(headline+summary)` 做键，
**只有内容变了的才重新翻译**，避免每天为同样的内容重复付费。

翻译后端：DeepSeek（OpenAI 兼容接口）。Key 从 ~/.dsh/.credentials.yaml 读取，**不落进仓库**。
  可用环境变量覆盖：DEEPSEEK_API_KEY / DEEPSEEK_BASE_URL / DEEPSEEK_MODEL

设计：
  * 已是中文的内容**跳过翻译**（标注 zh_native），既省费用也避免"中文翻中文"变味。
  * 单条失败不影响其余：逐条留痕，最后汇总。
  * 结果写回 data/news.json（新增 headline_zh / summary_zh / zh_native 字段）。
"""
import hashlib
import json
import os
import re
import sys
import time
import urllib.request
import urllib.error
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
CACHE = DATA / "translations.json"
NEWS = DATA / "news.json"

CRED = Path.home() / ".dsh" / ".credentials.yaml"
BATCH = 6          # 每次请求翻译的文章数
MAX_SUMMARY = 900  # 送入翻译的摘要字符上限（控制成本）
TIMEOUT = 120


def log(m):
    print(m, flush=True)


def read_key():
    k = os.environ.get("DEEPSEEK_API_KEY")
    if k:
        return k.strip()
    try:
        t = CRED.read_text(encoding="utf-8", errors="replace")
    except Exception as e:
        log("ERROR 无法读取凭证文件 %s: %s" % (CRED, e))
        return ""
    m = re.search(r"^\s*DEEPSEEK_API_KEY\s*:\s*[\"']?([^\"'\s]+)", t, re.M)
    return m.group(1) if m else ""


def is_chinese(s, thresh=0.30):
    """判断文本是否已以中文为主（据此跳过翻译）。"""
    if not s:
        return False
    cjk = sum(1 for c in s if "\u4e00" <= c <= "\u9fff")
    letters = sum(1 for c in s if c.isalpha())
    return letters > 0 and cjk / max(letters, 1) >= thresh


def call_llm(key, model, base, items):
    """items: [{"headline":..,"summary":..}] → 返回同长度的译文字典列表。"""
    payload_items = []
    for i, it in enumerate(items):
        payload_items.append({"i": i, "headline": it["headline"], "summary": it["summary"][:MAX_SUMMARY]})
    sys_p = (
        "你是跨境电商资深运营，负责把亚马逊各站点的官方公告准确翻译成简体中文。"
        "要求：1) 忠实原文，不要添加解释或评价；2) 保留政策名称、日期、数字、金额、百分比、"
        "功能名称与专有名词的准确性，必要时在括号内保留英文原名；3) 语气用商务书面语；"
        "4) 只输出一个 JSON 对象，形如 "
        "{\"items\":[{\"i\":0,\"headline_zh\":\"...\",\"summary_zh\":\"...\"}]}，"
        "不要输出任何其他文字、不要用 markdown 代码块包裹。"
    )
    usr_p = "请翻译以下 %d 条亚马逊公告（来自不同站点，语言可能为英文/日文/德文），按 i 对应返回：\n%s" % (
        len(payload_items), json.dumps(payload_items, ensure_ascii=False))
    body = json.dumps({
        "model": model,
        "messages": [{"role": "system", "content": sys_p}, {"role": "user", "content": usr_p}],
        "temperature": 0.2,
        "response_format": {"type": "json_object"},
    }).encode("utf-8")
    req = urllib.request.Request(base.rstrip("/") + "/chat/completions", data=body, headers={
        "Content-Type": "application/json",
        "Authorization": "Bearer " + key,
    })
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        d = json.loads(r.read().decode("utf-8"))
    txt = d["choices"][0]["message"]["content"].strip()
    # 兼容模型可能包一层对象的情况
    try:
        arr = json.loads(txt)
    except Exception:
        m = re.search(r"\[[\s\S]*\]", txt)
        if not m:
            raise RuntimeError("模型返回无法解析为 JSON: %s" % txt[:200])
        arr = json.loads(m.group(0))
    if isinstance(arr, dict):
        arr = arr.get("items") or arr.get("translations") or arr.get("data") or []
    out = {}
    for o in arr:
        if not isinstance(o, dict):
            continue
        try:
            i = int(o.get("i", o.get("index")))
        except Exception:
            continue
        # 实测：模型有时会返回 headline/summary 而非要求的 headline_zh/summary_zh，
        # 因此两种键名都要接受 —— 否则会被误判成「翻译失败」。
        h = (o.get("headline_zh") or o.get("headline") or o.get("headline_zh_cn") or "").strip()
        s = (o.get("summary_zh") or o.get("summary") or o.get("summary_zh_cn") or "").strip()
        out[i] = (h, s)
    return out


def main():
    if not NEWS.exists():
        log("ERROR 缺少 data/news.json，先运行 fetch.py")
        return 1
    data = json.loads(NEWS.read_text(encoding="utf-8"))
    cache = {}
    if CACHE.exists():
        try:
            cache = json.loads(CACHE.read_text(encoding="utf-8"))
        except Exception:
            cache = {}

    key = read_key()
    base = os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
    model = os.environ.get("DEEPSEEK_MODEL", "deepseek-chat")
    if not key:
        log("ERROR 未找到 DEEPSEEK_API_KEY（~/.dsh/.credentials.yaml 或环境变量）")

    todo = []          # (site, idx, hash, article)
    for site, v in data.get("sites", {}).items():
        for idx, a in enumerate(v.get("articles") or []):
            h = (a.get("headline") or "").strip()
            s = (a.get("summary") or "").strip()
            if not h:
                continue
            key_h = hashlib.sha1((h + "||" + s).encode("utf-8")).hexdigest()
            a["_h"] = key_h
            if is_chinese(h) and is_chinese(s, 0.2):
                a["headline_zh"] = h
                a["summary_zh"] = s[:MAX_SUMMARY]
                a["zh_native"] = True
                continue
            a["zh_native"] = False
            if key_h in cache:
                a["headline_zh"] = cache[key_h].get("headline_zh", "")
                a["summary_zh"] = cache[key_h].get("summary_zh", "")
            else:
                todo.append((site, idx, key_h, a))

    log("待翻译 %d 条（缓存命中 %d 条，中文原生跳过 %d 条）" % (
        len(todo), sum(1 for v in data["sites"].values() for a in (v.get("articles") or []) if a.get("headline_zh") and not a.get("zh_native")),
        sum(1 for v in data["sites"].values() for a in (v.get("articles") or []) if a.get("zh_native"))))

    failed = 0
    if todo and key:
        for i in range(0, len(todo), BATCH):
            chunk = todo[i:i + BATCH]
            items = [{"headline": c[3]["headline"], "summary": c[3].get("summary", "")} for c in chunk]
            ok = False
            for attempt in (1, 2, 3):
                try:
                    res = call_llm(key, model, base, items)
                    for j, (site, idx, kh, a) in enumerate(chunk):
                        if j in res and res[j][0]:
                            a["headline_zh"], a["summary_zh"] = res[j]
                            cache[kh] = {"headline_zh": res[j][0], "summary_zh": res[j][1],
                                         "model": model, "at": time.strftime("%Y-%m-%d %H:%M:%S")}
                        else:
                            failed += 1
                    ok = True
                    break
                except urllib.error.HTTPError as e:
                    log("  批次 %d 第 %d 次失败：HTTP %s %s" % (i // BATCH + 1, attempt, e.code,
                                                              e.read()[:180].decode("utf-8", "replace")))
                except Exception as e:
                    log("  批次 %d 第 %d 次失败：%s" % (i // BATCH + 1, attempt, e))
                time.sleep(4)
            if not ok:
                failed += len(chunk)
            else:
                log("  已完成 %d/%d" % (min(i + BATCH, len(todo)), len(todo)))
    elif todo:
        failed = len(todo)

    # 清理临时字段
    for v in data.get("sites", {}).values():
        for a in (v.get("articles") or []):
            a.pop("_h", None)

    CACHE.write_text(json.dumps(cache, ensure_ascii=False, indent=1), encoding="utf-8")
    data["translated_at"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    data["translate_failed"] = failed
    NEWS.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    total = sum(len(v.get("articles") or []) for v in data["sites"].values())
    have = sum(1 for v in data["sites"].values() for a in (v.get("articles") or []) if a.get("headline_zh"))
    log("翻译完成：%d/%d 条有中文（失败 %d 条）；缓存条目 %d" % (have, total, failed, len(cache)))
    return 8 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
