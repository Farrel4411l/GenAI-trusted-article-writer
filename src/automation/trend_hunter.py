import json
import random
import re
import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import datetime
from typing import List, Dict, Any, Optional
from langchain_core.messages import SystemMessage, HumanMessage
from src.agents.llm_factory import get_llm

# 4 Genre Resmi Travelista.id
TRAVELISTA_GENRES = [
    "Wisata & Destinasi (Travel)",
    "Kuliner Nusantara",
    "Sejarah & Misteri Lokal",
    "Budaya & Fakta Unik",
]

# Kueri RSS Google News Indonesia per Genre (Filter `when:30d` agar selalu berita hangat terbaru)
GENRE_RSS_QUERIES = {
    "Wisata & Destinasi (Travel)": "wisata+destinasi+indonesia+when:30d",
    "Kuliner Nusantara": "kuliner+makanan+khas+indonesia+when:30d",
    "Sejarah & Misteri Lokal": "sejarah+candi+budaya+situs+indonesia+when:30d",
    "Budaya & Fakta Unik": "tradisi+budaya+adat+indonesia+when:30d",
}

# Pool Topik Nusantara Kaya Referensi (1 Entitas Spesifik Tunggal agar RAG & Foto Wikimedia 100% Akurat)
CURATED_EVERGREEN_POOL = {
    "Wisata & Destinasi (Travel)": [
        {"keyword": "Labuan Bajo & Pulau Komodo", "topic": "Taman Nasional Komodo"},
        {"keyword": "Kawah Ijen Blue Fire", "topic": "Kawah Ijen"},
        {"keyword": "Raja Ampat Papua", "topic": "Kepulauan Raja Ampat"},
        {"keyword": "Danau Toba & Samosir", "topic": "Danau Toba"},
        {"keyword": "Gunung Bromo Tengger", "topic": "Gunung Bromo"},
        {"keyword": "Nusa Penida Bali", "topic": "Nusa Penida"},
        {"keyword": "Taman Nasional Tanjung Puting", "topic": "Taman Nasional Tanjung Puting"},
        {"keyword": "Gunung Rinjani & Segara Anak", "topic": "Gunung Rinjani"},
        {"keyword": "Kepulauan Banda Neira", "topic": "Banda Neira"},
        {"keyword": "Taman Nasional Wakatobi", "topic": "Taman Nasional Wakatobi"},
        {"keyword": "Dataran Tinggi Dieng", "topic": "Dataran Tinggi Dieng"},
        {"keyword": "Masjid Agung Jawa Tengah", "topic": "Masjid Agung Jawa Tengah"},
    ],
    "Kuliner Nusantara": [
        {"keyword": "Rendang Minangkabau", "topic": "Rendang"},
        {"keyword": "Pempek Palembang", "topic": "Pempek"},
        {"keyword": "Gudeg Yogyakarta", "topic": "Gudeg"},
        {"keyword": "Rawon Jawa Timur", "topic": "Rawon"},
        {"keyword": "Sate Lilit Bali", "topic": "Sate lilit"},
        {"keyword": "Coto Makassar", "topic": "Coto Makassar"},
        {"keyword": "Papeda Maluku Papua", "topic": "Papeda"},
        {"keyword": "Soto Lamongan", "topic": "Soto Lamongan"},
        {"keyword": "Kopi Gayo Aceh", "topic": "Kopi Gayo"},
        {"keyword": "Ayam Betutu Bali", "topic": "Ayam betutu"},
        {"keyword": "Nasi Goreng Nusantara", "topic": "Nasi goreng"},
        {"keyword": "Bakso Malang", "topic": "Bakso"},
    ],
    "Sejarah & Misteri Lokal": [
        {"keyword": "Misteri & Sejarah Lawang Sewu", "topic": "Lawang Sewu"},
        {"keyword": "Hutan Alas Purwo Banyuwangi", "topic": "Taman Nasional Alas Purwo"},
        {"keyword": "Sejarah Candi Borobudur", "topic": "Candi Borobudur"},
        {"keyword": "Benteng Vredeburg Yogyakarta", "topic": "Museum Benteng Vredeburg"},
        {"keyword": "Candi Plaosan Klaten", "topic": "Candi Plaosan"},
        {"keyword": "Situs Megalitikum Gunung Padang", "topic": "Situs Gunung Padang"},
        {"keyword": "Candi Prambanan & Legenda Roro Jonggrang", "topic": "Candi Prambanan"},
        {"keyword": "Istana Maimun Medan", "topic": "Istana Maimun"},
        {"keyword": "Kerajaan Majapahit Trowulan", "topic": "Trowulan"},
        {"keyword": "Benteng Rotterdam Makassar", "topic": "Benteng Rotterdam"},
        {"keyword": "Candi Muara Takus Riau", "topic": "Candi Muara Takus"},
        {"keyword": "Benteng Pendem Cilacap", "topic": "Benteng Pendem Cilacap"},
    ],
    "Budaya & Fakta Unik": [
        {"keyword": "Kehidupan Suku Baduy Dalam", "topic": "Suku Baduy"},
        {"keyword": "Desa Adat Wae Rebo Flores", "topic": "Wae Rebo"},
        {"keyword": "Tradisi Rambu Solo Tana Toraja", "topic": "Suku Toraja"},
        {"keyword": "Filosofi Batik Warisan UNESCO", "topic": "Batik"},
        {"keyword": "Seni Pertunjukan Wayang Kulit", "topic": "Wayang kulit"},
        {"keyword": "Tari Kecak Uluwatu Bali", "topic": "Tari Kecak"},
        {"keyword": "Alat Musik Angklung Sunda", "topic": "Angklung"},
        {"keyword": "Tradisi Lompat Batu Nias", "topic": "Lompat batu Nias"},
        {"keyword": "Kapal Pinisi Bulukumba", "topic": "Pinisi"},
        {"keyword": "Subak Sistem Irigasi Bali", "topic": "Subak"},
        {"keyword": "Rumah Betang Kalimantan", "topic": "Rumah Betang"},
        {"keyword": "Tradisi Tabuik Pariaman", "topic": "Tabuik"},
    ],
}

# Daftar topik yang terlalu luas/administratif/korporasi (memicu isi berita kriminal/birokrasi/kecelakaan, bukan wisata)
_OVERBROAD_OR_OFFBRAND_PATTERNS = (
    r"^indonesia$",
    r"^jawa\s+(?:barat|tengah|timur)$",
    r"^kalimantan\s+(?:barat|tengah|selatan|timur|utara)$",
    r"^sumatera\s+(?:utara|barat|selatan)$",
    r"^sulawesi\s+(?:utara|tengah|selatan|tenggara)$",
    r"^papua$",
    r"^(?:kabupaten|kota|provinsi)\s+",
    r"^cilacap$",
    r"^pariaman$",
    r"^pati$",
    r"^garuda\s+indonesia$",
    r"^lion\s+air$",
    r"^kereta\s+api\s+indonesia$",
    r"^pertamina$",
    r"^dpr(?:d)?\b",
    r"^kpk\b",
)


def is_overbroad_or_unsuitable_topic(topic: str) -> bool:
    """Memastikan topik bukan nama negara, provinsi, kabupaten/kota umum, atau maskapai/korporasi."""
    cleaned = re.sub(r"\s+", " ", (topic or "").strip().lower())
    if not cleaned or len(cleaned) < 3:
        return True
    return any(re.match(pat, cleaned, flags=re.IGNORECASE) for pat in _OVERBROAD_OR_OFFBRAND_PATTERNS)


def fetch_google_trends_id(max_items: int = 10) -> List[Dict[str, str]]:
    """
    Mengambil tren pencarian harian terpopuler di Indonesia dari Google Trends RSS resmi.
    """
    urls = [
        "https://trends.google.com/trending/rss?geo=ID",
        "https://trends.google.co.id/trends/trendingsearches/daily/rss?geo=ID",
    ]
    items: List[Dict[str, str]] = []
    headers = {"User-Agent": "Mozilla/5.0 (compatible; TravelistaTrendBot/1.0)"}

    for url in urls:
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=8) as resp:
                xml_data = resp.read()
            root = ET.fromstring(xml_data)
            for item in root.findall(".//item")[:max_items]:
                title_el = item.find("title")
                pub_el = item.find("pubDate")
                link_el = item.find("link")
                if title_el is not None and title_el.text:
                    kw = title_el.text.strip()
                    if kw and kw not in [x["title"] for x in items]:
                        items.append({
                            "title": kw,
                            "source": "Google Trends Indonesia (Real-Time RSS)",
                            "pub_date": pub_el.text.strip() if (pub_el is not None and pub_el.text) else "",
                            "link": link_el.text.strip() if (link_el is not None and link_el.text) else url,
                            "genre_hint": "General Trending ID"
                        })
            if items:
                break
        except Exception as e:
            print(f"[Trend Hunter] Info gagal akses {url}: {e}")
    return items


def fetch_google_autocomplete(query: str, max_items: int = 6) -> List[str]:
    """
    Mengambil kata kunci pencarian real-time (long-tail keywords) dari Google Suggest Indonesia
    tanpa memerlukan API key berbayar.
    """
    clean_q = query.strip()
    if not clean_q:
        return []
    encoded_q = urllib.parse.quote(clean_q)
    url = f"https://suggestqueries.google.com/complete/search?client=chrome&hl=id&gl=ID&q={encoded_q}"
    headers = {"User-Agent": "Mozilla/5.0 (compatible; TravelistaSeoBot/2.0)"}
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode("utf-8", errors="ignore"))
            if len(data) > 1 and isinstance(data[1], list):
                suggestions = [str(item).strip().lower() for item in data[1] if item]
                return suggestions[:max_items]
    except Exception as e:
        print(f"[Trend Hunter] Info autocomplete untuk '{clean_q}': {e}")
    return []


def mine_travel_search_keywords(topic: str, genre: str) -> Dict[str, Any]:
    """
    Memetakan kata kunci pencarian riil (Search-Intent Keywords) dan niat pengguna Google:
    1. Primary Keyword (kata kunci utama dengan volume/relevansi tertinggi)
    2. Target Keywords (3-5 kata kunci turunan/long-tail untuk heading & paragraf)
    3. Search Intent (Kategori niat: Healing, Kuliner Autentik, Sejarah/Misteri, Budaya)
    4. Meta Title Target (Judul SERP singkat <= 60 karakter yang ramah mesin pencari)
    """
    # Pisahkan entitas dari topic (misal "Kawah Ijen dan Banyuwangi" -> ["Kawah Ijen", "Banyuwangi"])
    parts = re.split(r'\b(?:dan|serta|atau)\b|[,&/]', topic, flags=re.IGNORECASE)
    entities = [p.strip() for p in parts if len(p.strip()) >= 3]
    main_entity = entities[0] if entities else topic.strip()
    sub_entity = entities[1] if len(entities) > 1 else ""

    # Tentukan Search Intent default berbasis Genre
    intent_map = {
        "Wisata & Destinasi (Travel)": "Wisata Alam, Healing, & Spot Liburan Eksploratif",
        "Kuliner Nusantara": "Wisata Kuliner Tradisional & Cita Rasa Autentik",
        "Sejarah & Misteri Lokal": "Wisata Sejarah, Arkeologi, & Misteri Budaya Lokal",
        "Budaya & Fakta Unik": "Warisan Budaya, Tradisi Adat, & Kearifan Lokal Nusantara",
    }
    search_intent = intent_map.get(genre, "Panduan Wisata & Gaya Hidup Travelista")

    # Kumpulkan variasi kata kunci dari Google Suggest
    raw_keywords: List[str] = []

    # 1. Kueri langsung entitas utama
    raw_keywords.extend(fetch_google_autocomplete(main_entity, max_items=4))

    # 2. Kueri kontekstual berbasis genre
    if "wisata" in genre.lower() or "travel" in genre.lower():
        raw_keywords.extend(fetch_google_autocomplete(f"wisata {main_entity}", max_items=4))
        raw_keywords.extend(fetch_google_autocomplete(f"tempat healing di {main_entity}", max_items=3))
    elif "kuliner" in genre.lower():
        raw_keywords.extend(fetch_google_autocomplete(f"kuliner khas {main_entity}", max_items=4))
        raw_keywords.extend(fetch_google_autocomplete(f"makanan enak di {main_entity}", max_items=3))
    elif "sejarah" in genre.lower() or "misteri" in genre.lower():
        raw_keywords.extend(fetch_google_autocomplete(f"sejarah {main_entity}", max_items=4))
        raw_keywords.extend(fetch_google_autocomplete(f"misteri {main_entity}", max_items=3))
    else:
        raw_keywords.extend(fetch_google_autocomplete(f"tradisi {main_entity}", max_items=4))
        raw_keywords.extend(fetch_google_autocomplete(f"keunikan {main_entity}", max_items=3))

    # Bersihkan & deduplikasi
    unique_kw = []
    seen = set()
    for kw in raw_keywords:
        kw_clean = kw.strip().lower()
        if kw_clean and kw_clean not in seen and len(kw_clean) > 4:
            seen.add(kw_clean)
            unique_kw.append(kw_clean)

    # Tentukan Primary Keyword
    primary_kw = unique_kw[0] if unique_kw else f"wisata {main_entity.lower()}"

    # Pastikan ada 3-5 target keywords
    target_kw = unique_kw[:5]
    if len(target_kw) < 3:
        target_kw.extend([
            f"daya tarik {main_entity.lower()}",
            f"tips berkunjung ke {main_entity.lower()}",
            f"rekomendasi {main_entity.lower()}"
        ])
        target_kw = list(dict.fromkeys(target_kw))[:5]

    # Buat Target Meta Title (<= 60 karakter, primary keyword di depan)
    if "wisata" in genre.lower() or "travel" in genre.lower():
        candidate_meta = f"{main_entity}: Daya Tarik, Info & Panduan Wisata"
    elif "kuliner" in genre.lower():
        candidate_meta = f"{main_entity}: Cita Rasa & Rekomendasi Kuliner"
    elif "sejarah" in genre.lower():
        candidate_meta = f"{main_entity}: Sejarah, Misteri & Fakta Menarik"
    else:
        candidate_meta = f"{main_entity}: Tradisi, Filosofi & Keunikan Budaya"

    if len(candidate_meta) > 60:
        candidate_meta = candidate_meta[:57] + "..."

    return {
        "primary_keyword": primary_kw,
        "target_keywords": target_kw,
        "search_intent": search_intent,
        "meta_title_target": candidate_meta,
        "main_entity": main_entity,
        "sub_entity": sub_entity,
    }


def fetch_google_news_by_genre(genre: str, max_items: int = 5) -> List[Dict[str, str]]:
    """
    Mengambil berita & topik yang sedang hangat di Google News Indonesia sesuai Genre Travelista.
    """
    query = GENRE_RSS_QUERIES.get(genre, "wisata+kuliner+budaya+indonesia")
    url = f"https://news.google.com/rss/search?q={query}&hl=id&gl=ID&ceid=ID:id"
    headers = {"User-Agent": "Mozilla/5.0 (compatible; TravelistaTrendBot/1.0)"}
    results: List[Dict[str, str]] = []

    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=8) as resp:
            xml_data = resp.read()
        root = ET.fromstring(xml_data)
        for item in root.findall(".//item")[:max_items]:
            title_el = item.find("title")
            pub_el = item.find("pubDate")
            link_el = item.find("link")
            if title_el is not None and title_el.text:
                # Bersihkan nama portal berita di belakang tanda ' - '
                clean_title = title_el.text.split(" - ")[0].strip()
                portal = title_el.text.split(" - ")[-1].strip() if " - " in title_el.text else "Google News ID"
                results.append({
                    "title": clean_title,
                    "source": f"Google News ID ({genre} — {portal})",
                    "pub_date": pub_el.text.strip() if (pub_el is not None and pub_el.text) else "",
                    "link": link_el.text.strip() if (link_el is not None and link_el.text) else url,
                    "genre_hint": genre
                })
    except Exception as e:
        print(f"[Trend Hunter] Gagal mengambil Google News untuk {genre}: {e}")
    return results


def collect_live_trends(preferred_genre: Optional[str] = None) -> List[Dict[str, str]]:
    """
    Mengumpulkan sinyal tren dari Google Trends Indonesia & Google News Indonesia
    untuk 4 genre resmi Travelista.id.
    """
    all_signals: List[Dict[str, str]] = []

    # 1. Tarik Google Trends Harian Indonesia
    gtrends = fetch_google_trends_id(max_items=8)
    all_signals.extend(gtrends)

    # 2. Tarik Google News per Genre
    target_genres = [preferred_genre] if (preferred_genre and preferred_genre in TRAVELISTA_GENRES) else TRAVELISTA_GENRES
    for g in target_genres:
        news_items = fetch_google_news_by_genre(g, max_items=4)
        all_signals.extend(news_items)

    return all_signals


def analyze_and_select_daily_topic(
    recent_topics: Optional[List[str]] = None,
    preferred_genre: Optional[str] = None,
    planner_model_id: Optional[str] = None
) -> Dict[str, Any]:
    from src.automation.model_router import is_gemini_quota_exhausted
    if not planner_model_id:
        planner_model_id = "cohere/command-a-plus-05-2026" if is_gemini_quota_exhausted() else "gemini/gemini-3.5-flash"
    """
    Menganalisis sinyal tren pencarian hari ini dan menentukan:
    1. Genre Terbaik (dari 4 genre Travelista)
    2. Kata Kunci Tren Pemicu
    3. Topik Entitas Riset (untuk pencarian pgvector & Wikipedia Indonesia)
    4. Target Judul Artikel (SEO & Jurnalistik)
    5. Sudut Pandang Redaksi (Editorial Angle)
    """
    recent_topics = recent_topics or []
    recent_lower = {t.lower() for t in recent_topics}

    print("[Trend Hunter] Mengumpulkan tren pencarian terkini dari Google Trends & Google News Indonesia...")
    live_signals = collect_live_trends(preferred_genre=preferred_genre)

    # Siapkan kandidat referensi dari Evergreen Pool yang belum pernah ditulis baru-baru ini
    available_pool = {}
    for g, items in CURATED_EVERGREEN_POOL.items():
        if preferred_genre and g != preferred_genre:
            continue
        filtered = [
            it for it in items
            if it["topic"].lower() not in recent_lower and it["keyword"].lower() not in recent_lower
        ]
        available_pool[g] = filtered if filtered else items

    signals_text = "\n".join(
        f"- [{s['source']}] {s['title']}" for s in live_signals[:20]
    ) or "- Tren Wisata Alam, Kuliner Tradisional, Sejarah & Budaya Nusantara"

    recent_text = ", ".join(recent_topics[:30]) if recent_topics else "Belum ada"
    allowed_genres_str = preferred_genre if preferred_genre in TRAVELISTA_GENRES else ", ".join(TRAVELISTA_GENRES)

    system_prompt = """Anda adalah *Chief Trend Analyst & Editorial Planner* untuk portal media "Travelista.id".
Tugas Anda adalah menganalisis sinyal tren pencarian terkini di Indonesia (Google Trends & Google News) dan menentukan 1 rencana artikel harian terbaik.

ATURAN WAJIB:
1. GENRE: Pilih HANYA SATU dari daftar genre resmi berikut:
   - "Wisata & Destinasi (Travel)"
   - "Kuliner Nusantara"
   - "Sejarah & Misteri Lokal"
   - "Budaya & Fakta Unik"
2. FILTER NIAT WISATA & LIFESTYLE: Prioritaskan sinyal tren yang mengarah pada objek wisata, hidangan kuliner spesifik, candi/situs sejarah, atau tradisi budaya nyata Nusantara. Hindari topik politik, korupsi/OTT, hukum, kecelakaan, atau seremoni birokrasi.
3. KETERSEDIAAN ENSIKLOPEDIA & LARANGAN TOPIK TERLALU LUAS:
   - Nilai `topic` WAJIB berupa **1 entitas destinasi, hidangan, situs bersejarah, atau tradisi budaya SPESIFIK** yang memiliki halaman khusus di Wikipedia Bahasa Indonesia (contoh BAIK: "Kawah Ijen", "Rendang", "Candi Prambanan", "Candi Plaosan", "Lawang Sewu", "Suku Baduy", "Rumah Betang", "Tradisi Tabuik").
   - DILARANG KERAS memilih nama negara ("Indonesia"), nama provinsi ("Jawa Tengah", "Kalimantan Tengah"), nama kabupaten/kota administratif umum ("Cilacap", "Kabupaten Pati", "Kota Pariaman"), atau nama maskapai/korporasi ("Garuda Indonesia") sebagai `topic`, karena halaman Wikipedia administratif/perusahaan didominasi daftar kecamatan, statistik birokrasi, kasus hukum, atau berita kecelakaan!
   - HINDARI menggabungkan dua entitas dengan kata "dan" (seperti "Candi X dan Kabupaten Y").
4. KESELARASAN JUDUL & ISI (ANTI-DIPAKSAKAN): Gunakan berita tren sebagai *inspirasi tema abadi (evergreen)*, BUKAN memaksakan klaim angka peringkat 2026 atau peristiwa seremonial kemarin masuk ke judul utama apabila fakta tersebut tidak tersedia di ensiklopedia Wikipedia. Gunakan Bahasa Indonesia jurnalistik yang alami tanpa mencampur bahasa asing yang tidak perlu.
5. HINDARI DUPLIKASI: Jangan memilih topik yang sudah ada di daftar TOPIK YANG SUDAH DITULIS.
6. OUTPUT WAJIB berupa JSON murni (tanpa teks pembuka/penutup) dengan struktur persis berikut:
{
  "genre": "Nama Genre Resmi",
  "trending_keyword": "Kata kunci atau berita tren yang memicu pemilihan topik ini",
  "trend_source": "Google Trends ID / Google News ID",
  "topic": "1 Entitas Spesifik Wikipedia Indonesia (bukan nama provinsi/kabupaten/negara/maskapai)",
  "target_title": "Judul Artikel Jurnalistik Travelista yang Menarik, Nyata, dan SEO-Friendly",
  "editorial_angle": "2-3 kalimat arahan sudut pandang pembahasan artikel sesuai fakta wisata/kuliner/sejarah/budaya"
}"""

    user_prompt = f"""TANGGAL HARI INI: {datetime.now().strftime('%Y-%m-%d')}
GENRE YANG DIIZINKAN: {allowed_genres_str}

SINYAL TREN PENCARIAN & BERITA HARI INI DI INDONESIA:
{signals_text}

TOPIK YANG SUDAH PERNAH DITULIS (JANGAN DIULANG):
{recent_text}

Pilih 1 topik terhangat dan paling menarik untuk pembaca Travelista.id hari ini, lalu keluarkan dalam format JSON!"""

    try:
        llm = get_llm(planner_model_id)
        if hasattr(llm, "temperature"):
            llm.temperature = 0.4
        resp = llm.invoke([
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt)
        ])
        content = resp.content
        if isinstance(content, list):
            content = "".join(
                item.get("text", "") if isinstance(item, dict) else str(item)
                for item in content
            )
        json_match = re.search(r"\{.*\}", content, flags=re.DOTALL)
        if json_match:
            parsed = json.loads(json_match.group(0))
            genre = parsed.get("genre", "")
            if genre not in TRAVELISTA_GENRES:
                genre = preferred_genre if preferred_genre in TRAVELISTA_GENRES else TRAVELISTA_GENRES[0]
            topic = parsed.get("topic", "").strip()
            # Bersihkan topik majemuk jika LLM masih menyisipkan ' dan '
            topic = re.split(r"\s+(?:dan|serta|atau)\s+|[,&/]", topic, maxsplit=1, flags=re.IGNORECASE)[0].strip()
            target_title = parsed.get("target_title", "").strip()
            if is_overbroad_or_unsuitable_topic(topic):
                print(f"[Trend Hunter] Topik '{topic}' terlalu luas/administratif/korporasi (berisiko konten melenceng). Beralih ke pool entitas spesifik...")
                raise ValueError(f"Overbroad or unsuitable topic: {topic}")
            recent_primary_lowers = {
                re.split(r"\s+(?:dan|serta|atau)\s+|[,&/]", r.lower(), maxsplit=1)[0].strip()
                for r in recent_lower if r
            }
            if topic.lower() in recent_lower or topic.lower() in recent_primary_lowers:
                print(f"[Trend Hunter] Topik '{topic}' sudah pernah terbit baru-baru ini. Memilih topik segar dari pool terkurasi...")
                raise ValueError(f"Duplicate recent topic: {topic}")
            # Jaminan Anti-Identik: Jika judul persis sama dengan yang pernah dibuat, tambahkan diferensiator sudut pandang
            if target_title.lower() in recent_lower:
                target_title = f"{target_title}: Perspektif Baru & Fakta Mendalam ({datetime.now().strftime('%d %b %Y')})"
            if topic and target_title:
                seo_intel = mine_travel_search_keywords(topic, genre)
                return {
                    "genre": genre,
                    "trending_keyword": parsed.get("trending_keyword", topic),
                    "trend_source": parsed.get("trend_source", "Google Trends & News ID"),
                    "topic": topic,
                    "target_title": target_title,
                    "editorial_angle": parsed.get(
                        "editorial_angle",
                        f"Mengulas mendalam daya tarik, sejarah, dan keunikan {topic} bagi pembaca Travelista."
                    ),
                    "primary_keyword": seo_intel["primary_keyword"],
                    "target_keywords": seo_intel["target_keywords"],
                    "search_intent": seo_intel["search_intent"],
                    "meta_title_target": seo_intel["meta_title_target"],
                    "raw_signals_count": len(live_signals),
                    "live_signals_preview": [s["title"] for s in live_signals[:6]],
                    "live_signals_evidence": live_signals[:25],
                    "checked_history_list": recent_topics,
                    "is_unique_title": target_title.lower() not in recent_lower,
                }
    except Exception as e:
        print(f"[Trend Hunter] Fallback ke kurasi cerdas karena kendala LLM Planner: {e}")

    # Fallback deterministik jika API LLM Planner sedang limit
    chosen_genre = preferred_genre if preferred_genre in TRAVELISTA_GENRES else random.choice(TRAVELISTA_GENRES)
    candidates = available_pool.get(chosen_genre, CURATED_EVERGREEN_POOL[chosen_genre])
    picked = random.choice(candidates)
    genre_signals = [s["title"] for s in live_signals if s.get("genre_hint") == chosen_genre]
    top_signal = genre_signals[0] if genre_signals else picked["keyword"]
    fallback_title = f"Menjelajahi Pesona dan Fakta Menarik {picked['keyword']} yang Wajib Anda Ketahui"
    if fallback_title.lower() in recent_lower:
        fallback_title = f"{fallback_title} (Edisi {datetime.now().strftime('%d %b %Y')})"

    seo_intel = mine_travel_search_keywords(picked["topic"], chosen_genre)
    return {
        "genre": chosen_genre,
        "trending_keyword": top_signal[:90] if genre_signals else picked["keyword"],
        "trend_source": "Google News & Trends Indonesia",
        "topic": picked["topic"],
        "target_title": fallback_title,
        "editorial_angle": (
            f"Mengupas tuntas keunikan, latar sejarah, serta daya tarik utama dari {picked['topic']} "
            f"dengan gaya jurnalistik mendalam khas Travelista.id."
        ),
        "primary_keyword": seo_intel["primary_keyword"],
        "target_keywords": seo_intel["target_keywords"],
        "search_intent": seo_intel["search_intent"],
        "meta_title_target": seo_intel["meta_title_target"],
        "raw_signals_count": len(live_signals),
        "live_signals_preview": [s["title"] for s in live_signals[:6]],
        "live_signals_evidence": live_signals[:25],
        "checked_history_list": recent_topics,
        "is_unique_title": True,
    }
