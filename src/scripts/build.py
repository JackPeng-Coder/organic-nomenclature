# -*- coding: utf-8 -*-
"""Build the two PDF books with Chromium + PyMuPDF."""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import fitz  # PyMuPDF
from jinja2 import Environment, FileSystemLoader
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC / "data"))
from exercises import CHAPTERS, ITEMS, SPECIALS, MOCKS  # noqa: E402

CONTENT = SRC / "content"
TEMPLATES = SRC / "templates"
ASSETS = SRC / "assets"
STRUCTS = ASSETS / "structures"
BUILD = ROOT / "build"
OUTPUT = ROOT / "output"
BUILD.mkdir(exist_ok=True)
OUTPUT.mkdir(exist_ok=True)

CSS_URI = (ASSETS / "book.css").as_uri()
STRUCT_URI = STRUCTS.as_uri()

INDEX = json.loads((SRC / "data" / "structures_index.json").read_text(encoding="utf-8"))
INDEX_BY_ID = {x["id"]: x for x in INDEX}

env = Environment(
    loader=FileSystemLoader([str(CONTENT), str(TEMPLATES)]),
    autoescape=False,
    trim_blocks=False,
    lstrip_blocks=False,
)


def fig(cid, caption="", cls="", alt=None, maxh=None):
    info = INDEX_BY_ID.get(cid)
    if not info:
        raise KeyError(f"unknown structure id: {cid}")
    classes = "struct-img"
    if cls:
        classes += " " + cls
    style = f' style="max-height:{maxh}"' if maxh else ""
    cap = f"<figcaption>{caption}</figcaption>" if caption else ""
    return (
        f'<figure class="figure"><img class="{classes}" src="{STRUCT_URI}/{cid}.svg" '
        f'alt="{alt or info["name"]}"{style}>{cap}</figure>'
    )


def inline_fig(cid, alt=None, height=None):
    info = INDEX_BY_ID.get(cid)
    if not info:
        raise KeyError(f"unknown structure id: {cid}")
    style = f' style="height:{height}"' if height else ""
    return (
        f'<span class="inline-fig"><img src="{STRUCT_URI}/{cid}.svg" '
        f'alt="{alt or info["name"]}"{style}></span>'
    )


env.globals["fig"] = fig
env.globals["inline_fig"] = inline_fig
env.globals["struct_uri"] = STRUCT_URI


# --------------------------------------------------------------------------
# HTML rendering
# --------------------------------------------------------------------------

def add_anchor_spans(html: str) -> str:
    def repl(m):
        tag, attrs, anchor = m.group(1), m.group(2), m.group(3)
        return f'<{tag}{attrs}><span class="anchor">@@{anchor}@@</span>'

    return re.sub(
        r'<(h[123])([^>]*?data-anchor="([^"]+)"[^>]*?)>',
        repl,
        html,
    )


def parse_toc(html: str):
    entries = []
    for m in re.finditer(r'<h([1-4])([^>]*data-toc="[^"]+"[^>]*)>', html, re.S):
        tag, attrs = m.group(1), m.group(2)
        title = re.search(r'data-toc="([^"]+)"', attrs).group(1)
        anchor = re.search(r'data-anchor="([^"]+)"', attrs).group(1)
        level_m = re.search(r'data-level="([^"]+)"', attrs)
        level = level_m.group(1) if level_m else {"1": "part", "2": "chapter", "3": "section"}.get(tag, "section")
        entries.append({"tag": f"h{tag}", "level": level, "title": title, "anchor": anchor})
    return entries


def render_body_html(book: str):
    template = "knowledge.html" if book == "knowledge" else "exercise.html"
    if book == "knowledge":
        html = env.get_template(template).render(book=book, css_uri=CSS_URI)
    else:
        html = env.get_template(template).render(
            book=book, css_uri=CSS_URI, chapters=CHAPTERS, items=ITEMS,
            specials=SPECIALS, mocks=MOCKS,
        )
    html = add_anchor_spans(html)
    path = BUILD / f"{book}_body.html"
    path.write_text(html, encoding="utf-8")
    return path, html


# --------------------------------------------------------------------------
# PDF rendering
# --------------------------------------------------------------------------

HEADER_TEMPLATE = """
<div style="width:100%; font-family:'Microsoft YaHei','SimHei',sans-serif; font-size:7.2pt; color:#75878a; padding:0 17mm;">
  <div style="display:flex; justify-content:space-between; align-items:flex-end; border-bottom:0.4pt solid #d8d2c4; padding-bottom:1.8mm; letter-spacing:0.04em;">
    <span>高中有机化学命名全书</span>
    <span>__LABEL__</span>
  </div>
</div>
"""

FOOTER_TEMPLATE = """
<div style="width:100%; font-family:'Microsoft YaHei','SimHei',sans-serif; font-size:7.8pt; color:#607276; padding:0 17mm;">
  <div style="display:flex; justify-content:space-between; align-items:center; border-top:0.4pt solid #d8d2c4; padding-top:1.8mm; letter-spacing:0.03em;">
    <span>2026 · 学习版</span>
    <span><span class="pageNumber"></span> / <span class="totalPages"></span></span>
    <span>__LABEL__</span>
  </div>
</div>
"""


def pdf_render(html_path: Path, pdf_path: Path, *, kind: str, book: str, header_label: str):
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1200, "height": 1600})
        page.goto(html_path.as_uri(), wait_until="load")
        page.wait_for_timeout(400)
        page.evaluate(
            """async () => {
                await document.fonts.ready;
                await Promise.all(Array.from(document.images).map(img => {
                    if (img.complete) return Promise.resolve();
                    return new Promise(resolve => { img.onload = resolve; img.onerror = resolve; });
                }));
            }"""
        )
        page.wait_for_timeout(300)
        if kind == "cover":
            page.pdf(
                path=str(pdf_path),
                width="210mm",
                height="297mm",
                margin={"top": "0", "bottom": "0", "left": "0", "right": "0"},
                print_background=True,
                display_header_footer=False,
                prefer_css_page_size=True,
            )
        elif kind == "toc":
            page.pdf(
                path=str(pdf_path),
                format="A4",
                margin={"top": "19mm", "bottom": "19mm", "left": "17mm", "right": "17mm"},
                print_background=True,
                display_header_footer=False,
                prefer_css_page_size=True,
            )
        else:
            page.pdf(
                path=str(pdf_path),
                format="A4",
                margin={"top": "19mm", "bottom": "20mm", "left": "17mm", "right": "17mm"},
                print_background=True,
                display_header_footer=True,
                header_template=HEADER_TEMPLATE.replace("__LABEL__", header_label),
                footer_template=FOOTER_TEMPLATE.replace("__LABEL__", "知识手册" if book == "knowledge" else "配套练习"),
                prefer_css_page_size=True,
            )
        browser.close()
    return pdf_path


# --------------------------------------------------------------------------
# TOC + outline
# --------------------------------------------------------------------------

def locate_pages(body_pdf: Path, entries):
    doc = fitz.open(str(body_pdf))
    page_map = {}
    for e in entries:
        token = f"@@{e['anchor']}@@"
        found = None
        for i in range(doc.page_count):
            if doc[i].search_for(token):
                found = i + 1
                break
        if found is None:
            # fallback: search heading text, prefer later pages after previous hit
            for i in range(doc.page_count):
                if doc[i].search_for(e["title"]):
                    found = i + 1
                    break
        if found is not None:
            page_map[e["anchor"]] = found
        else:
            print(f"  ! TOC anchor not found: {e['anchor']} / {e['title']}")
    doc.close()
    return page_map


def render_cover(book: str, pdf_path: Path):
    if book == "knowledge":
        context = dict(
            light=False,
            volume_no="01",
            kicker="SYSTEMATIC NOMENCLATURE",
            title="高中有机化学<br>命名知识手册",
            subtitle="系统规则 · 典型例析 · 高考真题 · 易错清单",
            points=["命名总则与书写规范", "烃类与烃的衍生物", "顺反异构与手性拓展", "高考真题与速查卡"],
            mark="名",
            bottom_left="2026年11月 · 第一版",
            bottom_right="知识手册 / HANDBOOK",
        )
    else:
        context = dict(
            light=True,
            volume_no="02",
            kicker="PRACTICE WORKBOOK",
            title="高中有机化学<br>命名配套练习",
            subtitle="分章同步 · 专项突破 · 模拟实战 · 详解答案",
            points=["20章同步练习", "8个专项突破", "2套综合模拟卷", "全部答案与重点解析"],
            mark="练",
            bottom_left="2026年11月 · 第一版",
            bottom_right="配套练习 / WORKBOOK",
        )
    html = env.get_template("cover.html").render(**context, css_uri=CSS_URI)
    html_path = BUILD / f"{book}_cover.html"
    html_path.write_text(html, encoding="utf-8")
    return pdf_render(html_path, pdf_path, kind="cover", book=book, header_label="")


def render_toc(book: str, entries, page_map, pdf_path: Path):
    html = env.get_template("toc.html").render(
        entries=entries,
        page_map=page_map,
        css_uri=CSS_URI,
        book_title="高中有机化学命名知识手册" if book == "knowledge" else "高中有机化学命名配套练习",
        book_kicker="知识手册" if book == "knowledge" else "配套练习",
    )
    html_path = BUILD / f"{book}_toc.html"
    html_path.write_text(html, encoding="utf-8")
    return pdf_render(html_path, pdf_path, kind="toc", book=book, header_label="")


def merge_book(book: str, cover_pdf: Path, toc_pdf: Path, body_pdf: Path, entries, page_map, out_name: str):
    doc = fitz.open(str(cover_pdf))
    cover_count = doc.page_count
    toc_doc = fitz.open(str(toc_pdf))
    toc_count = toc_doc.page_count
    doc.insert_pdf(toc_doc)
    body_doc = fitz.open(str(body_pdf))
    doc.insert_pdf(body_doc)

    outline = [[1, "封面", 1]]
    if toc_count:
        outline.append([1, "目录", cover_count + 1])
    for e in entries:
        p = page_map.get(e["anchor"])
        if not p:
            continue
        level = {"part": 1, "chapter": 2, "section": 3}[e["level"]]
        outline.append([level, e["title"], cover_count + toc_count + p])

    doc.set_toc(outline)
    doc.set_metadata({
        "title": "高中有机化学命名知识手册" if book == "knowledge" else "高中有机化学命名配套练习",
        "author": "OpenCode · 2026",
        "subject": "高中化学有机化合物系统命名法",
        "keywords": "高中化学, 有机化学, 命名, 系统命名法, 高考, 练习",
        "creator": "HTML/CSS + Chromium + PyMuPDF",
        "producer": "OpenCode",
    })
    out = OUTPUT / out_name
    doc.save(str(out), garbage=4, deflate=True)
    doc.close()
    print(f"  -> {out}  ({out.stat().st_size / 1024 / 1024:.1f} MB)")
    return out


# --------------------------------------------------------------------------
# Build entry
# --------------------------------------------------------------------------

def build_book(book: str):
    print(f"\n=== {book} ===")
    body_html_path, body_html = render_body_html(book)
    entries = parse_toc(body_html)
    print(f"  TOC entries: {len(entries)}")

    body_pdf = BUILD / f"{book}_body.pdf"
    pdf_render(body_html_path, body_pdf, kind="body", book=book, header_label="知识精讲" if book == "knowledge" else "配套练习")
    print(f"  body pages: {fitz.open(str(body_pdf)).page_count}")

    page_map = locate_pages(body_pdf, entries)
    print(f"  located: {len(page_map)}/{len(entries)}")

    cover_pdf = render_cover(book, BUILD / f"{book}_cover.pdf")
    toc_pdf = render_toc(book, entries, page_map, BUILD / f"{book}_toc.pdf")
    print(f"  toc pages: {fitz.open(str(toc_pdf)).page_count}")

    out_name = "高中有机化学命名_知识手册.pdf" if book == "knowledge" else "高中有机化学命名_配套练习.pdf"
    return merge_book(book, cover_pdf, toc_pdf, body_pdf, entries, page_map, out_name)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--book", choices=["knowledge", "exercise", "all"], default="all")
    args = ap.parse_args()
    if args.book in ("knowledge", "all"):
        build_book("knowledge")
    if args.book in ("exercise", "all"):
        build_book("exercise")


if __name__ == "__main__":
    main()
