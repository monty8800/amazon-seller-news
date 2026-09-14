#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
把 data/news.json 渲染成静态站点（单文件，无外部依赖）。

展示方式（用户要求）：**中文为主 + 原文可对照**
  * 标题：中文在上（主），原文在下（小字灰）
  * 摘要：默认显示中文；点「显示原文」展开该条的原语言摘要
  * 已是中文原生内容（如阿联酋站）不重复展示原文

视觉参照 Amazon Seller Central 的界面语言：
  深蓝顶栏 #232f3e / 橙色强调 #ff9900 / 浅灰底 #eaeded / 白色卡片 + #d5dbdb 描边 / 链接色 #007185
注意：不使用 Amazon 的任何 logo 或商标，页面明确标注为「非官方」。
"""
import html
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"

LANG_LABEL = {"en_US": "英文", "en_GB": "英文", "en_AU": "英文", "ja_JP": "日文",
              "de_DE": "德文", "ar_AE": "阿拉伯文", "zh_CN": "中文", "": "站点默认语言"}

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
.topbar{background:var(--navy);color:#fff;height:52px;display:flex;align-items:center;
  padding:0 16px;gap:14px;position:sticky;top:0;z-index:30}
.brand{display:flex;align-items:center;gap:9px;font-weight:700;font-size:16px;letter-spacing:.2px}
.brand .mark{width:22px;height:22px;border-radius:4px;background:var(--orange);color:var(--navy);
  display:flex;align-items:center;justify-content:center;font-size:13px;font-weight:800}
.brand .sub{font-weight:400;font-size:12px;color:#c9d1d9}
.topbar .spacer{flex:1}
.topbar .meta{font-size:12px;color:#c9d1d9;text-align:right;line-height:1.35}
.badge-unofficial{background:var(--amber-bg);color:var(--amber);border:1px solid #f0d9a8;
  padding:2px 7px;border-radius:10px;font-size:11px}
.subbar{background:var(--navy2);color:#fff;display:flex;gap:2px;padding:0 12px;overflow-x:auto}
.subbar button{background:transparent;border:0;color:#d6dde4;padding:11px 15px;font-size:13px;
  cursor:pointer;border-bottom:3px solid transparent;white-space:nowrap;font-family:inherit}
.subbar button:hover{background:rgba(255,255,255,.07);color:#fff}
.subbar button.active{color:#fff;border-bottom-color:var(--orange);font-weight:600;background:rgba(255,255,255,.05)}
.subbar .cnt{display:inline-block;margin-left:6px;background:rgba(255,255,255,.14);
  border-radius:9px;padding:0 6px;font-size:11px}
.wrap{max-width:1240px;margin:0 auto;padding:18px 16px 56px}
.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:12px;margin-bottom:18px}
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
.p-lang{background:#f4f5f6;color:#4a5259;border-color:#e2e5e7}
.art{padding:15px 18px;border-bottom:1px solid #eef0f1}
.art:last-child{border-bottom:0}
.art:hover{background:#fafbfb}
.hd{display:flex;gap:12px;align-items:flex-start;flex-wrap:wrap}
.date{font-size:12px;color:var(--muted);white-space:nowrap;min-width:100px;font-variant-numeric:tabular-nums;padding-top:3px}
.ttlwrap{flex:1;min-width:260px}
.ttl{font-size:15px;font-weight:600;color:var(--text)}
.ttl-src{font-size:12px;color:#7b858c;margin-top:2px;font-weight:400}
.body{margin-left:112px}
.sum{color:#3a4551;font-size:13px;margin-top:7px;
  display:-webkit-box;-webkit-line-clamp:3;-webkit-box-orient:vertical;overflow:hidden}
.sum.open{-webkit-line-clamp:unset}
.src{display:none;margin-top:8px;padding:10px 12px;background:#f7f8f8;border:1px solid #e9ebec;
  border-radius:6px;font-size:12.5px;color:#4a5259;white-space:pre-wrap}
.src.open{display:block}
.src .lbl{display:block;font-size:11px;color:var(--muted);margin-bottom:5px;font-weight:600}
.acts{margin-top:8px;display:flex;gap:14px;align-items:center;flex-wrap:wrap}
.acts button{background:none;border:0;color:var(--link);cursor:pointer;padding:0;font-size:12px;font-family:inherit}
.acts button:hover{text-decoration:underline;color:var(--orange-d)}
@media(max-width:720px){.body{margin-left:0}}
.table{width:100%;border-collapse:collapse;font-size:13px}
.table th,.table td{padding:9px 12px;text-align:left;border-bottom:1px solid #eef0f1}
.table th{background:#f7f8f8;color:var(--muted);font-weight:600;font-size:12px;border-bottom:1px solid var(--line)}
.table td.n{font-variant-numeric:tabular-nums}
.foot{color:var(--muted);font-size:12px;text-align:center;padding:22px 16px;line-height:1.8}
.note{background:var(--blue-bg);border:1px solid #bfe0ea;border-radius:8px;padding:12px 15px;
  font-size:13px;color:#0f4a5a;margin-bottom:18px}
.empty{padding:26px;text-align:center;color:var(--muted)}
"""

JS = """
function showSite(key){
  document.querySelectorAll('[data-site]').forEach(function(el){
    el.style.display = (key==='ALL' || el.getAttribute('data-site')===key) ? '' : 'none';
  });
  document.querySelectorAll('.subbar button').forEach(function(b){
    b.classList.toggle('active', b.getAttribute('data-key')===key);
  });
}
function tgl(btn, sel){
  var box = btn.closest('.art').querySelector(sel);
  box.classList.toggle('open');
  var on = box.classList.contains('open');
  btn.textContent = on ? btn.getAttribute('data-off') : btn.getAttribute('data-on');
}
"""


def esc(s):
    return html.escape(s or "", quote=True)


def render(data):
    sites = data.get("sites", {})
    order = [k for k in ["US", "JP", "AE", "UK", "DE", "AU"] if k in sites]
    total = sum(len(v.get("articles") or []) for v in sites.values())
    zh_n = sum(1 for v in sites.values() for a in (v.get("articles") or []) if a.get("headline_zh"))
    ok_n = sum(1 for v in sites.values() if v.get("ok"))
    failed = [v["label"] for v in sites.values() if not v.get("ok")]
    gen = (data.get("generated_at") or "")[:19].replace("T", " ")

    tabs = ['<button data-key="ALL" class="active" onclick="showSite(\'ALL\')">全部站点'
            '<span class="cnt">%d</span></button>' % total]
    for k in order:
        v = sites[k]
        tabs.append('<button data-key="%s" onclick="showSite(\'%s\')">%s'
                    '<span class="cnt">%d</span></button>'
                    % (k, k, esc(v["label"]), len(v.get("articles") or [])))

    rows = []
    for k in order:
        v = sites[k]
        lang = LANG_LABEL.get(v.get("locale", ""), v.get("locale") or "—")
        st = ('<span class="pill p-ok">正常</span>' if v.get("ok")
              else '<span class="pill p-warn">沿用上次</span>' if v.get("stale")
              else '<span class="pill p-err">抓取失败</span>')
        rows.append("<tr><td>%s <span class='muted'>%s</span></td><td>%s</td>"
                    "<td><span class='pill p-lang'>%s</span></td><td class='n'>%d</td>"
                    "<td>%s</td><td class='muted'>%s</td></tr>"
                    % (esc(v["label"]), k, st, esc(lang), len(v.get("articles") or []),
                       "卖家新闻" if v.get("kind") == "seller-news" else "政策变更页",
                       esc(v.get("error") or "—")))

    panels = []
    for k in order:
        v = sites[k]
        arts = v.get("articles") or []
        lang = LANG_LABEL.get(v.get("locale", ""), v.get("locale") or "—")
        if not arts:
            body = '<div class="empty">无数据（%s）</div>' % esc(v.get("error") or "未抓取")
        else:
            items = []
            for a in arts:
                zh = a.get("headline_zh") or ""
                native = a.get("zh_native")
                orig_h = a.get("headline") or ""
                zh_s = a.get("summary_zh") or ""
                orig_s = a.get("summary") or ""
                show_orig = bool(orig_h) and not native and orig_h.strip() != (zh or "").strip()

                ttl_main = esc(zh or orig_h)
                ttl_src = ('<div class="ttl-src">原文：%s</div>' % esc(orig_h)) if show_orig else ""
                long_zh = len(zh_s) > 200
                long_src = len(orig_s) > 200

                acts = []
                if long_zh:
                    acts.append('<button data-on="展开全文" data-off="收起" '
                                'onclick="tgl(this,\'.sum\')">展开全文</button>')
                if show_orig and orig_s:
                    acts.append('<button data-on="显示原文（%s）" data-off="隐藏原文" '
                                'onclick="tgl(this,\'.src\')">显示原文（%s）</button>'
                                % (esc(lang), esc(lang)))
                acts.append('<a href="%s" target="_blank" rel="noopener">打开官方页面 ↗</a>'
                            % esc(v.get("url") or "#"))

                src_block = ""
                if show_orig and orig_s:
                    src_block = ('<div class="src"><span class="lbl">原文（%s）</span>%s</div>'
                                 % (esc(lang), esc(orig_s)))

                items.append(
                    '<div class="art">'
                    '<div class="hd"><span class="date">%s</span><div class="ttlwrap">'
                    '<div class="ttl">%s</div>%s</div>%s</div>'
                    '<div class="body"><div class="sum">%s</div>%s'
                    '<div class="acts">%s</div></div></div>'
                    % (esc(a.get("date") or a.get("date_iso") or "—"),
                       ttl_main, ttl_src,
                       ('<span class="pill p-warn">沿用上次</span>' if v.get("stale") else ""),
                       esc(zh_s or orig_s), src_block, "".join(acts)))
            body = "".join(items)

        badge = ('<span class="pill p-ok">正常</span>' if v.get("ok")
                 else '<span class="pill p-warn">沿用上次</span>' if v.get("stale")
                 else '<span class="pill p-err">失败</span>')
        panels.append(
            '<div class="panel" data-site="%s"><div class="panel-h"><h2>%s</h2>%s'
            '<span class="pill p-lang">原文语言：%s</span>'
            '<span class="muted">共 %d 条 · %s</span>'
            '<span class="muted" style="margin-left:auto">'
            '<a href="%s" target="_blank" rel="noopener">打开官方页面 ↗</a></span>'
            '</div><div class="panel-b">%s</div></div>'
            % (k, esc(v["label"]), badge, esc(lang), len(arts),
               "Seller Central 卖家新闻" if v.get("kind") == "seller-news" else "Amazon 计划政策变更页",
               esc(v.get("url") or "#"), body))

    note = ('<div class="note"><b>中文翻译</b>：各站点按其母语抓取原文（日本站日文、德国站德文，'
            '英美澳站英文），再用 AI 翻译成简体中文 —— <b>中文为主，原文可点「显示原文」对照</b>。'
            '已是中文原生的内容（如阿联酋站）不重复展示。%s</div>'
            % ("<br><b>本次未成功的站点：</b>" + "、".join(esc(f) for f in failed) +
               "（相关站点若显示「沿用上次」，表示本次抓取失败、页面为上一次的数据）" if failed else ""))

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
  <div class="meta">最后更新：%s<br>原文取自 Amazon 官方页面 · AI 译为中文</div>
</div>
<div class="subbar">%s</div>
<div class="wrap">
  %s
  <div class="kpis">
    <div class="kpi"><div class="k">抓取成功的站点</div><div class="v">%d<small>/ %d</small></div></div>
    <div class="kpi"><div class="k">收录条目</div><div class="v">%d</div></div>
    <div class="kpi"><div class="k">已译成中文</div><div class="v">%d<small>/ %d</small></div></div>
    <div class="kpi"><div class="k">上次更新</div><div class="v" style="font-size:15px;font-weight:600">%s</div></div>
  </div>
  <div class="panel"><div class="panel-h"><h2>抓取状态</h2>
    <span class="muted">每次运行的逐站点结果，含抓取语言与失败原因</span></div>
    <div class="panel-b"><table class="table">
      <thead><tr><th>站点</th><th>状态</th><th>原文语言</th><th>条数</th><th>来源类型</th><th>备注</th></tr></thead>
      <tbody>%s</tbody></table></div>
  </div>
  %s
  <div class="foot">
    本页由本地脚本每日自动抓取 Amazon 公开页面、并经 AI 翻译生成，<b>非 Amazon 官方页面</b>，不代表 Amazon 立场。<br>
    AI 翻译可能存在偏差，以「显示原文」中的官方原文为准。数据仅含 Amazon 公开发布的新闻与政策变更，<br>
    不含任何店铺、账号或账户状况信息。｜ 生成时间 %s ｜ 生成器 build.py
  </div>
</div>
<script>%s</script>
</body></html>""" % (CSS, esc(gen), "".join(tabs), note, ok_n, len(order), total, zh_n, total,
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
