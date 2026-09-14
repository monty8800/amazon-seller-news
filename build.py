#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
把 data/news.json 渲染成静态站点（单文件，无外部依赖）。

视觉参照 Amazon Seller Central 的界面语言：
  深蓝顶栏 #232f3e / 橙色强调 #ff9900 / 浅灰底 #eaeded / 白色卡片 + #d5dbdb 描边 / 链接色 #007185
注意：不使用 Amazon 的任何 logo 或商标，页面明确标注为「非官方」。
"""
import html
import json
from datetime import datetime, timezone, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
TZ = timezone(timedelta(hours=8))

CSS = """
:root{
  --navy:#232f3e; --navy2:#37475a; --orange:#ff9900; --orange-d:#e88b00;
  --bg:#eaeded; --card:#ffffff; --line:#d5dbdb; --text:#111820; --muted:#565959;
  --link:#007185; --green:#067d62; --green-bg:#e6f5f0; --red:#b12704; --red-bg:#fdecea;
  --amber:#8a6116; --amber-bg:#fff8e5; --blue-bg:#e8f4f9;
}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--text);
  font-family:"Amazon Ember","Helvetica Neue",Helvetica,Arial,"PingFang SC","Hiragino Sans GB","Microsoft YaHei",sans-serif;
  font-size:14px;line-height:1.55;-webkit-font-smoothing:antialiased}
a{color:var(--link);text-decoration:none}
a:hover{text-decoration:underline;color:var(--orange-d)}

/* 顶栏 */
.topbar{background:var(--navy);color:#fff;height:52px;display:flex;align-items:center;
  padding:0 16px;gap:14px;position:sticky;top:0;z-index:30}
.brand{display:flex;align-items:center;gap:9px;font-weight:700;font-size:16px;letter-spacing:.2px}
.brand .mark{width:22px;height:22px;border-radius:4px;background:var(--orange);color:var(--navy);
  display:flex;align-items:center;justify-content:center;font-size:13px;font-weight:800}
.brand .sub{font-weight:400;font-size:12px;color:#c9d1d9}
.topbar .spacer{flex:1}
.topbar .meta{font-size:12px;color:#c9d1d9;text-align:right;line-height:1.35}
.badge-unofficial{background:var(--orange-bg);color:var(--amber);border:1px solid #f0d9a8;
  padding:2px 7px;border-radius:10px;font-size:11px}

/* 二级栏 + 站点标签 */
.subbar{background:var(--navy2);color:#fff;display:flex;gap:2px;padding:0 12px;overflow-x:auto}
.subbar button{background:transparent;border:0;color:#d6dde4;padding:11px 15px;font-size:13px;
  cursor:pointer;border-bottom:3px solid transparent;white-space:nowrap;font-family:inherit}
.subbar button:hover{background:rgba(255,255,255,.07);color:#fff}
.subbar button.active{color:#fff;border-bottom-color:var(--orange);font-weight:600;background:rgba(255,255,255,.05)}
.subbar .cnt{display:inline-block;margin-left:6px;background:rgba(255,255,255,.14);
  border-radius:9px;padding:0 6px;font-size:11px}

/* 布局 */
.wrap{max-width:1240px;margin:0 auto;padding:18px 16px 56px}
.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:12px;margin-bottom:18px}
.kpi{background:var(--card);border:1px solid var(--line);border-radius:8px;padding:14px 16px}
.kpi .k{font-size:12px;color:var(--muted);margin-bottom:6px}
.kpi .v{font-size:24px;font-weight:700;letter-spacing:-.3px}
.kpi .v small{font-size:13px;font-weight:400;color:var(--muted);margin-left:4px}

.panel{background:var(--card);border:1px solid var(--line);border-radius:8px;margin-bottom:18px;overflow:hidden}
.panel-h{padding:13px 16px;border-bottom:1px solid var(--line);display:flex;align-items:center;gap:10px;flex-wrap:wrap}
.panel-h h2{margin:0;font-size:16px}
.panel-h .muted{color:var(--muted);font-size:12px}
.panel-b{padding:0}

.pill{display:inline-block;padding:2px 9px;border-radius:11px;font-size:11px;font-weight:600;border:1px solid transparent}
.p-ok{background:var(--green-bg);color:var(--green);border-color:#b7e0d4}
.p-warn{background:var(--amber-bg);color:var(--amber);border-color:#f0d9a8}
.p-err{background:var(--red-bg);color:var(--red);border-color:#f3c3bb}
.p-info{background:var(--blue-bg);color:var(--link);border-color:#bfe0ea}

/* 文章列表 */
.art{padding:15px 18px;border-bottom:1px solid #eef0f1}
.art:last-child{border-bottom:0}
.art:hover{background:#fafbfb}
.art .hd{display:flex;gap:12px;align-items:baseline;flex-wrap:wrap}
.art .date{font-size:12px;color:var(--muted);white-space:nowrap;min-width:104px;font-variant-numeric:tabular-nums}
.art .ttl{font-size:15px;font-weight:600;color:var(--text);flex:1;min-width:260px}
.art .sum{color:#3a4551;font-size:13px;margin-top:6px;margin-left:116px;
  display:-webkit-box;-webkit-line-clamp:3;-webkit-box-orient:vertical;overflow:hidden}
.art .sum.open{-webkit-line-clamp:unset}
.art .more{margin-left:116px;margin-top:6px;font-size:12px;background:none;border:0;color:var(--link);
  cursor:pointer;padding:0;font-family:inherit}
@media(max-width:720px){.art .sum,.art .more{margin-left:0}}

.table{width:100%;border-collapse:collapse;font-size:13px}
.table th,.table td{padding:9px 12px;text-align:left;border-bottom:1px solid #eef0f1}
.table th{background:#f7f8f8;color:var(--muted);font-weight:600;font-size:12px;
  text-transform:none;border-bottom:1px solid var(--line)}
.table td.n{font-variant-numeric:tabular-nums}

.foot{color:var(--muted);font-size:12px;text-align:center;padding:22px 16px;line-height:1.8}
.note{background:var(--blue-bg);border:1px solid #bfe0ea;border-radius:8px;padding:12px 15px;
  font-size:13px;color:#0f4a5a;margin-bottom:18px}
.empty{padding:26px;text-align:center;color:var(--muted)}
"""

JS = """
function toggleSum(btn){
  var s=btn.parentElement.querySelector('.sum');
  s.classList.toggle('open');
  btn.textContent = s.classList.contains('open') ? '收起' : '展开全文';
}
function showSite(key){
  document.querySelectorAll('[data-site]').forEach(function(el){
    el.style.display = (key==='ALL' || el.getAttribute('data-site')===key) ? '' : 'none';
  });
  document.querySelectorAll('.subbar button').forEach(function(b){
    b.classList.toggle('active', b.getAttribute('data-key')===key);
  });
}
"""


def esc(s):
    return html.escape(s or "", quote=True)


def render(data):
    sites = data.get("sites", {})
    order = [k for k in ["US", "JP", "AE", "UK", "DE", "AU"] if k in sites]
    total_arts = sum(v.get("count", 0) for v in sites.values())
    ok_n = sum(1 for v in sites.values() if v.get("ok"))
    failed = [v["label"] for v in sites.values() if not v.get("ok")]
    gen = data.get("generated_at", "")[:19].replace("T", " ")

    # 站点标签
    tabs = ['<button data-key="ALL" class="active" onclick="showSite(\'ALL\')">全部站点'
            '<span class="cnt">%d</span></button>' % total_arts]
    for k in order:
        v = sites[k]
        cls = "p-ok" if v.get("ok") else ("p-warn" if v.get("stale") else "p-err")
        tabs.append('<button data-key="%s" onclick="showSite(\'%s\')">%s'
                    '<span class="cnt">%d</span></button>' % (k, k, esc(v["label"]), v.get("count", 0)))

    # 站点状态表
    rows = []
    for k in order:
        v = sites[k]
        if v.get("ok"):
            st = '<span class="pill p-ok">正常</span>'
        elif v.get("stale"):
            st = '<span class="pill p-warn">抓取失败·沿用上次</span>'
        else:
            st = '<span class="pill p-err">抓取失败</span>'
        err = esc(v.get("error") or "")
        rows.append("<tr><td>%s <span class='muted'>%s</span></td><td>%s</td>"
                    "<td class='n'>%d</td><td>%s</td><td class='muted'>%s</td></tr>"
                    % (esc(v["label"]), k, st, v.get("count", 0),
                       "卖家新闻" if v.get("kind") == "seller-news" else "政策变更页", err or "—"))

    # 文章面板
    panels = []
    for k in order:
        v = sites[k]
        arts = v.get("articles") or []
        if not arts:
            body = '<div class="empty">无数据（%s）</div>' % esc(v.get("error") or "未抓取")
        else:
            items = []
            for i, a in enumerate(arts):
                long = len(a.get("summary") or "") > 200
                items.append(
                    '<div class="art">'
                    '<div class="hd"><span class="date">%s</span>'
                    '<span class="ttl">%s</span>%s</div>'
                    '<div class="sum">%s</div>%s</div>'
                    % (esc(a.get("date") or a.get("date_iso") or "—"),
                       esc(a.get("headline")),
                       ('<span class="pill p-warn">沿用上次</span>' if v.get("stale") else ""),
                       esc(a.get("summary") or ""),
                       ('<button class="more" onclick="toggleSum(this)">展开全文</button>' if long else "")))
            body = "".join(items)
        badge = ('<span class="pill p-ok">正常</span>' if v.get("ok")
                 else '<span class="pill p-warn">沿用上次</span>' if v.get("stale")
                 else '<span class="pill p-err">失败</span>')
        panels.append(
            '<div class="panel" data-site="%s"><div class="panel-h"><h2>%s</h2>%s'
            '<span class="muted">共 %d 条 · 来源：%s</span>'
            '<span class="muted" style="margin-left:auto"><a href="%s" target="_blank" rel="noopener">打开官方页面 ↗</a></span>'
            '</div><div class="panel-b">%s</div></div>'
            % (k, esc(v["label"]), badge, len(arts),
               "Seller Central 卖家新闻" if v.get("kind") == "seller-news" else "Amazon 计划政策变更页",
               esc(v.get("url") or "#"), body))

    note = ""
    if failed:
        note = ('<div class="note"><b>本次未成功的站点：</b>%s。'
                '相关站点若显示「沿用上次」，表示本次抓取失败、页面上是上一次的数据，不是最新。</div>'
                % "、".join(esc(f) for f in failed))

    return """<!DOCTYPE html>
<html lang="zh-CN"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Amazon 各站点新闻与规则变更 · 每日看板</title>
<style>%s</style></head>
<body>
<div class="topbar">
  <div class="brand"><span class="mark">SN</span>
    <span>Seller News<span class="sub"> · 亚马逊站点新闻看板</span></span>
  </div>
  <span class="badge-unofficial">非官方 · 自建</span>
  <div class="spacer"></div>
  <div class="meta">最后更新：%s<br>数据来自 Amazon 公开页面</div>
</div>
<div class="subbar">%s</div>
<div class="wrap">
  %s
  <div class="kpis">
    <div class="kpi"><div class="k">抓取成功的站点</div><div class="v">%d<small>/ %d</small></div></div>
    <div class="kpi"><div class="k">收录条目</div><div class="v">%d</div></div>
    <div class="kpi"><div class="k">上次更新</div><div class="v" style="font-size:15px;font-weight:600">%s</div></div>
    <div class="kpi"><div class="k">数据源</div><div class="v" style="font-size:15px;font-weight:600">Amazon 官方页面</div></div>
  </div>
  <div class="panel"><div class="panel-h"><h2>抓取状态</h2>
    <span class="muted">每次运行的逐站点结果，失败原因会显示在最后一列</span></div>
    <div class="panel-b"><table class="table">
      <thead><tr><th>站点</th><th>状态</th><th>条数</th><th>来源类型</th><th>备注</th></tr></thead>
      <tbody>%s</tbody></table></div>
  </div>
  %s
  <div class="foot">
    本页由本地脚本每日自动抓取 Amazon 公开页面生成，<b>非 Amazon 官方页面</b>，不代表 Amazon 立场。<br>
    数据仅含 Amazon 公开发布的新闻与政策变更，不含任何店铺、账号或账户状况信息。<br>
    生成时间 %s ｜ 生成器 build.py
  </div>
</div>
<script>%s</script>
</body></html>""" % (CSS, esc(gen), "".join(tabs), note, ok_n, len(order), total_arts,
                     esc(gen), "".join(rows), "".join(panels), esc(gen), JS)


def main():
    src = DATA / "news.json"
    if not src.exists():
        print("缺少 data/news.json，先运行 fetch.py")
        return 1
    data = json.loads(src.read_text(encoding="utf-8"))
    out = ROOT / "index.html"
    out.write_text(render(data), encoding="utf-8")
    print("已生成 %s（%d 字节）" % (out, out.stat().st_size))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
