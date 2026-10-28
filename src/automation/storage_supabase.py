import os
import json
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any, Optional
import psycopg2
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv

load_dotenv()

LOCAL_CACHE_FILE = "daily_articles_cache.json"
WIB_TZ = timezone(timedelta(hours=7))


def _get_clean_db_url() -> Optional[str]:
    """Mengambil DATABASE_URL yang kompatibel dengan psycopg2 langsung."""
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        return None
    if db_url.startswith("postgresql+psycopg2://"):
        db_url = db_url.replace("postgresql+psycopg2://", "postgresql://", 1)
    return db_url


def get_db_connection():
    """Membuka koneksi ke PostgreSQL / Supabase."""
    db_url = _get_clean_db_url()
    if not db_url:
        raise ValueError("DATABASE_URL tidak ditemukan di environment variables (.env / st.secrets).")
    return psycopg2.connect(db_url)


def init_daily_articles_table() -> bool:
    """
    Membuat tabel `daily_auto_articles` di Supabase PostgreSQL jika belum ada.
    Sama sekali tidak menyentuh tabel langchain_pg_embedding yang sudah ada.
    """
    create_sql = """
    CREATE TABLE IF NOT EXISTS daily_auto_articles (
        id SERIAL PRIMARY KEY,
        created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
        run_date VARCHAR(32),
        genre VARCHAR(120),
        trending_keyword VARCHAR(255),
        trend_source VARCHAR(255),
        topic VARCHAR(500),
        target_title VARCHAR(500),
        final_title VARCHAR(500),
        slug VARCHAR(500),
        editorial_angle TEXT,
        writer_model VARCHAR(150),
        reviewer_model VARCHAR(150),
        routing_reason TEXT,
        article_markdown TEXT,
        meta_description TEXT,
        tags_json TEXT,
        references_json TEXT,
        fact_check_passed BOOLEAN DEFAULT FALSE,
        fact_check_revisions INTEGER DEFAULT 1,
        final_check_passed BOOLEAN DEFAULT FALSE,
        final_check_score INTEGER DEFAULT 100,
        final_check_notes TEXT,
        cms_payload_json TEXT,
        writer_tokens INTEGER DEFAULT 0,
        reviewer_tokens INTEGER DEFAULT 0,
        grader_tokens INTEGER DEFAULT 0,
        final_checker_tokens INTEGER DEFAULT 0,
        total_latency FLOAT DEFAULT 0.0
    );
    """
    try:
        conn = get_db_connection()
        with conn:
            with conn.cursor() as cur:
                cur.execute(create_sql)
        conn.close()
        return True
    except Exception as e:
        print(f"[Storage Supabase] Peringatan gagal inisialisasi tabel: {e}")
        return False


def _save_to_local_cache(record: Dict[str, Any]):
    """Menyimpan salinan ke file JSON lokal sebagai cadangan (fallback)."""
    try:
        existing = []
        if os.path.exists(LOCAL_CACHE_FILE):
            with open(LOCAL_CACHE_FILE, "r", encoding="utf-8") as f:
                existing = json.load(f)
        record_copy = dict(record)
        if "id" not in record_copy:
            record_copy["id"] = len(existing) + 1
        if "created_at" not in record_copy:
            record_copy["created_at"] = datetime.now(WIB_TZ).strftime("%Y-%m-%d %H:%M:%S WIB")
        existing.insert(0, record_copy)
        with open(LOCAL_CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(existing[:50], f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[Storage Local Cache] Gagal menyimpan cache lokal: {e}")


def get_recent_topics(limit: int = 30) -> List[str]:
    """
    Mengambil daftar topik dan judul yang sudah pernah dibuat (baik dari tabel
    Supabase `daily_auto_articles` maupun `experiment_metrics.csv`) agar sistem
    otomatis tidak membuat judul yang identik atau mengulang topik yang sama.
    """
    topics = []
    try:
        init_daily_articles_table()
        conn = get_db_connection()
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT topic, final_title, target_title FROM daily_auto_articles ORDER BY created_at DESC LIMIT %s",
                    (limit,)
                )
                for row in cur.fetchall():
                    for val in row:
                        if val and val not in topics:
                            topics.append(val)
        conn.close()
    except Exception:
        if os.path.exists(LOCAL_CACHE_FILE):
            try:
                with open(LOCAL_CACHE_FILE, "r", encoding="utf-8") as f:
                    items = json.load(f)
                for item in items[:limit]:
                    for key in ("topic", "final_title", "target_title"):
                        if item.get(key) and item[key] not in topics:
                            topics.append(item[key])
            except Exception:
                pass

    # Cek juga riwayat dari experiment_metrics.csv
    if os.path.exists("experiment_metrics.csv"):
        try:
            import csv
            with open("experiment_metrics.csv", mode="r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for r in reader:
                    t = (r.get("Topic") or "").strip()
                    if t and t not in topics:
                        topics.append(t)
        except Exception:
            pass

    return topics


def save_daily_article(record: Dict[str, Any]) -> Optional[int]:
    """
    Menyimpan artikel otomatis harian ke Supabase (tabel `daily_auto_articles`)
    serta menyimpan cadangan ke cache lokal.
    """
    now_wib = datetime.now(WIB_TZ)
    run_date = record.get("run_date") or now_wib.strftime("%Y-%m-%d %H:%M WIB")
    tags_json = json.dumps(record.get("tags", []), ensure_ascii=False)
    references_json = json.dumps(record.get("references", []), ensure_ascii=False)
    cms_payload_json = json.dumps(record.get("cms_payload", {}), ensure_ascii=False)

    inserted_id = None
    try:
        init_daily_articles_table()
        conn = get_db_connection()
        insert_sql = """
        INSERT INTO daily_auto_articles (
            run_date, genre, trending_keyword, trend_source, topic,
            target_title, final_title, slug, editorial_angle,
            writer_model, reviewer_model, routing_reason,
            article_markdown, meta_description, tags_json, references_json,
            fact_check_passed, fact_check_revisions,
            final_check_passed, final_check_score, final_check_notes,
            cms_payload_json,
            writer_tokens, reviewer_tokens, grader_tokens, final_checker_tokens,
            total_latency
        ) VALUES (
            %s, %s, %s, %s, %s,
            %s, %s, %s, %s,
            %s, %s, %s,
            %s, %s, %s, %s,
            %s, %s,
            %s, %s, %s,
            %s,
            %s, %s, %s, %s,
            %s
        ) RETURNING id;
        """
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    insert_sql,
                    (
                        run_date,
                        record.get("genre", ""),
                        record.get("trending_keyword", ""),
                        record.get("trend_source", ""),
                        record.get("topic", ""),
                        record.get("target_title", ""),
                        record.get("final_title", ""),
                        record.get("slug", ""),
                        record.get("editorial_angle", ""),
                        record.get("writer_model", ""),
                        record.get("reviewer_model", ""),
                        record.get("routing_reason", ""),
                        record.get("article_markdown", ""),
                        record.get("meta_description", ""),
                        tags_json,
                        references_json,
                        bool(record.get("fact_check_passed", False)),
                        int(record.get("fact_check_revisions", 1)),
                        bool(record.get("final_check_passed", False)),
                        int(record.get("final_check_score", 100)),
                        record.get("final_check_notes", ""),
                        cms_payload_json,
                        int(record.get("writer_tokens", 0)),
                        int(record.get("reviewer_tokens", 0)),
                        int(record.get("grader_tokens", 0)),
                        int(record.get("final_checker_tokens", 0)),
                        float(record.get("total_latency", 0.0)),
                    )
                )
                row = cur.fetchone()
                if row:
                    inserted_id = row[0]
        conn.close()
        print(f"[Storage Supabase] Artikel harian berhasil disimpan ke Supabase (ID: {inserted_id}).")
    except Exception as e:
        print(f"[Storage Supabase] Gagal menyimpan ke Supabase, beralih ke cache lokal: {e}")

    record["id"] = inserted_id or 1
    record["run_date"] = run_date
    _save_to_local_cache(record)
    return inserted_id


def _parse_db_row(row: Dict[str, Any]) -> Dict[str, Any]:
    """Mengonversi kolom JSON string dari database kembali menjadi objek Python."""
    parsed = dict(row)
    for json_col, target_key in [
        ("tags_json", "tags"),
        ("references_json", "references"),
        ("cms_payload_json", "cms_payload"),
    ]:
        raw_val = parsed.get(json_col)
        if isinstance(raw_val, str) and raw_val.strip():
            try:
                parsed[target_key] = json.loads(raw_val)
            except Exception:
                parsed[target_key] = [] if target_key != "cms_payload" else {}
        elif target_key not in parsed:
            parsed[target_key] = [] if target_key != "cms_payload" else {}
    return parsed


def get_daily_articles(limit: int = 20) -> List[Dict[str, Any]]:
    """
    Mengambil daftar artikel harian dari Supabase PostgreSQL
    (diurutkan dari yang terbaru).
    """
    try:
        init_daily_articles_table()
        conn = get_db_connection()
        with conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    "SELECT * FROM daily_auto_articles ORDER BY created_at DESC LIMIT %s",
                    (limit,)
                )
                rows = cur.fetchall()
        conn.close()
        if rows:
            return [_parse_db_row(r) for r in rows]
    except Exception as e:
        print(f"[Storage Supabase] Gagal membaca dari Supabase, membaca cache lokal: {e}")

    if os.path.exists(LOCAL_CACHE_FILE):
        try:
            with open(LOCAL_CACHE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)[:limit]
        except Exception:
            pass
    return []
