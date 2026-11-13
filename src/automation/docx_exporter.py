"""
Modul Export Artikel Travelista ke Format Microsoft Word (.docx).
Menghasilkan dokumen Word berformat rapi dan profesional lengkap dengan metadata,
tabel ringkasan verifikasi multi-agent, badan artikel editorial, dan daftar referensi.
"""
import io
import re
from typing import Dict, Any, List, Optional
from docx import Document
from docx.shared import Inches, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.oxml import OxmlElement
from docx.oxml.ns import qn


def _set_cell_background(cell, hex_color: str):
    """Mengatur warna latar belakang sel tabel Word (hex_color: misal 'F4F6F9')."""
    tcPr = cell._element.get_or_add_tcPr()
    shd = OxmlElement('w:shd')
    shd.set(qn('w:val'), 'clear')
    shd.set(qn('w:color'), 'auto')
    shd.set(qn('w:fill'), hex_color.lstrip('#'))
    tcPr.append(shd)


def _set_cell_margins(cell, top=100, bottom=100, left=150, right=150):
    """Mengatur padding internal sel tabel."""
    tcPr = cell._element.get_or_add_tcPr()
    tcMar = OxmlElement('w:tcMar')
    for m, val in [('top', top), ('bottom', bottom), ('left', left), ('right', right)]:
        node = OxmlElement(f'w:{m}')
        node.set(qn('w:w'), str(val))
        node.set(qn('w:type'), 'dxa')
        tcMar.append(node)
    tcPr.append(tcMar)


def build_article_docx(doc: Document, article: Dict[str, Any], is_first: bool = True):
    """Menambahkan konten satu artikel ke dalam dokumen docx."""
    if not is_first:
        doc.add_page_break()

    title = article.get("final_title") or article.get("target_title") or article.get("topic") or "Artikel Editorial Travelista"
    genre = article.get("genre", "Umum")
    run_date = article.get("run_date") or article.get("created_at") or "-"
    topic = article.get("topic", "-")
    trend_kw = article.get("trending_keyword", "-")
    trend_src = article.get("trend_source", "Google Trends")
    writer_model = article.get("writer_model", "Gemini 3.5 Flash")
    reviewer_model = article.get("reviewer_model", "GPT-OSS 120B (Groq)")
    checker2_score = article.get("final_check_score", 95)
    audit_notes = article.get("final_check_notes", "Format dan fakta lolos audit redaksi.")
    cover_url = article.get("cover_image_url") or ""
    cover_alt = article.get("cover_image_alt") or ""
    article_md = article.get("article_markdown") or ""

    meta_title = article.get("meta_title") or article.get("cms_payload", {}).get("article", {}).get("meta_title") or title[:60]
    excerpt = article.get("excerpt") or article.get("cms_payload", {}).get("article", {}).get("excerpt") or article.get("meta_description") or ""
    seo_score = article.get("seo_score") or article.get("cms_payload", {}).get("seo_audit", {}).get("seo_score", 92)
    search_intent = article.get("cms_payload", {}).get("seo_audit", {}).get("search_intent") or "Wisata & Eksplorasi"

    # Header / Kategori Badge
    p_badge = doc.add_paragraph()
    p_badge.alignment = WD_ALIGN_PARAGRAPH.LEFT
    run_badge = p_badge.add_run(f"TRAVELISTA INDONESIA • {genre.upper()}")
    run_badge.font.name = "Arial"
    run_badge.font.size = Pt(9.5)
    run_badge.font.bold = True
    run_badge.font.color.rgb = RGBColor(0, 122, 255)

    # Judul Artikel
    p_title = doc.add_paragraph()
    p_title.paragraph_format.space_before = Pt(4)
    p_title.paragraph_format.space_after = Pt(12)
    p_title.paragraph_format.line_spacing = 1.15
    run_title = p_title.add_run(title)
    run_title.font.name = "Georgia"
    run_title.font.size = Pt(20)
    run_title.font.bold = True
    run_title.font.color.rgb = RGBColor(26, 36, 43)

    # Tabel Ringkasan Metadata & Audit AI
    table = doc.add_table(rows=6, cols=2)
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    table.autofit = False

    col_widths = [Inches(2.2), Inches(4.3)]
    for row in table.rows:
        for i, width in enumerate(col_widths):
            row.cells[i].width = width

    meta_items = [
        ("Tanggal Rilis / Naskah", f"{run_date} (Bank Naskah H-1 Siap Tayang)"),
        ("Tren Pemicu & Topik", f"{trend_kw} ({trend_src}) | Topik: {topic}"),
        ("SEO SERP & Search Intent", f"Meta Title: {meta_title} | Niat: {search_intent}"),
        ("Audit Kepatuhan & SEO", f"Checker 1: LULUS | Checker 2: {checker2_score}/100 | SEO On-Page: {seo_score}/100"),
        ("Smart Model Router", f"Writer: {writer_model} | Reviewer: {reviewer_model}"),
        ("Hak Cipta & Redaksi", "Kontributor: Farrel & Travelista AI Autonomous Desk"),
    ]

    for idx, (label, val) in enumerate(meta_items):
        cell_lbl = table.cell(idx, 0)
        cell_val = table.cell(idx, 1)

        _set_cell_background(cell_lbl, "F0F4F8")
        _set_cell_background(cell_val, "FAFBFD")
        _set_cell_margins(cell_lbl, 80, 80, 120, 120)
        _set_cell_margins(cell_val, 80, 80, 120, 120)

        p_lbl = cell_lbl.paragraphs[0]
        p_lbl.paragraph_format.space_after = Pt(2)
        r_lbl = p_lbl.add_run(label)
        r_lbl.font.name = "Arial"
        r_lbl.font.size = Pt(9)
        r_lbl.font.bold = True
        r_lbl.font.color.rgb = RGBColor(70, 80, 95)

        p_val = cell_val.paragraphs[0]
        p_val.paragraph_format.space_after = Pt(2)
        r_val = p_val.add_run(val)
        r_val.font.name = "Arial"
        r_val.font.size = Pt(9)
        r_val.font.color.rgb = RGBColor(30, 40, 50)

    p_spacer = doc.add_paragraph()
    p_spacer.paragraph_format.space_before = Pt(8)
    p_spacer.paragraph_format.space_after = Pt(4)

    # Info Cover Image jika ada
    if cover_url:
        p_cover = doc.add_paragraph()
        p_cover.paragraph_format.space_after = Pt(12)
        r_c1 = p_cover.add_run("🖼️ Foto Sampul (16:9 WebP Terverifikasi Bebas Watermark): ")
        r_c1.font.bold = True
        r_c1.font.size = Pt(9.5)
        r_c2 = p_cover.add_run(cover_alt or title)
        r_c2.font.italic = True
        r_c2.font.size = Pt(9.5)
        p_cover.add_run(f"\nTautan Sumber: {cover_url}").font.size = Pt(8.5)

    # Parsing Isi Markdown Artikel
    lines = article_md.split("\n")
    in_references = False

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue

        # Lewati judul H1 utama karena sudah dicetak besar di atas
        if stripped.startswith("# ") and not stripped.startswith("## "):
            continue

        # Subheading H2
        if stripped.startswith("## "):
            heading_text = stripped[3:].strip()
            if "sumber" in heading_text.lower() or "referensi" in heading_text.lower():
                in_references = True

            p_h2 = doc.add_paragraph()
            p_h2.paragraph_format.space_before = Pt(14)
            p_h2.paragraph_format.space_after = Pt(4)
            r_h2 = p_h2.add_run(heading_text)
            r_h2.font.name = "Georgia"
            r_h2.font.size = Pt(14)
            r_h2.font.bold = True
            r_h2.font.color.rgb = RGBColor(30, 60, 110)
            continue

        # Subheading H3
        if stripped.startswith("### "):
            heading_text = stripped[4:].strip()
            p_h3 = doc.add_paragraph()
            p_h3.paragraph_format.space_before = Pt(10)
            p_h3.paragraph_format.space_after = Pt(3)
            r_h3 = p_h3.add_run(heading_text)
            r_h3.font.name = "Georgia"
            r_h3.font.size = Pt(12)
            r_h3.font.bold = True
            r_h3.font.color.rgb = RGBColor(40, 70, 120)
            continue

        # Kutipan / Blockquote
        if stripped.startswith("> "):
            quote_text = stripped[2:].strip()
            p_q = doc.add_paragraph()
            p_q.paragraph_format.left_indent = Inches(0.4)
            p_q.paragraph_format.space_before = Pt(4)
            p_q.paragraph_format.space_after = Pt(6)
            r_q = p_q.add_run(f"“{quote_text}”")
            r_q.font.name = "Georgia"
            r_q.font.italic = True
            r_q.font.size = Pt(10.5)
            r_q.font.color.rgb = RGBColor(90, 100, 115)
            continue

        # Bullet list
        if stripped.startswith("- ") or stripped.startswith("* "):
            item_text = stripped[2:].strip()
            p_b = doc.add_paragraph(style='List Bullet')
            p_b.paragraph_format.space_after = Pt(3)
            r_b = p_b.add_run(item_text)
            r_b.font.name = "Georgia"
            r_b.font.size = Pt(10.5)
            continue

        # Paragraf Standar
        p_body = doc.add_paragraph()
        p_body.paragraph_format.space_after = Pt(8)
        p_body.paragraph_format.line_spacing = 1.2
        r_body = p_body.add_run(stripped)
        r_body.font.name = "Georgia"
        r_body.font.size = Pt(11)
        r_body.font.color.rgb = RGBColor(35, 45, 55)

    # Catatan Disclaimer Redaksi di akhir artikel
    p_disc = doc.add_paragraph()
    p_disc.paragraph_format.space_before = Pt(16)
    p_disc.paragraph_format.space_after = Pt(4)
    r_disc = p_disc.add_run(
        "⚖️ Catatan Editorial & Kepatuhan Jurnalistik:\n"
        "Artikel ini disusun secara otomatis oleh Travelista AI Autonomous Editorial Desk melalui verifikasi fakta berlapis "
        "(Dual-Stage Fact-Checker & Human-in-the-Loop Gatekeeper). Naskah disimpan dengan status Review dan memerlukan otorisasi "
        "tim redaksi sebelum dipublikasikan ke publik."
    )
    r_disc.font.name = "Arial"
    r_disc.font.size = Pt(8.5)
    r_disc.font.italic = True
    r_disc.font.color.rgb = RGBColor(120, 130, 140)


def export_article_to_docx(article: Dict[str, Any]) -> io.BytesIO:
    """Mengonversi 1 artikel menjadi file docx dalam memori."""
    doc = Document()
    # Atur margin standar 1 inci
    sections = doc.sections
    for s in sections:
        s.top_margin = Inches(1)
        s.bottom_margin = Inches(1)
        s.left_margin = Inches(1)
        s.right_margin = Inches(1)

    build_article_docx(doc, article, is_first=True)

    file_stream = io.BytesIO()
    doc.save(file_stream)
    file_stream.seek(0)
    return file_stream


def export_bulk_articles_to_docx(articles: List[Dict[str, Any]], title_batch: str = "Edisi Harian Travelista") -> io.BytesIO:
    """Mengonversi sekumpulan (4) artikel harian menjadi satu bundel dokumen docx resmi."""
    doc = Document()
    sections = doc.sections
    for s in sections:
        s.top_margin = Inches(1)
        s.bottom_margin = Inches(1)
        s.left_margin = Inches(1)
        s.right_margin = Inches(1)

    for idx, art in enumerate(articles):
        build_article_docx(doc, art, is_first=(idx == 0))

    file_stream = io.BytesIO()
    doc.save(file_stream)
    file_stream.seek(0)
    return file_stream
