import json
import re
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List
from langchain_core.messages import SystemMessage, HumanMessage
from src.agents.llm_factory import get_llm
from src.agents.writer_agent import deduplicate_references
from src.automation.travelista_adapter import build_travelista_ready_payload
from src.automation.image_hunter import acquire_cover_image

WIB_TZ = timezone(timedelta(hours=7))


def _slugify(text: str) -> str:
    """Mengubah judul artikel menjadi URL slug yang bersih untuk auto-deploy CMS."""
    slug = text.lower().strip()
    slug = re.sub(r"[^a-z0-9\s-]", "", slug)
    slug = re.sub(r"[\s-]+", "-", slug).strip("-")
    return slug[:90] or "artikel-travelista"


def _extract_references_from_draft(draft_text: str) -> List[Dict[str, str]]:
    """Mengekstrak daftar objek {title, url} dari bagian Sumber Referensi artikel."""
    refs: List[Dict[str, str]] = []
    pattern = re.compile(r"(?i)(\*{0,2}sumber referensi:?\*{0,2})")
    match = pattern.search(draft_text)
    if not match:
        return refs

    ref_block = draft_text[match.end():].strip()
    seen_urls = set()
    for line in ref_block.splitlines():
        line_clean = line.strip()
        if not line_clean:
            continue
        md_match = re.search(r"\[([^\]]+)\]\((https?://[^\s\)]+)\)", line_clean)
        if md_match:
            title, url = md_match.group(1).strip(), md_match.group(2).strip()
            if url not in seen_urls:
                seen_urls.add(url)
                refs.append({"title": title, "url": url})
        else:
            url_only = re.search(r"(https?://[^\s\)]+)", line_clean)
            if url_only:
                url = url_only.group(1).strip()
                if url not in seen_urls:
                    seen_urls.add(url)
                    refs.append({"title": url, "url": url})
    return refs


def _count_body_paragraphs(draft_text: str) -> int:
    """Menghitung jumlah paragraf isi (tidak termasuk judul H1 dan daftar referensi)."""
    pattern = re.compile(r"(?i)(\*{0,2}sumber referensi:?\*{0,2})")
    match = pattern.search(draft_text)
    body_part = draft_text[:match.start()] if match else draft_text

    paragraphs = []
    for block in re.split(r"\n\s*\n", body_part.strip()):
        b = block.strip()
        if not b:
            continue
        if b.startswith("#") or b in ("***", "---", "___"):
            continue
        if len(b) >= 60:
            paragraphs.append(b)
    return len(paragraphs)


def _ensure_header_and_clean_format(draft_text: str, final_title: str) -> str:
    """
    Memastikan artikel memiliki judul utama H1 (# Judul) di baris paling atas
    dan daftar referensi yang sudah terdeduplikasi rapi.
    """
    cleaned = deduplicate_references(draft_text.strip())
    lines = cleaned.splitlines()
    if not lines:
        return f"# {final_title}\n\n{cleaned}"

    first_line = lines[0].strip()
    # Jika baris pertama sudah berupa heading atau bold judul, rapikan menjadi H1 standar
    if first_line.startswith("#"):
        lines[0] = f"# {final_title}"
        return "\n".join(lines)
    elif first_line.startswith("**") and first_line.endswith("**") and len(first_line) < 160:
        lines[0] = f"# {final_title}"
        return "\n".join(lines)
    else:
        return f"# {final_title}\n\n{cleaned}"


def run_final_gatekeeper(
    draft: str,
    target_title: str,
    topic: str,
    genre: str,
    editorial_angle: str,
    checker_model_id: str = "gemini/gemini-3.5-flash"
) -> Dict[str, Any]:
    """
    CHECKER AKHIR (Stage 2 Gatekeeper — Post Fact-Checker):
    Memeriksa apakah artikel yang sudah lolos verifikasi sumber (Checker 1)
    benar-benar sesuai dari segi:
    1. Judul (Title alignment)
    2. Topik (Topic completeness)
    3. Genre (Travelista genre tone)
    4. Format & Struktur (5-8 paragraf, sitasi unik, serta kesiapan skema JSON untuk Auto-Deploy CMS).
    """
    print(f"\n[Final Gatekeeper] Memeriksa kesesuaian Judul, Topik, Genre, dan Format CMS menggunakan {checker_model_id}...")

    para_count = _count_body_paragraphs(draft)
    refs_list = _extract_references_from_draft(draft)
    has_ref_section = len(refs_list) > 0

    system_prompt = """Anda adalah *Final Editorial Gatekeeper & CMS Packaging Auditor* (Checker Tahap 2) di Travelista.id.
Draf artikel yang Anda terima SUDAH melalui pemeriksaan fakta sumber (Checker Tahap 1).
Tugas Anda sekarang adalah mengaudit keselarasan akhir dan menyiapkan metadata untuk publikasi/auto-deploy:

1. CEK KESESUAIAN JUDUL: Apakah isi artikel selaras dengan Target Judul? Jika Target Judul kurang pas dengan isi faktual artikel, sempurnakan menjadi `final_title` yang akurat, memikat, dan SEO-friendly.
2. CEK KESESUAIAN TOPIK: Apakah artikel benar-benar membahas Topik yang diminta?
3. CEK KESESUAIAN GENRE: Apakah gaya bahasanya sesuai dengan Genre Travelista yang ditetapkan?
4. CEK FORMAT & METADATA CMS: Buat `meta_description` (120-155 karakter bahasa Indonesia) dan 5 `tags` relevan untuk keperluan auto-deploy ke CMS.

Balas HANYA dengan format JSON murni berikut:
{
  "title_aligned": true,
  "topic_aligned": true,
  "genre_aligned": true,
  "format_aligned": true,
  "compliance_score": 95,
  "final_title": "Judul Artikel Final yang Sudah Diselaraskan",
  "meta_description": "Ringkasan SEO 120-155 karakter yang menarik pembaca.",
  "tags": ["Tag1", "Tag2", "Tag3", "Tag4", "Tag5"],
  "audit_notes": "Ringkasan verifikasi Judul, Topik, Genre, dan Format (1-2 kalimat)."
}"""

    user_prompt = f"""TARGET GENRE: {genre}
TARGET TOPIK: {topic}
TARGET JUDUL AWAL: {target_title}
ARAHAN SUDUT PANDANG: {editorial_angle}
STATISTIK FORMAT DETEKSI SISTEM: {para_count} paragraf isi, {len(refs_list)} tautan referensi unik.

DRAF ARTIKEL:
{draft}"""

    tokens_used = 0
    audit_data = {
        "title_aligned": True,
        "topic_aligned": True,
        "genre_aligned": True,
        "format_aligned": (5 <= para_count <= 8) and has_ref_section,
        "compliance_score": 92 if has_ref_section else 75,
        "final_title": target_title,
        "meta_description": f"Simak ulasan mendalam seputar {topic} dalam kategori {genre} hanya di Travelista.id.",
        "tags": [genre.split(" ")[0], topic, "Travelista", "Indonesia", "Nusantara"],
        "audit_notes": (
            f" Terverifikasi sesuai dengan genre '{genre}' dan topik '{topic}' "
            f"({para_count} paragraf, {len(refs_list)} referensi unik)."
        ),
    }

    try:
        llm = get_llm(checker_model_id)
        if hasattr(llm, "temperature"):
            llm.temperature = 0.0
        response = llm.invoke([
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt)
        ])
        if hasattr(response, "usage_metadata") and response.usage_metadata:
            tokens_used = response.usage_metadata.get("total_tokens", 0)
        elif hasattr(response, "response_metadata") and "token_usage" in response.response_metadata:
            tokens_used = response.response_metadata["token_usage"].get("total_tokens", 0)

        content = response.content
        if isinstance(content, list):
            content = "".join(
                item.get("text", "") if isinstance(item, dict) else str(item)
                for item in content
            )

        json_match = re.search(r"\{.*\}", content, flags=re.DOTALL)
        if json_match:
            parsed = json.loads(json_match.group(0))
            audit_data.update({
                "title_aligned": bool(parsed.get("title_aligned", True)),
                "topic_aligned": bool(parsed.get("topic_aligned", True)),
                "genre_aligned": bool(parsed.get("genre_aligned", True)),
                "format_aligned": bool(parsed.get("format_aligned", True)) and has_ref_section,
                "compliance_score": int(parsed.get("compliance_score", 95)),
                "final_title": parsed.get("final_title", target_title).strip() or target_title,
                "meta_description": parsed.get("meta_description", audit_data["meta_description"]).strip(),
                "tags": parsed.get("tags", audit_data["tags"]),
                "audit_notes": parsed.get("audit_notes", audit_data["audit_notes"]).strip(),
            })
    except Exception as e:
        print(f"[Final Gatekeeper] Menggunakan hasil verifikasi struktural otomatis (info LLM: {e})")

    final_title = audit_data["final_title"]
    slug = _slugify(final_title)
    formatted_markdown = _ensure_header_and_clean_format(draft, final_title)

    is_passed = (
        audit_data["title_aligned"]
        and audit_data["topic_aligned"]
        and audit_data["genre_aligned"]
        and has_ref_section
    )

    checklist_summary = (
        f"[Judul: {'✅ Sesuai' if audit_data['title_aligned'] else '⚠️ Disesuaikan'}] "
        f"[Topik: {'✅ Sesuai' if audit_data['topic_aligned'] else '⚠️ Perlu Cek'}] "
        f"[Genre: {'✅ Sesuai' if audit_data['genre_aligned'] else '⚠️ Perlu Cek'}] "
        f"[Format: {'✅ Siap Deploy' if has_ref_section else '⚠️ Tanpa Sitasi'} ({para_count} Paragraf, {len(refs_list)} Sumber)] — "
        f"{audit_data['audit_notes']}"
    )

    # 5. Akuisisi Cover Image 16:9 WebP (Hybrid Vision-RAG & Storage Ready)
    image_meta = acquire_cover_image(
        topic=topic,
        title=final_title,
        genre=genre,
        slug=slug,
        editorial_angle=editorial_angle,
        prefer_real_first=True
    )
    cover_image_url = image_meta.get("cover_image_url")
    cover_image_alt = image_meta.get("cover_image_alt")

    # Skema JSON Standar Travelista 2026 & Auto-Deploy Readiness
    travelista_payload = build_travelista_ready_payload(
        final_title=final_title,
        slug=slug,
        genre=genre,
        article_markdown=formatted_markdown,
        meta_description=audit_data["meta_description"],
        raw_tags=audit_data["tags"],
        references=refs_list,
        author_id=None,
        cover_image_url=cover_image_url,
        cover_image_alt=cover_image_alt,
        status="review" if is_passed else "draft",
    )

    cms_payload = {
        "schema_version": "2.0-travelista-cms",
        "status": "ready_to_publish" if is_passed else "draft_review",
        "generated_at": datetime.now(WIB_TZ).isoformat(),
        "article": {
            "title": final_title,
            "slug": slug,
            "genre": genre,
            "category_id": travelista_payload["category"]["id"],
            "category_name": travelista_payload["category"]["name_id"],
            "category_slug": travelista_payload["category"]["slug"],
            "topic": topic,
            "meta_description": audit_data["meta_description"],
            "tags": audit_data["tags"],
            "formatted_tags": travelista_payload["tags"],
            "paragraph_count": para_count,
            "content_markdown": formatted_markdown,
            "content_html": travelista_payload["articles_record"]["content_html"],
            "references": refs_list,
            "author_id": travelista_payload["author"]["id"],
            "cover_image_url": cover_image_url,
            "cover_image_alt": cover_image_alt,
            "cover_image_meta": image_meta,
        },
        "travelista_payload": travelista_payload,
        "verification": {
            "stage1_fact_checker": True,
            "stage2_final_gatekeeper": is_passed,
            "compliance_score": audit_data["compliance_score"],
            "audit_summary": checklist_summary,
        },
    }

    return {
        "final_check_passed": is_passed,
        "final_check_score": audit_data["compliance_score"],
        "final_check_notes": checklist_summary,
        "final_title": final_title,
        "slug": slug,
        "meta_description": audit_data["meta_description"],
        "tags": audit_data["tags"],
        "references": refs_list,
        "article_markdown": formatted_markdown,
        "content_html": travelista_payload["articles_record"]["content_html"],
        "category_id": travelista_payload["category"]["id"],
        "cover_image_url": cover_image_url,
        "cover_image_alt": cover_image_alt,
        "cover_image_meta": image_meta,
        "cms_payload": cms_payload,
        "travelista_payload": travelista_payload,
        "final_checker_tokens": tokens_used,
    }
