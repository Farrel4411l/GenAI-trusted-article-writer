import os
import re
from typing import Dict, Any, List, Optional
from markdown_it import MarkdownIt

# Inisialisasi parser Markdown-it dengan ekstensi dasar
_md = MarkdownIt("commonmark", {"html": True, "breaks": True, "typographer": True})


# ── 1. Pemetaan Kategori Resmi Travelista ──────────────────────────────────────
TRAVELISTA_CATEGORIES = {
    "destinasi": {"id": 1, "name_id": "Destinasi", "slug": "destinasi"},
    "kuliner": {"id": 2, "name_id": "Kuliner", "slug": "kuliner"},
    "budaya": {"id": 3, "name_id": "Budaya", "slug": "budaya"},
    "petualangan": {"id": 4, "name_id": "Petualangan", "slug": "petualangan"},
    "hotel-resort": {"id": 5, "name_id": "Hotel & Resort", "slug": "hotel-resort"},
    "tips-perjalanan": {"id": 6, "name_id": "Tips Perjalanan", "slug": "tips-perjalanan"},
}

GENRE_TO_CATEGORY_MAP = {
    # 4 Genre resmi penelitian
    "wisata & destinasi": TRAVELISTA_CATEGORIES["destinasi"],
    "destinasi": TRAVELISTA_CATEGORIES["destinasi"],
    "wisata": TRAVELISTA_CATEGORIES["destinasi"],
    "kuliner nusantara": TRAVELISTA_CATEGORIES["kuliner"],
    "kuliner": TRAVELISTA_CATEGORIES["kuliner"],
    "sejarah & misteri lokal": TRAVELISTA_CATEGORIES["budaya"],
    "sejarah": TRAVELISTA_CATEGORIES["budaya"],
    "budaya & fakta unik": TRAVELISTA_CATEGORIES["budaya"],
    "budaya": TRAVELISTA_CATEGORIES["budaya"],
    # Genre pendukung
    "petualangan": TRAVELISTA_CATEGORIES["petualangan"],
    "hotel & resort": TRAVELISTA_CATEGORIES["hotel-resort"],
    "tips perjalanan": TRAVELISTA_CATEGORIES["tips-perjalanan"],
}


def map_genre_to_category(genre: str) -> Dict[str, Any]:
    """
    Memetakan genre dari Trend Hunter ke kategori resmi database Travelista.
    Default fallback: Kategori 1 (Destinasi).
    """
    key = (genre or "").strip().lower()
    return GENRE_TO_CATEGORY_MAP.get(key, TRAVELISTA_CATEGORIES["destinasi"])


# ── 2. Format & Penanganan Tags ───────────────────────────────────────────────
def slugify_tag(text: str) -> str:
    """Mengubah teks tag menjadi slug yang valid."""
    slug = text.lower().strip()
    slug = re.sub(r"[^a-z0-9\s-]", "", slug)
    slug = re.sub(r"[\s-]+", "-", slug).strip("-")
    return slug or "wisata"


def format_travelista_tags(raw_tags: List[str]) -> List[Dict[str, str]]:
    """
    Mengubah list tag mentah menjadi list objek tag terstruktur
    yang siap dihubungkan ke tabel `tags` dan `article_tags` di Travelista.
    Contoh: ["kawah-ijen", "banyuwangi"] -> [{"name": "Kawah Ijen", "slug": "kawah-ijen"}]
    """
    formatted: List[Dict[str, str]] = []
    seen_slugs = set()

    for item in raw_tags:
        if not item or not isinstance(item, str):
            continue
        clean_item = item.strip()
        slug = slugify_tag(clean_item)
        if slug in seen_slugs:
            continue
        seen_slugs.add(slug)

        # Nama tag yang rapi (title case jika awalnya berupa slug)
        display_name = clean_item.replace("-", " ").title()
        formatted.append({"name": display_name, "slug": slug})

    return formatted


# ── 3. Converter Markdown -> HTML & TipTap JSON ──────────────────────────────
def markdown_to_html(markdown_text: str) -> str:
    """
    Mengonversi Markdown artikel ke format HTML standar
    yang siap dibaca oleh Nuxt 4 (apps/magazine).
    """
    if not markdown_text:
        return ""
    html = _md.render(markdown_text)
    # Hapus tag H1 pertama jika itu judul artikel (karena judul sudah ada di field `title`)
    html = re.sub(r"^\s*<h1>.*?</h1>\s*", "", html, count=1, flags=re.DOTALL)
    return html.strip()


def markdown_to_tiptap_json(markdown_text: str) -> Dict[str, Any]:
    """
    Mengonversi Markdown artikel ke struktur TipTap JSON Document (apps/cms).
    Menghasilkan AST dokumen standar TipTap yang valid.
    """
    if not markdown_text:
        return {"type": "doc", "content": []}

    tokens = _md.parse(markdown_text, {})
    doc_content: List[Dict[str, Any]] = []

    i = 0
    while i < len(tokens):
        token = tokens[i]

        if token.type == "heading_open":
            level = int(token.tag[1]) if len(token.tag) > 1 and token.tag[1].isdigit() else 2
            # Skip H1 pertama karena judul disimpan di kolom terpisah `title`
            if level == 1 and not doc_content:
                # Lewati heading_open, inline, heading_close
                i += 3
                continue

            inline_token = tokens[i + 1] if i + 1 < len(tokens) else None
            text = inline_token.content if inline_token else ""
            if text.strip():
                doc_content.append({
                    "type": "heading",
                    "attrs": {"level": level},
                    "content": [{"type": "text", "text": text.strip()}]
                })
            i += 3
            continue

        elif token.type == "paragraph_open":
            inline_token = tokens[i + 1] if i + 1 < len(tokens) else None
            content_nodes = []
            if inline_token and inline_token.children:
                current_link: Optional[str] = None
                for child in inline_token.children:
                    if child.type == "link_open":
                        current_link = child.attrGet("href")
                    elif child.type == "link_close":
                        current_link = None
                    elif child.type == "text" and child.content:
                        node: Dict[str, Any] = {"type": "text", "text": child.content}
                        if current_link:
                            node["marks"] = [{"type": "link", "attrs": {"href": current_link}}]
                        content_nodes.append(node)
                    elif child.type == "code_inline" and child.content:
                        content_nodes.append({
                            "type": "text",
                            "text": child.content,
                            "marks": [{"type": "code"}]
                        })
            elif inline_token and inline_token.content:
                content_nodes.append({"type": "text", "text": inline_token.content})

            if content_nodes:
                doc_content.append({
                    "type": "paragraph",
                    "content": content_nodes
                })
            i += 3
            continue

        elif token.type == "bullet_list_open" or token.type == "ordered_list_open":
            list_type = "bulletList" if token.type == "bullet_list_open" else "orderedList"
            list_items = []
            close_type = "bullet_list_close" if token.type == "bullet_list_open" else "ordered_list_close"
            i += 1
            while i < len(tokens) and tokens[i].type != close_type:
                if tokens[i].type == "list_item_open":
                    i += 1
                    item_paragraphs = []
                    while i < len(tokens) and tokens[i].type != "list_item_close":
                        if tokens[i].type == "paragraph_open":
                            inline_t = tokens[i + 1] if i + 1 < len(tokens) else None
                            txt = inline_t.content if inline_t else ""
                            if txt.strip():
                                item_paragraphs.append({
                                    "type": "paragraph",
                                    "content": [{"type": "text", "text": txt.strip()}]
                                })
                            i += 3
                            continue
                        i += 1
                    if item_paragraphs:
                        list_items.append({"type": "listItem", "content": item_paragraphs})
                else:
                    i += 1
            if list_items:
                doc_content.append({"type": list_type, "content": list_items})
            i += 1
            continue

        i += 1

    return {"type": "doc", "content": doc_content}


# ── 4. Penulis / Profil Bot AI Default ─────────────────────────────────────────
DEFAULT_TRAVELISTA_BOT_AUTHOR = {
    # Default UUID placeholder jika user belum memasukkan UUID profil di .env
    "id": os.getenv("TRAVELISTA_AUTHOR_ID", "00000000-0000-0000-0000-000000000001"),
    "full_name": "Travelista AI Editorial",
    "username": "travelista-ai",
    "role": "writer",
}


def get_default_author() -> Dict[str, Any]:
    """Mengambil konfigurasi profil penulis AI bot Travelista."""
    return DEFAULT_TRAVELISTA_BOT_AUTHOR


# ── 5. Builder Payload Lengkap Travelista ──────────────────────────────────────
def build_travelista_ready_payload(
    final_title: str,
    slug: str,
    genre: str,
    article_markdown: str,
    meta_description: str,
    raw_tags: List[str],
    references: List[Dict[str, str]],
    author_id: Optional[str] = None,
    cover_image_url: Optional[str] = None,
    cover_image_alt: Optional[str] = None,
    status: str = "review",  # 'draft' | 'review' (aman untuk redaksi)
) -> Dict[str, Any]:
    """
    Menyusun payload artikel yang 100% kompatibel dengan skema tabel
    `public.articles`, `public.categories`, dan `public.tags` milik Travelista 2026.
    """
    category = map_genre_to_category(genre)
    formatted_tags = format_travelista_tags(raw_tags)
    content_html = markdown_to_html(article_markdown)
    content_json = markdown_to_tiptap_json(article_markdown)

    # Estimasi waktu baca: rata-rata 200 kata/menit
    word_count = len(article_markdown.split())
    read_time_minutes = max(1, round(word_count / 200))

    target_author_id = author_id or os.getenv("TRAVELISTA_AUTHOR_ID", DEFAULT_TRAVELISTA_BOT_AUTHOR["id"])

    # 1. Objek tabel `articles` (kolom langsung di Supabase Travelista)
    article_db_record = {
        "title": final_title,
        "slug": slug,
        "excerpt": meta_description[:200] if meta_description else None,
        "content_html": content_html,
        "content_json": content_json,
        "cover_image_url": cover_image_url,  # Ditahan sesuai permintaan, default None
        "cover_image_alt": cover_image_alt,
        "category_id": category["id"],
        "author_id": target_author_id,
        "status": status,
        "locale": "id",
        "is_featured": False,
        "is_breaking": False,
        "meta_title": final_title,
        "meta_description": meta_description,
        "read_time_minutes": read_time_minutes,
        "published_at": None,  # Belum di-publish, siap untuk review redaksi
    }

    # 2. Paket lengkap termasuk relasi tag dan audit
    return {
        "schema_version": "2.0-travelista-monorepo-ready",
        "compatibility": "travelista-2026",
        "category": category,
        "tags": formatted_tags,
        "author": {
            "id": target_author_id,
            "full_name": DEFAULT_TRAVELISTA_BOT_AUTHOR["full_name"],
            "role": DEFAULT_TRAVELISTA_BOT_AUTHOR["role"],
        },
        "articles_record": article_db_record,
        "references": references,
        "notes": {
            "cover_image_reminder": "Riset cover image ditahan sementara sesuai arahan user.",
            "workflow_step": "Siap di-review oleh Editor / Admin di CMS Travelista.",
        }
    }
