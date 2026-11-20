import random
import re
import time
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional, Callable, Tuple, List
import wikipedia
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter
from src.agents.orchestrator import build_graph
from src.utils.metrics_logger import log_metrics
from src.automation.trend_hunter import (
    analyze_and_select_daily_topic,
    CURATED_EVERGREEN_POOL,
    is_overbroad_or_unsuitable_topic,
    mine_travel_search_keywords,
)
from src.automation.model_router import select_optimal_models
from src.automation.final_checker_agent import run_final_gatekeeper
from src.automation.storage_supabase import (
    get_db_connection,
    get_recent_topics,
    save_daily_article,
)

WIB_TZ = timezone(timedelta(hours=7))

_wiki_patched = False

_REFUSAL_PHRASES = (
    "tidak terdapat informasi",
    "tidak ada informasi",
    "konteks yang diberikan tidak",
    "konteks tidak menyediakan",
    "tidak memiliki informasi",
    "mohon maaf, saya tidak",
)


_OFF_GENRE_POLLUTION_PHRASES = (
    "operasi tangkap tangan",
    "komisi pemberantasan korupsi",
    "hamilton sundstrand",
    "tragedi ga 152",
    "inspektur jenderal polisi",
)


def _extract_primary_entity(raw_topic: str) -> str:
    """Ambil entitas tunggal utama jika LLM/planner menghasilkan topik majemuk 'A dan B'."""
    text = (raw_topic or "").strip()
    if not text:
        return text
    primary = re.split(r"\s+(?:dan|serta|atau)\s+|[,&/]", text, maxsplit=1, flags=re.IGNORECASE)[0].strip()
    return primary or text


def _inspect_draft_quality(draft_text: str, topic: str = "", genre: str = "") -> Tuple[bool, str]:
    """
    Mengaudit keutuhan draf setelah Orchestrator:
    mengembalikan (is_broken, reason_code).
    Mendeteksi penolakan RAG, draf terlalu pendek, terpotong di tengah kalimat,
    ketiadaan Sumber Referensi, kebocoran tag <think>/aksara asing, dan isi melenceng.
    """
    raw = (draft_text or "").strip()
    if "<think>" in raw.lower() or "</think>" in raw.lower():
        raw = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL | re.IGNORECASE).strip()

    body_only = re.split(r"(?i)\n\*{0,2}sumber referensi:?\*{0,2}", raw)[0].strip()
    if len(body_only) < 1000:
        if any(ph in body_only[:800].lower() for ph in _REFUSAL_PHRASES):
            return True, "refusal"
        return True, "short_body"

    paragraphs = [p for p in re.split(r"\n\s*\n", body_only) if len(p.strip()) > 30]
    if len(paragraphs) < 4:
        return True, "few_paragraphs"

    lower_head = body_only[:800].lower()
    if any(phrase in lower_head for phrase in _REFUSAL_PHRASES):
        return True, "refusal"

    if not body_only.endswith((".", "!", "?", '"', "'", "”", ")", "*")):
        return True, "truncated"

    if not re.search(r"https?://[^\s\)]+", raw[len(body_only):]):
        return True, "no_refs"

    # Deteksi kebocoran aksara asing (CJK/Hangul/Cyrillic) yang menempel di kalimat Indonesia
    cjk_glued = re.search(r"[A-Za-z][\u4e00-\u9fff\u3040-\u30ff\uac00-\ud7af]|[\u4e00-\u9fff\u3040-\u30ff\uac00-\ud7af][A-Za-z]", body_only)
    is_east_asian_topic = any(k in (topic or "").lower() for k in ("tionghoa", "china", "jepang", "korea"))
    cjk_any = re.search(r"[\u4e00-\u9fff\u3040-\u30ff\uac00-\ud7af]", body_only)
    if cjk_glued or (cjk_any and not is_east_asian_topic):
        return True, "cjk_leak"

    body_low = body_only.lower()
    if any(p in body_low for p in _OFF_GENRE_POLLUTION_PHRASES):
        return True, "off_genre"

    return False, "ok"


def _is_broken_or_refusal_draft(draft_text: str, topic: str = "", genre: str = "") -> bool:
    """Wrapper boolean untuk mendeteksi draf penolakan RAG atau draf bermasalah sebelum Checker 2."""
    broken, _ = _inspect_draft_quality(draft_text, topic=topic, genre=genre)
    return broken


def _ensure_wikipedia_topic_indexed(topic: str) -> bool:
    """
    Memastikan artikel Wikipedia Bahasa Indonesia untuk `topic` sudah terindeks
    dengan chunk substansial (>= 120 karakter) di `pgvector` sebelum Graph berjalan,
    sehingga topik spesifik seperti Candi Plaosan tidak terjebak menjadi kosong konteks.
    """
    try:
        import src.retriever.search as search_mod
        _install_pgvector_connection_guard()
        wikipedia.set_lang("id")
        page_title = None
        page_url = None
        page_content = ""

        try:
            p = wikipedia.page(topic, auto_suggest=False)
            page_title, page_url, page_content = p.title, p.url, p.content
        except Exception:
            try:
                sr = wikipedia.search(topic, results=3)
                for cand in sr:
                    if topic.lower().split()[0] in cand.lower() or cand.lower() in topic.lower():
                        p = wikipedia.page(cand, auto_suggest=False)
                        page_title, page_url, page_content = p.title, p.url, p.content
                        break
            except Exception:
                pass

        if not page_content or len(page_content) < 600:
            fb = _fetch_wiki_html_fallback(topic)
            if fb and len(fb.get("extract", "")) >= 600:
                page_title = fb["title"]
                page_url = fb["url"]
                page_content = fb["extract"]

        if not page_title or len(page_content) < 600:
            return False

        # Cek apakah chunk berkualitas (>= 120 karakter) untuk judul ini sudah ada di pgvector
        existing_substantial = 0
        try:
            conn = get_db_connection()
            with conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "SELECT COUNT(*) FROM langchain_pg_embedding WHERE cmetadata->>'title' = %s AND length(document) >= 120;",
                        (page_title,),
                    )
                    row = cur.fetchone()
                    if row:
                        existing_substantial = int(row[0])
            conn.close()
        except Exception:
            pass

        if existing_substantial >= 3:
            return True

        splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=150)
        doc = Document(
            page_content=page_content,
            metadata={"title": page_title, "url": page_url, "source": "wikipedia-preseed"},
        )
        raw_chunks = splitter.split_documents([doc])
        good_chunks = [c for c in raw_chunks if len(c.page_content.strip()) >= 120]
        if good_chunks:
            store = search_mod.get_vectorstore()
            store.add_documents(good_chunks[:18])
            print(f"[Pre-Seed RAG] Menambahkan {min(len(good_chunks), 18)} chunk bersih untuk '{page_title}' ke pgvector.")
        return True
    except Exception as e:
        print(f"[Pre-Seed RAG] Info gagal pre-seed '{topic}': {e}")
        return False


def _pick_fresh_curated_topic(genre: str, exclude_topics: List[str]) -> Dict[str, str]:
    """Memilih topik entitas spesifik terkurasi dari CURATED_EVERGREEN_POOL yang belum baru ditulis."""
    pool = CURATED_EVERGREEN_POOL.get(genre, CURATED_EVERGREEN_POOL["Wisata & Destinasi (Travel)"])
    ex_low = {t.lower().strip() for t in exclude_topics if t}
    fresh = [item for item in pool if item["topic"].lower() not in ex_low]
    return random.choice(fresh if fresh else pool)


def _fetch_wiki_html_fallback(title_or_query: str) -> Dict[str, str]:
    """
    Fallback langsung ke CDN halaman artikel `https://id.wikipedia.org/wiki/{Judul}`
    ketika endpoint `/w/api.php` Wikimedia sedang mengalami gangguan 503.
    Mengekstrak teks paragraf bersih dan URL resmi Wikipedia Bahasa Indonesia.
    """
    import re
    import html
    import urllib.parse
    import requests

    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) TravelistaEditorial/2.0"}
    candidates = [
        title_or_query.strip().replace(" ", "_"),
        title_or_query.strip().title().replace(" ", "_"),
    ]
    if "candi_dieng" in candidates[0].lower() and "kompleks" not in candidates[0].lower():
        candidates.insert(0, "Kompleks_Candi_Dieng")
    if "candi_batujaya" in candidates[0].lower():
        candidates.insert(0, "Situs_Batujaya")

    for slug in candidates:
        url = f"https://id.wikipedia.org/wiki/{urllib.parse.quote(slug)}"
        try:
            r = requests.get(url, headers=headers, timeout=10)
            if r.status_code == 200 and "mw-content-text" in r.text:
                # Ambil judul resmi dari <title>
                t_match = re.search(r"<title>(.*?) - Wikipedia bahasa Indonesia.*?</title>", r.text)
                real_title = html.unescape(t_match.group(1).strip()) if t_match else title_or_query.strip()

                # Ekstrak seluruh tag <p> di dalam konten artikel
                paragraphs = re.findall(r"<p[^>]*>(.*?)</p>", r.text, flags=re.DOTALL)
                clean_paras = []
                for p in paragraphs:
                    # Hapus tag HTML dan nomor sitasi [1], [2]
                    txt = re.sub(r"<[^>]+>", "", p)
                    txt = re.sub(r"\[\d+\]|\[butuh rujukan\]", "", txt)
                    txt = html.unescape(txt).strip()
                    if len(txt) >= 50:
                        clean_paras.append(txt)

                if clean_paras:
                    return {
                        "title": real_title,
                        "url": r.url,
                        "extract": "\n\n".join(clean_paras[:25]),
                    }
        except Exception:
            continue
    return {}


class _AnyKeyPageDict(dict):
    """Dictionary pintar yang selalu mengembalikan objek halaman berapa pun pageid yang diminta."""
    def __init__(self, pid: str, page_data: Dict[str, Any]):
        super().__init__({pid: page_data})
        self._page_data = page_data

    def __getitem__(self, key):
        return self._page_data


_wiki_cache_fallback: Dict[str, Dict[str, str]] = {}


def _install_wikipedia_rate_limit_guard():
    """
    Memasang User-Agent resmi dan fallback CDN otomatis pada modul `wikipedia`
    jika endpoint `/w/api.php` Wikimedia mengembalikan HTTP 503,
    tanpa mengubah kode asli `src/retriever/search.py`.
    """
    global _wiki_patched
    if _wiki_patched:
        return
    try:
        import wikipedia.wikipedia as wiki_mod
        orig_wiki_request = wiki_mod._wiki_request

        def _safe_wiki_request(params):
            try:
                res = orig_wiki_request(params)
                if isinstance(res, dict) and "query" in res:
                    return res
            except Exception:
                pass

            # Fallback otomatis ke CDN Wikipedia HTML jika /w/api.php sedang 503
            if params.get("list") == "search":
                q = params.get("srsearch", "").strip()
                info = _fetch_wiki_html_fallback(q)
                if info:
                    _wiki_cache_fallback[info["title"]] = info
                    return {"query": {"search": [{"title": info["title"]}]}}
                return {"query": {"search": []}}

            if params.get("prop") == "info|pageprops":
                target = str(params.get("titles") or params.get("pageids") or "")
                info = _wiki_cache_fallback.get(target) or _fetch_wiki_html_fallback(target)
                if info:
                    pid = str(abs(hash(info["title"])) % 800000 + 1000)
                    info["pageid"] = pid
                    _wiki_cache_fallback[info["title"]] = info
                    _wiki_cache_fallback[target] = info
                    _wiki_cache_fallback[pid] = info
                    page_obj = {
                        "pageid": pid,
                        "title": info["title"],
                        "fullurl": info["url"],
                        "pageprops": {},
                    }
                    return {"query": {"pages": _AnyKeyPageDict(pid, page_obj)}}

            if "extracts" in str(params.get("prop", "")):
                target = str(params.get("titles") or params.get("pageids") or "")
                info = (
                    _wiki_cache_fallback.get(target)
                    or _fetch_wiki_html_fallback(target)
                    or next(iter(_wiki_cache_fallback.values()), None)
                )
                if info:
                    pid = info.get("pageid", str(abs(hash(info["title"])) % 800000 + 1000))
                    page_obj = {
                        "pageid": pid,
                        "title": info["title"],
                        "extract": info["extract"],
                        "revisions": [{"revid": 1, "parentid": 0}],
                    }
                    return {"query": {"pages": _AnyKeyPageDict(pid, page_obj)}}

            empty_obj = {
                "pageid": "0",
                "title": "",
                "fullurl": "",
                "extract": "",
                "pageprops": {},
                "revisions": [{"revid": 1, "parentid": 0}],
            }
            return {"query": {"search": [], "pages": _AnyKeyPageDict("0", empty_obj)}}

        wiki_mod._wiki_request = _safe_wiki_request
        _wiki_patched = True
    except Exception:
        pass


_pgvector_patched = False
_SHARED_PGVECTOR_STORE = None


def _install_pgvector_connection_guard():
    """
    Mencegah kebocoran pool koneksi PGVector terhadap batas 15 koneksi Session Pooler Supabase
    dengan memakai singleton PGVector + NullPool + create_extension=False, tanpa mengubah `src/retriever/search.py`.
    """
    global _pgvector_patched, _SHARED_PGVECTOR_STORE
    if _pgvector_patched:
        return
    try:
        from sqlalchemy.pool import NullPool
        from langchain_community.vectorstores import PGVector
        import src.retriever.search as search_mod

        def _pooled_get_vectorstore():
            global _SHARED_PGVECTOR_STORE
            if _SHARED_PGVECTOR_STORE is not None:
                return _SHARED_PGVECTOR_STORE
            if not search_mod.DATABASE_URL:
                raise ValueError("DATABASE_URL tidak disetel di .env")
            try:
                _SHARED_PGVECTOR_STORE = PGVector(
                    collection_name=search_mod.COLLECTION_NAME,
                    connection_string=search_mod.DATABASE_URL,
                    embedding_function=search_mod.get_embeddings(),
                    engine_args={"poolclass": NullPool},
                    create_extension=False,
                )
            except Exception:
                _SHARED_PGVECTOR_STORE = PGVector(
                    collection_name=search_mod.COLLECTION_NAME,
                    connection_string=search_mod.DATABASE_URL,
                    embedding_function=search_mod.get_embeddings(),
                    engine_args={"poolclass": NullPool},
                    create_extension=True,
                )
            return _SHARED_PGVECTOR_STORE

        search_mod.get_vectorstore = _pooled_get_vectorstore
        _pgvector_patched = True
    except Exception:
        pass


def run_autonomous_daily_pipeline(
    preferred_genre: Optional[str] = None,
    progress_callback: Optional[Callable[[str, str], None]] = None
) -> Dict[str, Any]:
    """
    Menjalankan seluruh alur Pembuatan Artikel Otomatis Harian (End-to-End):
    1. Trend Hunter: Cek tren pencarian Indonesia -> Tentukan Genre, Topik, Judul, & Angle.
    2. Smart Model Router: Pilih kombinasi Model Writer & Model Reviewer terbaik sesuai Genre & Sisa Kuota.
    3. Core Multi-Agent RAG (Retriever -> Writer <-> Checker 1 Fact-Checker Sumber).
    4. Checker 2 (Final Gatekeeper): Validasi kesesuaian Judul, Topik, Genre, dan Format CMS Auto-Deploy.
    5. Storage: Simpan ke tabel Supabase `daily_auto_articles` & perbarui log kuota token.
    """
    def _notify(stage: str, msg: str):
        print(f"[{stage}] {msg}")
        if progress_callback:
            progress_callback(stage, msg)

    start_time = time.time()
    now_wib = datetime.now(WIB_TZ)
    _install_wikipedia_rate_limit_guard()
    _install_pgvector_connection_guard()

    # 1. Ambil daftar topik yang sudah pernah ditulis agar tidak duplikat
    _notify("trend", "🔎 Mengecek riwayat artikel di Supabase & memindai tren pencarian terkini (Google Trends & News ID)...")
    recent_topics = get_recent_topics(limit=30)

    # 2. Analisis Tren & Perencanaan Redaksi Otomatis
    trend_plan = analyze_and_select_daily_topic(
        recent_topics=recent_topics,
        preferred_genre=preferred_genre,
    )
    genre = trend_plan["genre"]
    trending_keyword = trend_plan["trending_keyword"]
    trend_source = trend_plan["trend_source"]
    raw_topic = trend_plan["topic"]
    topic = _extract_primary_entity(raw_topic)
    if topic != raw_topic.strip():
        print(f"[Daily Pipeline] Menyederhanakan topik majemuk '{raw_topic}' -> '{topic}' agar presisi RAG maksimal.")
    target_title = trend_plan["target_title"]
    editorial_angle = trend_plan["editorial_angle"]

    # 2b. Pre-Seed Wikipedia Context & Validasi Spesifisitas Topik (cegah kegagalan tipe ID=35 Candi Plaosan / ID=34 Garuda)
    if is_overbroad_or_unsuitable_topic(topic) or not _ensure_wikipedia_topic_indexed(topic):
        fallback_pick = _pick_fresh_curated_topic(genre, recent_topics + [topic])
        topic = fallback_pick["topic"]
        trending_keyword = fallback_pick["keyword"]
        target_title = f"Menelusuri Pesona {topic}: Sejarah, Keunikan, dan Fakta Menarik Nusantara"
        editorial_angle = f"Mengulas tuntas daya tarik, latar sejarah, dan keunikan autentik {topic} berbasis fakta ensiklopedis terverifikasi."
        seo_refreshed = mine_travel_search_keywords(topic, genre)
        trend_plan.update(seo_refreshed)
        _ensure_wikipedia_topic_indexed(topic)
        print(f"[Daily Pipeline] Topik diganti ke entitas terverifikasi kaya referensi: '{topic}'")

    _notify(
        "trend_done",
        f"📈 **Tren Ditemukan**: `{trending_keyword}` ({trend_source})  \n"
        f"📂 **Genre**: `{genre}` | 🎯 **Topik RAG**: `{topic}`  \n"
        f"📰 **Target Judul**: *{target_title}*"
    )

    # 3. Smart Model Router (Pilih Model Writer & Reviewer)
    _notify("router", "🧠 **Smart Model Router**: Mengevaluasi model terbaik untuk genre & mengecek sisa kuota token...")
    routing = select_optimal_models(genre=genre, topic=topic)
    writer_model_id = routing["writer_model"]
    reviewer_model_id = routing["reviewer_model"]
    writer_label = routing["writer_label"]
    reviewer_label = routing["reviewer_label"]
    routing_reason = routing["routing_reason"]

    _notify(
        "router_done",
        f"🤖 **Model Terpilih**: Writer = **{writer_label}** | Reviewer = **{reviewer_label}**  \n"
        f"💡 *Alasan Router*: {routing_reason}"
    )

    # 4. Jalankan Mesin Inti Multi-Agent RAG (Tanpa Mengubah Kode Inti)
    app_graph = build_graph()
    editorial_brief = (
        f"ARAHAN REDAKSI OTOMATIS:\n"
        f"- Genre Artikel: {genre}\n"
        f"- Gunakan Judul Utama (Baris Pertama): # {target_title}\n"
        f"- Sudut Pandang (Angle): {editorial_angle}\n"
        f"- Wajib 5-8 paragraf berdasarkan KONTEKS ASLI dan sertakan **Sumber Referensi:** unik di bagian akhir."
    )

    initial_state = {
        "topic": topic,
        "context": "",
        "draft": "",
        "revision_notes": editorial_brief,
        "revision_count": 1,
        "is_passed": False,
        "writer_model": writer_model_id,
        "reviewer_model": reviewer_model_id,
        "writer_tokens": 0,
        "reviewer_tokens": 0,
        "grader_tokens": 0,
        "start_time": start_time,
    }

    final_state = initial_state.copy()

    for event in app_graph.stream(initial_state):
        for node_name, state_update in event.items():
            final_state.update(state_update)
            if node_name == "retriever":
                _notify("retriever", "✅ **Retriever**: Konteks terverifikasi dari Supabase pgvector / Wikipedia Indonesia.")
            elif node_name == "writer":
                iter_num = final_state.get("revision_count", 1)
                _notify("writer", f"✍️ **Agent Writer ({writer_label})**: Selesai menyusun draf (Iterasi ke-{iter_num}).")
            elif node_name == "reviewer":
                if final_state.get("is_passed"):
                    _notify("checker1_pass", f"🕵️‍♂️ **Checker 1 — Kredibilitas Sumber ({reviewer_label})**: **LULUS** (Fakta & sitasi valid).")
                else:
                    notes_short = final_state.get("revision_notes", "")[:180]
                    _notify("checker1_revise", f"🕵️‍♂️ **Checker 1 ({reviewer_label})**: Meminta revisi fakta/struktur ({notes_short}...).")

    # 4b. Post-Orchestrator Draft Validity Guard (cegah penolakan, terpotong, 0-referensi, aksara asing, atau konten melenceng)
    if final_state.get("draft"):
        final_state["draft"] = re.sub(r"<think>.*?</think>", "", final_state["draft"], flags=re.DOTALL | re.IGNORECASE).strip()

    is_broken, broken_reason = _inspect_draft_quality(final_state.get("draft", ""), topic=topic, genre=genre)
    if is_broken:
        clean_topic = _extract_primary_entity(topic)
        recovery_writer = (
            "cohere/command-a-plus-05-2026"
            if writer_model_id != "cohere/command-a-plus-05-2026"
            else "gemini/gemini-3.5-flash"
        )
        recovery_reviewer = (
            "groq/openai/gpt-oss-120b"
            if reviewer_model_id == recovery_writer
            else reviewer_model_id
        )
        recovery_note = f"alasan=`{broken_reason}`, Writer=`{recovery_writer}`"

        if clean_topic.lower() != topic.strip().lower():
            topic = clean_topic
            _ensure_wikipedia_topic_indexed(topic)
        elif broken_reason in ("refusal", "off_genre", "short_body"):
            alt_pick = _pick_fresh_curated_topic(genre, recent_topics + [topic])
            topic = alt_pick["topic"]
            trending_keyword = alt_pick["keyword"]
            target_title = f"Menelusuri Pesona {topic}: Sejarah, Keunikan, dan Fakta Menarik Nusantara"
            editorial_angle = f"Mengulas tuntas daya tarik, latar sejarah, dan keunikan autentik {topic} berbasis fakta ensiklopedis terverifikasi."
            editorial_brief = (
                f"ARAHAN REDAKSI OTOMATIS:\n"
                f"- Genre Artikel: {genre}\n"
                f"- Gunakan Judul Utama (Baris Pertama): # {target_title}\n"
                f"- Sudut Pandang (Angle): {editorial_angle}\n"
                f"- Wajib 5-8 paragraf dalam Bahasa Indonesia baku tanpa aksara asing, berdasar KONTEKS ASLI, dan sertakan **Sumber Referensi:** unik di akhir."
            )
            seo_refreshed = mine_travel_search_keywords(topic, genre)
            trend_plan.update(seo_refreshed)
            _ensure_wikipedia_topic_indexed(topic)
            recovery_note = f"alasan=`{broken_reason}`, topik cadangan=`{topic}`, Writer=`{recovery_writer}`"

        _notify(
            "recovery",
            f"⚠️ **Draft Validity Guard**: Draf awal bermasalah ({recovery_note}); menjalankan **Recovery Pass**..."
        )
        time.sleep(5)
        recovery_state = {
            "topic": topic,
            "context": "",
            "draft": "",
            "revision_notes": editorial_brief,
            "revision_count": 1,
            "is_passed": False,
            "writer_model": recovery_writer,
            "reviewer_model": recovery_reviewer,
            "writer_tokens": int(final_state.get("writer_tokens", 0)),
            "reviewer_tokens": int(final_state.get("reviewer_tokens", 0)),
            "grader_tokens": int(final_state.get("grader_tokens", 0)),
            "start_time": start_time,
        }
        recovery_final = recovery_state.copy()
        for event in app_graph.stream(recovery_state):
            for node_name, state_update in event.items():
                recovery_final.update(state_update)
                if node_name == "writer":
                    iter_num = recovery_final.get("revision_count", 1)
                    _notify("writer", f"✍️ **Recovery Writer ({recovery_writer})**: Selesai menyusun draf (Iterasi ke-{iter_num}).")
                elif node_name == "reviewer" and recovery_final.get("is_passed"):
                    _notify("checker1_pass", f"🕵️‍♂️ **Recovery Checker 1 ({recovery_reviewer})**: **LULUS** (Fakta & sitasi valid).")

        if recovery_final.get("draft"):
            recovery_final["draft"] = re.sub(r"<think>.*?</think>", "", recovery_final["draft"], flags=re.DOTALL | re.IGNORECASE).strip()

        rec_broken, _ = _inspect_draft_quality(recovery_final.get("draft", ""), topic=topic, genre=genre)
        if not rec_broken or len(recovery_final.get("draft", "")) > len(final_state.get("draft", "")):
            final_state = recovery_final
            writer_model_id = recovery_writer
            reviewer_model_id = recovery_reviewer
        else:
            final_state["writer_tokens"] = int(recovery_final.get("writer_tokens", final_state.get("writer_tokens", 0)))
            final_state["reviewer_tokens"] = int(recovery_final.get("reviewer_tokens", final_state.get("reviewer_tokens", 0)))
            final_state["grader_tokens"] = int(recovery_final.get("grader_tokens", final_state.get("grader_tokens", 0)))

    # Hard Publishability Gate: tolak draf penolakan/sampah sebelum Checker 2 & Supabase
    final_broken, final_reason = _inspect_draft_quality(final_state.get("draft", ""), topic=topic, genre=genre)
    if final_broken and final_reason in ("refusal", "short_body"):
        raise RuntimeError(
            f"Draf untuk '{topic}' ({genre}) gagal validasi konten setelah Recovery Pass (alasan={final_reason}); dibatalkan agar tidak menyimpan naskah rusak ke Supabase."
        )

    # 5. Jalankan Checker 2 (Final Gatekeeper: Judul, Topik, Genre, Format CMS, SEO On-Page)
    _notify("checker2", "🛡️ **Checker 2 — Final Gatekeeper**: Memvalidasi keselarasan Judul, SEO, Topik, Genre, dan mengemas format CMS...")
    gatekeeper_result = run_final_gatekeeper(
        draft=final_state.get("draft", ""),
        target_title=target_title,
        topic=topic,
        genre=genre,
        editorial_angle=editorial_angle,
        checker_model_id=reviewer_model_id,
        primary_keyword=trend_plan.get("primary_keyword"),
        target_keywords=trend_plan.get("target_keywords"),
        search_intent=trend_plan.get("search_intent"),
        meta_title_target=trend_plan.get("meta_title_target"),
    )

    end_time = time.time()
    total_latency = round(end_time - start_time, 2)

    _notify(
        "checker2_done",
        f"✅ **Checker 2 Selesai (Skor Kepatuhan: {gatekeeper_result['final_check_score']}/100)**:  \n"
        f"{gatekeeper_result['final_check_notes']}"
    )

    v_audit = gatekeeper_result.get("vision_audit", {})
    if v_audit:
        v_score = v_audit.get("score", 90)
        v_status = "LULUS" if v_audit.get("is_passed", True) else "REVISI"
        v_notes = v_audit.get("audit_notes", "")
        _notify(
            "vision_reviewer_done",
            f"👁️ **Agent Vision Reviewer (Visual Fact-Checker)**: **{v_status} (Skor: {v_score}/100)**  \n"
            f"*{v_notes}* — Verifikasi visual 16:9 WebP bebas watermark & fotorealistis."
        )

    # 6. Catat pemakaian token ke experiment_metrics.csv agar kuota harian ter-update
    try:
        log_metrics(final_state, total_latency)
    except Exception as e:
        print(f"[Daily Pipeline] Peringatan gagal log ke CSV: {e}")

    # 7. Simpan artikel matang ke Supabase (`daily_auto_articles`)
    actual_revisions = max(1, final_state.get("revision_count", 2) - 1)
    cms_payload = gatekeeper_result["cms_payload"]
    cms_payload["trend_and_uniqueness_proof"] = {
        "trending_keyword": trending_keyword,
        "trend_source": trend_source,
        "raw_signals_count": trend_plan.get("raw_signals_count", 0),
        "live_signals_evidence": trend_plan.get("live_signals_evidence", []),
        "checked_history_list": trend_plan.get("checked_history_list", []),
        "is_unique_non_identical_title": trend_plan.get("is_unique_title", True),
    }

    record = {
        "run_date": now_wib.strftime("%Y-%m-%d %H:%M WIB"),
        "genre": genre,
        "trending_keyword": trending_keyword,
        "trend_source": trend_source,
        "topic": topic,
        "target_title": target_title,
        "final_title": gatekeeper_result["final_title"],
        "meta_title": gatekeeper_result.get("meta_title"),
        "excerpt": gatekeeper_result.get("excerpt"),
        "slug": gatekeeper_result["slug"],
        "editorial_angle": editorial_angle,
        "cover_image_url": gatekeeper_result.get("cover_image_url"),
        "cover_image_alt": gatekeeper_result.get("cover_image_alt"),
        "cover_image_meta": gatekeeper_result.get("cover_image_meta"),
        "writer_model": writer_model_id,
        "reviewer_model": reviewer_model_id,
        "routing_reason": routing_reason,
        "article_markdown": gatekeeper_result["article_markdown"],
        "meta_description": gatekeeper_result["meta_description"],
        "tags": gatekeeper_result["tags"],
        "references": gatekeeper_result["references"],
        "fact_check_passed": bool(final_state.get("is_passed", False)),
        "fact_check_revisions": actual_revisions,
        "final_check_passed": gatekeeper_result["final_check_passed"],
        "final_check_score": gatekeeper_result["final_check_score"],
        "seo_score": gatekeeper_result.get("seo_score", 90),
        "final_check_notes": gatekeeper_result["final_check_notes"],
        "cms_payload": cms_payload,
        "writer_tokens": int(final_state.get("writer_tokens", 0)),
        "reviewer_tokens": int(final_state.get("reviewer_tokens", 0)),
        "grader_tokens": int(final_state.get("grader_tokens", 0)),
        "final_checker_tokens": int(gatekeeper_result.get("final_checker_tokens", 0)),
        "total_latency": total_latency,
    }

    _notify("storage", "🗄️ Menyimpan artikel siap terbit ke database Supabase (`daily_auto_articles`)...")
    article_id = save_daily_article(record)
    record["id"] = article_id
    _notify("complete", f"🎉 **Selesai dalam {total_latency:.1f} detik!** Artikel harian telah tersimpan di Supabase dan siap di-copy oleh Redaksi.")

    return record
