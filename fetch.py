#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
抓取亚马逊各站点官方新闻与政策变更（母语版）—— 供每日自动化使用。

数据源（全部为 Amazon 官方页面）：
  A) 卖家新闻（需登录）：/<域名>/seller-news/articles
  B) 公开政策变更页（无需登录）：/<域名>/help/hub/reference/external/GQHQGBTD7XB7EECN

语言策略（用户要求「什么站点就拉什么语言」）：
  用 `?mons_sel_locale=<locale>` 强制各站点返回其**母语版本**
  （US/UK/AU=英文、JP=日文、DE=德文、AE=阿拉伯文），中文翻译交给 translate.py。

⚠️ 两个必须知道的坑（均实测）：
  1) `mons_sel_locale` 会**持久化到该紫鸟店铺的语言偏好**，因此每次运行结束会把店铺语言恢复为中文，
     避免每天跑任务把店铺界面语言改掉（见 restore_locale）。
  2) 公开政策页要用「**没有该站点登录态**」的店铺去取：若所用店铺恰好有该站点登录态，
     会被重定向到登录版帮助中心、正文反而取不到（故 DE 走 SC-AE、其余走 SZB-US）。

设计要点：只读（page visit + page exec）；部分站点失败不致命（保留上次数据并标注 stale）；
状态写入 data/status.json；原始正文按日存档 data/raw/YYYY-MM-DD/（仅存本机）。
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

# key, 显示名, 类型, URL, 紫鸟店铺ID, 母语 locale
SITES = [
    ("US", "美国站",   "seller-news", "https://sellercentral.amazon.com/seller-news/articles",            "16395388697429", "en_US"),
    ("JP", "日本站",   "seller-news", "https://sellercentral-japan.amazon.com/seller-news/articles",      "16395388697429", "ja_JP"),
    # ⚠️ AE 不强制 locale：实测 Amazon.ae 的卖家新闻**没有阿拉伯文版**，
    #    且一旦带 mons_sel_locale（ar_AE / en_US / en_GB 都试过）该页就取不到任何条目，
    #    故留空 —— 用账号默认语言（当前为中文，本身即可直接阅读）。
    ("AE", "阿联酋站", "seller-news", "https://sellercentral.amazon.ae/seller-news/articles",             "27151611622883", ""),
    ("UK", "英国站",   "policy",      "https://sellercentral.amazon.co.uk/help/hub/reference/external/GQHQGBTD7XB7EECN", "16395388697429", "en_GB"),
    ("DE", "德国站",   "policy",      "https://sellercentral.amazon.de/help/hub/reference/external/GQHQGBTD7XB7EECN",    "27151611622883", "de_DE"),
    ("AU", "澳洲站",   "policy",      "https://sellercentral.amazon.com.au/help/hub/reference/external/GQHQGBTD7XB7EECN", "16395388697429", "en_AU"),
]

# 运行结束后把店铺语言恢复为中文，避免每日任务持续改动店铺显示语言
RESTORE_LOCALE = "zh_CN"
RESTORE_URL = {
    "16395388697429": "https://sellercentral.amazon.com/seller-news?mons_sel_locale=" + RESTORE_LOCALE,
    "27151611622883": "https://sellercentral.amazon.ae/seller-news?mons_sel_locale=" + RESTORE_LOCALE,
}

DATE_EN = re.compile(r"^[A-Z][a-z]{2}\s+\d{1,2},\s+\d{4}$")
DATE_CN = re.compile(r"^\d{4}\s*年\s*\d{1,2}\s*月\s*\d{1,2}\s*日$")
MON = {m: i + 1 for i, m in enumerate(
    ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"])}
MON_DE = {"januar": 1, "februar": 2, "märz": 3, "maerz": 3, "april": 4, "mai": 5, "juni": 6,
          "juli": 7, "august": 8, "september": 9, "oktober": 10, "november": 11, "dezember": 12}


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


def with_locale(url, locale):
    if not locale:
        return url
    sep = "&" if "?" in url else "?"
    if "mons_sel_locale=" in url:
        return url
    return "%s%smons_sel_locale=%s" % (url, sep, locale)


def iso_date(s):
    """把各语言日期归一为 ISO：'Sep 11, 2026' / '2026 年 9 月 29 日' / '29. September 2026'。"""
    if not s:
        return ""
    t = s.strip()
    # 中文（允许空格）
    m = re.match(r"^(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日$", t)
    if m:
        return "%s-%02d-%02d" % (m.group(1), int(m.group(2)), int(m.group(3)))
    # 英文 "Sep 11, 2026"
    m = re.match(r"^([A-Z][a-z]{2})\s+(\d{1,2}),?\s+(\d{4})$", t)
    if m and m.group(1) in MON:
        return "%s-%02d-%02d" % (m.group(3), MON[m.group(1)], int(m.group(2)))
    # 英文 "28 September 2026" / 德文 "29. September 2026"
    m = re.match(r"^(\d{1,2})\.?\s+([A-Za-zÄÖÜäöüß]+)\s+(\d{4})$", t)
    if m:
        mon = m.group(2)[:3].capitalize()
        if mon in MON:
            return "%s-%02d-%02d" % (m.group(3), MON[mon], int(m.group(1)))
        mi = MON_DE.get(m.group(2).lower())
        if mi:
            return "%s-%02d-%02d" % (m.group(3), mi, int(m.group(1)))
    return ""


# ---------------------------------------------------------------- 就绪轮询
# 实测教训：各站点渲染速度差异很大（AE 站 9 秒时链接数为 0、20 秒后才是 20 条）。
# 固定 sleep 会导致「明明有内容却抓到 0 条」这种假失败，因此改为**轮询直到出现**。
def wait_for_count(store, sel, timeout=60, interval=3):
    """轮询直到选择器匹配数 > 0，返回最终数量（超时返回 0）。"""
    waited = 0
    while True:
        v = js(store, "document.querySelectorAll(%s).length" % json.dumps(sel))
        try:
            n = int(v)
        except Exception:
            n = 0
        if n > 0:
            return n
        if waited >= timeout:
            return 0
        time.sleep(interval)
        waited += interval


def wait_for_marker(store, markers, timeout=60, interval=3):
    """轮询直到页面正文包含任一标记词，返回正文（超时返回最后读到的正文）。"""
    waited = 0
    body = ""
    while True:
        body = js(store, "document.body.innerText") or body
        if body and any(m in body for m in markers):
            return body
        if waited >= timeout:
            return body
        time.sleep(interval)
        waited += interval


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


def _parse_seller_news(store):
    raw = js(store, CARD_JS)
    if not raw:
        return None
    try:
        cards = json.loads(raw)
    except Exception:
        return None
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
                if DATE_EN.match(lines[j]) or DATE_CN.match(lines[j]) or \
                   re.match(r"^\d{4}年\d{1,2}月\d{1,2}日$", lines[j]) or \
                   re.match(r"^\d{1,2}\.\s+\w+\s+\d{4}$", lines[j]):
                    date = lines[j]
                    break
        body_txt = " ".join(l for l in ls[1:]
                            if not DATE_EN.match(l) and not DATE_CN.match(l)
                            and not re.match(r"^[\d.,]+K?\s*(views|次浏览|Aufrufe|回視聴|просмотр)", l)
                            and not re.match(r"^\d+\s*(likes|次点赞|Gefällt)", l))
        arts.append({"headline": head, "date": date, "date_iso": iso_date(date),
                     "summary": body_txt[:1500], "id": c["id"]})
    return arts or None


def fetch_seller_news(store, url, locale):
    """先按母语抓；若该语言无内容则回退到不带 locale 的默认语言。"""
    attempts = [locale, ""] if locale else [""]
    last_body = ""
    for i, loc in enumerate(attempts):
        target = with_locale(url, loc)
        run(["page", "visit", "--store-id", store, "--url", target,
             "--wait-until", "networkidle", "--timeout", "60000"], timeout=240)
        # 轮询等文章链接出现，而不是固定 sleep（各站渲染速度差异大）
        n = wait_for_count(store, 'a[href*="/seller-news/articles/"]', timeout=60)
        path = js(store, "location.pathname") or ""
        if "signin" in path:
            return None, "需要登录（跳转到 %s）" % path, ""
        arts = _parse_seller_news(store) if n > 0 else None
        last_body = js(store, "document.body.innerText.replace(/\\n{2,}/g,'\\n')") or last_body
        if arts:
            return arts, None, last_body
        if i == 0 and locale:
            log("     （%s 语言无内容，回退默认语言重试）" % loc)
    return None, "未取到文章列表", last_body


# ---------------------------------------------------------------- 政策变更页
# 多语言「变更列表」存在性标记
POLICY_MARKERS = ["Listed below", "listed below", "计划政策变更", "下面列出",
                  "Im Folgenden sind aktuelle oder bevorstehende Änderungen"]
POLICY_JS = r"""
(function(){
  var t=document.body.innerText.replace(/\n{2,}/g,'\n');
  var ms=%s;
  for(var i=0;i<ms.length;i++){ if(t.indexOf(ms[i])>=0) return t; }
  return null;
})()
""" % json.dumps(POLICY_MARKERS, ensure_ascii=False)

# 条目起始：英文 On/Effective…｜中文 <年>年<月>月<日>日，｜德文 Am <d>. <Monat> <Jahr>
EN_START = re.compile(r"^(?:On|Effective as of|Effective from|Effective)\s+\d{1,2}\s+[A-Za-z]+,?\s*\d{4}")
CN_START = re.compile(r"^\d{4}\s*年\s*\d{1,2}\s*月\s*\d{1,2}\s*日\s*[，,、]")
DE_START = re.compile(r"^(?:Am|Ab dem|Mit Wirkung zum)\s+\d{1,2}\.\s+[A-Za-zÄÖÜäöüß]+\s+\d{4}")
EN_DATE = re.compile(r"^(?:On|Effective as of|Effective from|Effective)\s+(\d{1,2}\s+[A-Za-z]+,?\s*\d{4})")
CN_DATE = re.compile(r"^(\d{4}\s*年\s*\d{1,2}\s*月\s*\d{1,2}\s*日)")
DE_DATE = re.compile(r"^(?:Am|Ab dem|Mit Wirkung zum)\s+(\d{1,2}\.\s+[A-Za-zÄÖÜäöüß]+\s+\d{4})")


def fetch_policy(store, url, locale):
    target = with_locale(url, locale)
    run(["page", "visit", "--store-id", store, "--url", target,
         "--wait-until", "networkidle", "--timeout", "60000"], timeout=240)
    # 同样轮询等正文标记出现
    body = wait_for_marker(store, POLICY_MARKERS, timeout=60)
    if not body or not any(m in body for m in POLICY_MARKERS):
        path = js(store, "location.pathname") or "?"
        return None, "未取到政策正文（path=%s；公开页若用有该站点登录态的店铺会被重定向到登录版）" % path, ""
    body = body.replace("\n\n", "\n")
    lines = [l.strip() for l in body.split("\n")]
    starts = [i for i, l in enumerate(lines)
              if EN_START.match(l) or CN_START.match(l) or DE_START.match(l)]
    arts = []
    for i in starts:
        m = EN_DATE.match(lines[i]) or CN_DATE.match(lines[i]) or DE_DATE.match(lines[i])
        # 保留可读日期文本（去逗号、压缩空白）；**不能去空格**，否则 ISO 解析会失败
        date = re.sub(r"\s+", " ", (m.group(1) if m else "").replace(",", "")).strip()
        title = ""
        for j in range(i - 1, max(0, i - 6), -1):
            if lines[j] and len(lines[j]) < 130 and not lines[j].endswith((".", "。")):
                title = lines[j]
                break
        arts.append({"headline": title or "(未识别标题)", "date": date, "date_iso": iso_date(date),
                     "summary": " ".join(lines[i:i + 10])[:1500], "id": ""})
    if not arts:
        return None, "页面上未找到政策变更条目", body
    return arts, None, body


# ---------------------------------------------------------------- ZClaw 就绪检查
def ensure_ready():
    rc, out, err = run(["doctor"], timeout=180)
    if "全部检查通过" in (out + err):
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


def restore_locale():
    """把店铺显示语言恢复为中文（mons_sel_locale 会持久化，不恢复会改动店铺界面语言）。"""
    for store, url in RESTORE_URL.items():
        try:
            run(["page", "visit", "--store-id", store, "--url", url,
                 "--wait-until", "domcontentloaded", "--timeout", "45000"], timeout=120)
            time.sleep(3)
            log("已恢复店铺 %s 的显示语言为 %s" % (store[-4:], RESTORE_LOCALE))
        except Exception as e:
            log("恢复语言失败（不影响数据）：%s" % e)


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
    rawdir = DATA / "raw" / now.strftime("%Y-%m-%d")
    rawdir.mkdir(parents=True, exist_ok=True)
    for key, label, kind, url, store, locale in SITES:
        log("[%s] locale=%s  %s" % (key, locale, url))
        try:
            arts, err, raw_body = (fetch_seller_news(store, url, locale) if kind == "seller-news"
                                   else fetch_policy(store, url, locale))
        except Exception as e:
            arts, err, raw_body = None, "异常: %s" % e, ""
        if raw_body:
            (rawdir / ("%s.txt" % key)).write_text(raw_body, encoding="utf-8")
        if arts:
            sites[key] = {"label": label, "kind": kind, "url": url, "locale": locale, "ok": True,
                          "fetched_at": now.isoformat(), "stale": False,
                          "count": len(arts), "articles": arts,
                          "raw": str((rawdir / ("%s.txt" % key)).relative_to(ROOT))}
            log("     ✓ %d 条（原始正文 %d 字已存档）" % (len(arts), len(raw_body)))
        else:
            old = prev.get(key) or {}
            sites[key] = {"label": label, "kind": kind, "url": url, "locale": locale, "ok": False,
                          "fetched_at": now.isoformat(), "stale": bool(old.get("articles")),
                          "error": err, "count": old.get("count", 0),
                          "articles": old.get("articles", []), "raw": old.get("raw", "")}
            log("     ✗ %s（%s）" % (err, "沿用上次数据" if old.get("articles") else "无历史数据"))
        status["sites"][key] = {"ok": sites[key]["ok"], "count": sites[key]["count"],
                                "error": sites[key].get("error"), "stale": sites[key]["stale"]}

    payload = {"generated_at": now.isoformat(), "date": now.strftime("%Y-%m-%d"), "sites": sites}
    (DATA / "news.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    (DATA / "history" / ("%s.json" % now.strftime("%Y-%m-%d"))).write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    restore_locale()

    ok = sum(1 for s in sites.values() if s["ok"])
    status["finished_at"] = datetime.now(TZ).isoformat()
    status["ok_sites"] = ok
    status["total_sites"] = len(SITES)
    (DATA / "status.json").write_text(json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8")
    log("完成：%d/%d 站成功" % (ok, len(SITES)))
    if ok == 0:
        log("全部站点抓取失败 —— 以非零码退出，不发布")
        return 3
    return 0


if __name__ == "__main__":
    sys.exit(main())
