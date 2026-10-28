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

# Pool Topik Nusantara Kaya Referensi (Sebagai penyeimbang & jaminan ketersediaan fakta di Wikipedia ID)
CURATED_EVERGREEN_POOL = {
    "Wisata & Destinasi (Travel)": [
        {"keyword": "Labuan Bajo & Pulau Komodo", "topic": "Taman Nasional Komodo dan Labuan Bajo"},
        {"keyword": "Kawah Ijen Blue Fire", "topic": "Kawah Ijen dan Banyuwangi"},
        {"keyword": "Raja Ampat Papua", "topic": "Kepulauan Raja Ampat dan Sorong"},
        {"keyword": "Danau Toba & Samosir", "topic": "Danau Toba dan Pulau Samosir"},
        {"keyword": "Gunung Bromo Tengger", "topic": "Gunung Bromo dan Taman Nasional Bromo Tengger Semeru"},
        {"keyword": "Nusa Penida Bali", "topic": "Nusa Penida dan Pariwisata di Bali"},
        {"keyword": "Taman Nasional Tanjung Puting", "topic": "Taman Nasional Tanjung Puting dan Kalimantan Tengah"},
        {"keyword": "Gunung Rinjani & Segara Anak", "topic": "Gunung Rinjani dan Pulau Lombok"},
        {"keyword": "Kepulauan Banda Neira", "topic": "Banda Neira dan Kepulauan Banda"},
        {"keyword": "Taman Nasional Wakatobi", "topic": "Taman Nasional Wakatobi dan Sulawesi Tenggara"},
    ],
    "Kuliner Nusantara": [
        {"keyword": "Rendang & Masakan Minang", "topic": "Rendang dan Masakan Padang"},
        {"keyword": "Pempek & Cuko Palembang", "topic": "Pempek dan Masakan Palembang"},
        {"keyword": "Gudeg Nangka Yogyakarta", "topic": "Gudeg dan Yogyakarta"},
        {"keyword": "Rawon Hitam Jawa Timur", "topic": "Rawon dan Surabaya"},
        {"keyword": "Sate Lilit & Kuliner Bali", "topic": "Sate Lilit dan Masakan Bali"},
        {"keyword": "Coto Makassar & Konro", "topic": "Coto Makassar dan Makassar"},
        {"keyword": "Papeda & Kuliner Maluku Papua", "topic": "Papeda dan Sagu"},
        {"keyword": "Soto Lamongan & Soto Nusantara", "topic": "Soto (makanan) dan Kabupaten Lamongan"},
        {"keyword": "Kopi Luwak & Kopi Gayo", "topic": "Kopi luwak dan Kopi Gayo"},
        {"keyword": "Ayam Betutu Gilimanuk", "topic": "Ayam betutu dan Masakan Bali"},
    ],
    "Sejarah & Misteri Lokal": [
        {"keyword": "Misteri & Sejarah Lawang Sewu", "topic": "Lawang Sewu dan Kota Semarang"},
        {"keyword": "Hutan Alas Purwo Banyuwangi", "topic": "Taman Nasional Alas Purwo dan Blambangan"},
        {"keyword": "Sejarah Candi Borobudur", "topic": "Candi Borobudur dan Wangsa Syailendra"},
        {"keyword": "Benteng Vredeburg & Kolonial Yogya", "topic": "Museum Benteng Vredeburg dan Kesultanan Ngayogyakarta Hadiningrat"},
        {"keyword": "Gunung Merapi & Petilasan Keraton", "topic": "Gunung Merapi dan Kesultanan Mataram"},
        {"keyword": "Situs Megalitikum Gunung Padang", "topic": "Situs Gunung Padang dan Kabupaten Cianjur"},
        {"keyword": "Candi Prambanan & Legenda Roro Jonggrang", "topic": "Candi Prambanan dan Rara Jonggrang"},
        {"keyword": "Istana Maimun & Kesultanan Deli", "topic": "Istana Maimun dan Kesultanan Deli"},
        {"keyword": "Kerajaan Majapahit di Trowulan", "topic": "Majapahit dan Trowulan, Mojokerto"},
        {"keyword": "Benteng Rotterdam Makassar", "topic": "Benteng Rotterdam dan Kerajaan Gowa"},
    ],
    "Budaya & Fakta Unik": [
        {"keyword": "Kehidupan Suku Baduy Dalam", "topic": "Suku Baduy dan Kabupaten Lebak"},
        {"keyword": "Desa Adat Wae Rebo Flores", "topic": "Wae Rebo dan Kabupaten Manggarai"},
        {"keyword": "Tradisi Rambu Solo Tana Toraja", "topic": "Tana Toraja dan Suku Toraja"},
        {"keyword": "Filosofi Batik & Warisan UNESCO", "topic": "Batik dan Budaya Jawa"},
        {"keyword": "Seni Pertunjukan Wayang Kulit", "topic": "Wayang kulit dan Gamelan"},
        {"keyword": "Tari Kecak Uluwatu Bali", "topic": "Tari Kecak dan Pura Luhur Uluwatu"},
        {"keyword": "Alat Musik Angklung Sunda", "topic": "Angklung dan Budaya Sunda"},
        {"keyword": "Tradisi Lompat Batu Nias (Fahombo)", "topic": "Lompat batu Nias dan Pulau Nias"},
        {"keyword": "Kapal Pinisi Bulukumba", "topic": "Pinisi dan Kabupaten Bulukumba"},
        {"keyword": "Subak Sistem Irigasi Bali", "topic": "Subak dan Budaya Bali"},
    ],
}


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
    planner_model_id: str = "gemini/gemini-3.5-flash"
) -> Dict[str, Any]:
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

    recent_text = ", ".join(recent_topics[:15]) if recent_topics else "Belum ada"
    allowed_genres_str = preferred_genre if preferred_genre in TRAVELISTA_GENRES else ", ".join(TRAVELISTA_GENRES)

    system_prompt = """Anda adalah *Chief Trend Analyst & Editorial Planner* untuk portal media "Travelista.id".
Tugas Anda adalah menganalisis sinyal tren pencarian terkini di Indonesia (Google Trends & Google News) dan menentukan 1 rencana artikel harian terbaik.

ATURAN WAJIB:
1. GENRE: Pilih HANYA SATU dari daftar genre resmi berikut:
   - "Wisata & Destinasi (Travel)"
   - "Kuliner Nusantara"
   - "Sejarah & Misteri Lokal"
   - "Budaya & Fakta Unik"
2. KETERSEDIAAN ENSIKLOPEDIA: Pastikan nilai `topic` berupa 1 atau 2 entitas spesifik di Indonesia yang PASTI memiliki halaman di Wikipedia Bahasa Indonesia (contoh format `topic`: "Kawah Ijen dan Banyuwangi", "Rendang dan Masakan Padang", "Lawang Sewu dan Kota Semarang", "Suku Baduy dan Kabupaten Lebak"). Jangan gunakan kalimat panjang pada `topic` agar mesin pencari database vektor & Wikipedia bekerja optimal.
3. HINDARI DUPLIKASI: Jangan memilih topik yang sudah ada di daftar TOPIK YANG SUDAH DITULIS.
4. OUTPUT WAJIB berupa JSON murni (tanpa teks pembuka/penutup) dengan struktur persis berikut:
{
  "genre": "Nama Genre Resmi",
  "trending_keyword": "Kata kunci atau berita tren yang memicu pemilihan topik ini",
  "trend_source": "Google Trends ID / Google News ID",
  "topic": "Entitas1 dan Entitas2",
  "target_title": "Judul Artikel Jurnalistik Travelista yang Menarik dan SEO-Friendly",
  "editorial_angle": "2-3 kalimat arahan sudut pandang pembahasan artikel"
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
            target_title = parsed.get("target_title", "").strip()
            # Jaminan Anti-Identik: Jika judul persis sama dengan yang pernah dibuat, tambahkan diferensiator sudut pandang
            if target_title.lower() in recent_lower:
                target_title = f"{target_title}: Perspektif Baru & Fakta Mendalam ({datetime.now().strftime('%d %b %Y')})"
            if topic and target_title:
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
    top_signal = live_signals[0]["title"] if live_signals else picked["keyword"]
    fallback_title = f"Menjelajahi Pesona dan Fakta Menarik {picked['keyword']} yang Wajib Anda Ketahui"
    if fallback_title.lower() in recent_lower:
        fallback_title = f"{fallback_title} (Edisi {datetime.now().strftime('%d %b %Y')})"

    return {
        "genre": chosen_genre,
        "trending_keyword": f"{picked['keyword']} (Tren: {top_signal[:45]})",
        "trend_source": "Google News & Trends Indonesia",
        "topic": picked["topic"],
        "target_title": fallback_title,
        "editorial_angle": (
            f"Mengupas tuntas keunikan, latar sejarah, serta daya tarik utama dari {picked['topic']} "
            f"dengan gaya jurnalistik mendalam khas Travelista.id."
        ),
        "raw_signals_count": len(live_signals),
        "live_signals_preview": [s["title"] for s in live_signals[:6]],
        "live_signals_evidence": live_signals[:25],
        "checked_history_list": recent_topics,
        "is_unique_title": True,
    }
