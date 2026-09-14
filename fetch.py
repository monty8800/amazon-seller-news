#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
抓取亚马逊各站点官方新闻与政策变更 —— 供每日自动化使用。

数据源（全部为 Amazon 官方页面）：
  A) 卖家新闻（需登录）：/<域名>/seller-news/articles
  B) 公开政策变更页（无需登录）：/<域名>/help/hub/reference/external/GQHQGBTD7XB7EECN

设计要点：
  * 只读：仅 page visit + page exec 读 innerText，不点击、不提交。
  * 部分失败不致命：任一站点失败时保留上一次的数据并标注 stale，整体仍产出。
  * 状态文件 data/status.json 记录每个站点的成功/失败与错误，供页面上展示与排障。
  * 上次数据暂存 data/news.json；同时按日期归档 data/history/YYYY-MM-DD.json。
"""
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
DATA.mkdir(exist_ok=True)
(DATA / "history").mkdir(exist_ok=True)

TZ = timezone(timedelta(hours=8))

# 站点配置： key, 显示名, 类型, URL, 紫鸟店铺ID
SITES = [
    ("US", "美国站",   "seller-news", "https://sellercentral.amazon.com/seller-news/articles",            "16395388697429"),
    ("JP", "日本站",   "seller-news", "https://sellercentral-japan.amazon.com/seller-news/articles",      "16395388697429"),
    ("AE", "阿联酋站", "seller-news", "https://sellercentral.amazon.ae/seller-news/articles",             "27151611622883"),
    ("UK", "英国站",   "policy",      "https://sellercentral.amazon.co.uk/help/hub/reference/external/GQHQGBTD7XB7EECN", "16395388697429"),
    ("DE", "德国站",   "policy",      "https://sellercentral.amazon.de/help/hub/reference/external/GQHQGBTD7XB7EECN",    "16395388697429"),
    ("AU", "澳洲站",   "policy",      "https://sellercentral.amazon.com.au/help/hub/reference/external/GQHQGBTD7XB7EECN", "16395388697429"),
]

DATE_EN = re.compile(r"^[A-Z][a-z]{2}\s+\d{1,2},\s+\d{4}$")
DATE_CN = re.compile(r"^\d{4}年\d{1,2}月\d{1,2}日$")
MON = {m: i + 1 for i, m in enumerate(
    ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"])}


def log(msg):
    print("%s  %s" % (datetime.now(TZ).strftime("%H:%M:%S"), msg), flush=True)


def run(args, timeout=240):
    try:
        p = subprocess.run(["ziniao-cli"] + args, capture_output=True, text=True, timeout=timeout)
        return p.returncode, p.stdout, p.stderr
    except subprocess.TimeoutExpired:
        return 124, "", "TIMEOUT"
    except Exception as e:
        return 125, "", str(e)


def js(store_id, script, timeout=240):
    rc, out, err = run(["page", "exec", "--store-id", store_id, "--script", script], timeout)
    try:
        d = json.loads(out)
    except Exception:
        return None
    return (d.get("data") or {}).get("data", {}).get("result") if d.get("ok") else None


def iso_date(s):
    """把 'Sep 11, 2026' / '2026年9月10日' / '27 July 2026' 归一为 ISO。"""
    if not s:
        return ""
    m = re.match(r"^([A-Z][a-z]{2})\s+(\d{1,2}),\s+(\d{4})$", s)
    if m and m.group(1) in MON:
        return "%s-%02d-%02d" % (m.group(3), MON[m.group(1)], int(m.group(2)))
    m = re.match(r"^(\d{4})年(\d{1,2})月(\d{1,2})日$", s)
    if m:
        return "%s-%02d-%02d" % (m.group(1), int(m.group(2)), int(m.group(3)))
    m = re.match(r"^(\d{1,2})\s+([A-Z][a-z]+)\s+(\d{4})$", s)
    if m:
        mon = m.group(2)[:3]
        if mon in MON:
            return "%s-%02d-%02d" % (m.group(3), MON[mon], int(m.group(1)))
    return ""


# ---------------------------------------------------------------- 卖家新闻
CARD_JS = r"""
(function(){
  var out=[];
  Array.from(document.querySelectorAll('a[href*="/seller-news/articles/"]')).forEach(function(a){
    var t=(a.innerText||'').replace(/\r/g,'').trim();
    if(!t) return;
    var m=(a.getAttribute('href')||'').match(/articles\/([A-Za-z0-9]+)/);
    out.push({id:m?m[1]:'', lines:t.split('\n').map(function(s){return s.trim()}).filter(Boolean)});
  });
  return JSON.stringify(out);
})()
"""


def fetch_seller_news(store, url):
    run(["page", "visit", "--store-id", store, "--url", url,
         "--wait-until", "networkidle", "--timeout", "60000"], timeout=240)
    time.sleep(9)
    path = js(store, "location.pathname") or ""
    if "signin" in path:
        return None, "需要登录（跳转到 %s）" % path
    raw = js(store, CARD_JS)
    if not raw:
        return None, "未取到文章列表（path=%s）" % path
    try:
        cards = json.loads(raw)
    except Exception as e:
        return None, "JSON 解析失败: %s" % e
    # 用页面全文补日期
    body = js(store, "document.body.innerText.replace(/\\n{2,}/g,'\\n')") or ""
    lines = [l.strip() for l in body.split("\n")]
    arts = []
    for c in cards:
        ls = c["lines"]
        if not ls:
            continue
        head = ls[0]
        pos = next((i for i, l in enumerate(lines) if l.startswith(head[:40])), None)
        date = ""
        if pos is not None:
            for j in range(pos, min(pos + 120, len(lines))):
                if DATE_EN.match(lines[j]) or DATE_CN.match(lines[j]):
                    date = lines[j]
                    break
        body_txt = " ".join(l for l in ls[1:]
                            if not DATE_EN.match(l) and not DATE_CN.match(l)
                            and not re.match(r"^[\d.,]+K?\s*(views|次浏览)$", l)
                            and not re.match(r"^\d+\s*(likes|次点赞)$", l))
        arts.append({"headline": head, "date": date, "date_iso": iso_date(date),
                     "summary": body_txt[:1200], "id": c["id"]})
    if not arts:
        return None, "解析后 0 条"
    return arts, None


# ---------------------------------------------------------------- 政策变更页
POLICY_JS = r"""
(function(){
  var t=document.body.innerText.replace(/\n{2,}/g,'\n');
  if(t.indexOf('Listed below')<0 && t.indexOf('listed below')<0 && t.indexOf('计划政策变更')<0) return null;
  return t;
})()
"""


def fetch_policy(store, url):
    run(["page", "visit", "--store-id", store, "--url", url,
         "--wait-until", "networkidle", "--timeout", "60000"], timeout=240)
    time.sleep(9)
    body = js(store, POLICY_JS)
    if not body:
        path = js(store, "location.pathname") or "?"
        return None, "未取到政策正文（path=%s，可能被重定向到登录版）" % path
    lines = [l.strip() for l in body.split("\n")]
    starts = [i for i, l in enumerate(lines)
              if re.match(r"^(On|Effective as of|Effective from|Effective)\s+\d{1,2}\s+[A-Za-z]+\s*,?\s*\d{4}", l)]
    arts = []
    for i in starts:
        m = re.match(r"^(?:On|Effective as of|Effective from|Effective)\s+(\d{1,2}\s+[A-Za-z]+,?\s*\d{4})", lines[i])
        date = m.group(1).replace(",", "") if m else ""
        title = ""
        for j in range(i - 1, max(0, i - 6), -1):
            if lines[j] and len(lines[j]) < 120 and not lines[j].endswith("."):
                title = lines[j]
                break
        arts.append({"headline": title or "(未识别标题)", "date": date, "date_iso": iso_date(date),
                     "summary": " ".join(lines[i:i + 8])[:1200], "id": ""})
    if not arts:
        return None, "页面上未找到政策变更条目"
    return arts, None


# ---------------------------------------------------------------- ZClaw 就绪检查
def ensure_ready():
    rc, out, err = run(["doctor"], timeout=180)
    txt = out + err
    if "全部检查通过" in txt:
        log("ZClaw 就绪检查：通过")
        return True
    log("ZClaw 就绪检查未通过，尝试唤起紫鸟客户端…")
    if os.path.isdir("/Applications/ziniao.app"):
        subprocess.run(["open", "-a", "/Applications/ziniao.app"], capture_output=True)
        for _ in range(6):
            time.sleep(5)
            rc, out, err = run(["doctor"], timeout=180)
            if "全部检查通过" in (out + err):
                log("唤起客户端后检查通过")
                return True
    log("ZClaw 仍未就绪。doctor 摘要：")
    for line in (out + err).splitlines():
        if "✓" not in line:
            log("   " + line)
    return False


def main():
    now = datetime.now(TZ)
    prev = {}
    if (DATA / "news.json").exists():
        try:
            prev = json.loads((DATA / "news.json").read_text(encoding="utf-8")).get("sites", {})
        except Exception:
            prev = {}

    status = {"started_at": now.isoformat(), "ready": False, "sites": {}}
    if not ensure_ready():
        status["error"] = "ZClaw/紫鸟客户端未就绪"
        (DATA / "status.json").write_text(json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8")
        log("中止：紫鸟环境未就绪（不产出空数据，保留上次结果）")
        return 2

    status["ready"] = True
    sites = {}
    failures = 0
    for key, label, kind, url, store in SITES:
        log("[%s] %s" % (key, url))
        try:
            arts, err = (fetch_seller_news(store, url) if kind == "seller-news"
                         else fetch_policy(store, url))
        except Exception as e:
            arts, err = None, "异常: %s" % e
        if arts:
            sites[key] = {"label": label, "kind": kind, "url": url, "ok": True,
                          "fetched_at": now.isoformat(), "stale": False,
                          "count": len(arts), "articles": arts}
            log("     ✓ %d 条" % len(arts))
        else:
            failures += 1
            old = prev.get(key) or {}
            sites[key] = {"label": label, "kind": kind, "url": url, "ok": False,
                          "fetched_at": now.isoformat(), "stale": bool(old.get("articles")),
                          "error": err, "count": old.get("count", 0),
                          "articles": old.get("articles", [])}
            log("     ✗ %s（%s）" % (err, "沿用上次数据" if old.get("articles") else "无历史数据"))
        status["sites"][key] = {"ok": sites[key]["ok"], "count": sites[key]["count"],
                                "error": sites[key].get("error"), "stale": sites[key]["stale"]}

    payload = {"generated_at": now.isoformat(), "date": now.strftime("%Y-%m-%d"),
               "sites": sites}
    (DATA / "news.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    (DATA / "history" / ("%s.json" % now.strftime("%Y-%m-%d"))).write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    ok = sum(1 for s in sites.values() if s["ok"])
    status["finished_at"] = datetime.now(TZ).isoformat()
    status["ok_sites"] = ok
    status["total_sites"] = len(SITES)
    (DATA / "status.json").write_text(json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8")
    log("完成：%d/%d 站成功" % (ok, len(SITES)))

    # 全部失败则视为运行失败（避免把空站点当成成功发布）
    if ok == 0:
        log("全部站点抓取失败 —— 以非零码退出，不发布")
        return 3
    return 0


if __name__ == "__main__":
    sys.exit(main())
