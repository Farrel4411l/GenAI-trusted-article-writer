import os
import re
import io
import html
import urllib.parse
from typing import Dict, Any, Optional, Tuple
import requests
from PIL import Image
from dotenv import load_dotenv

load_dotenv()

# Direktori lokal untuk menyimpan salinan WebP
LOCAL_COVERS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "static", "covers")
os.makedirs(LOCAL_COVERS_DIR, exist_ok=True)


def _slugify(text: str) -> str:
    slug = text.lower().strip()
    slug = re.sub(r"[^a-z0-9\s-]", "", slug)
    slug = re.sub(r"[\s-]+", "-", slug).strip("-")
    return slug[:80] or "cover-image"


def build_vision_prompt(topic: str, title: str, genre: str, editorial_angle: str = "") -> str:
    """
    Menyusun prompt visual dalam bahasa Inggris dengan gaya fotografi editorial Travelista
    untuk menghasilkan gambar berkualitas tinggi dan bebas halusinasi visual.
    """
    g_lower = (genre or "").lower()
    
    if "kuliner" in g_lower:
        genre_style = (
            "authentic Indonesian culinary food photography, appetizing dish presentation on traditional pottery "
            "and banana leaf, garnishes, shallow depth of field, warm natural restaurant table lighting, 8k resolution, photorealistic"
        )
    elif "sejarah" in g_lower or "budaya" in g_lower:
        genre_style = (
            "historical cultural heritage documentary photography, majestic architectural perspective, authentic Indonesian "
            "ancient cultural site, morning mist, warm golden hour sunbeams, National Geographic editorial style, highly detailed 8k"
        )
    else:  # Wisata / Destinasi / Alam
        genre_style = (
            "breathtaking Indonesian landscape and travel photography, wide angle view, vibrant tropical natural scenery, "
            "cinematic golden hour atmosphere, ultra-detailed 8k resolution, award-winning travel magazine cover"
        )

    clean_topic = re.sub(r"[^\w\s-]", "", topic).strip()
    clean_title = re.sub(r"[^\w\s-]", "", title).strip()

    prompt = (
        f"Award-winning editorial travel photography, 16:9 aspect ratio, {clean_topic}, {clean_title}, "
        f"{genre_style}, shot on 35mm lens, sharp focus, professional color grading, no text, no watermark, masterpiece"
    )
    return prompt[:450]


def crop_and_optimize_webp(image_bytes: bytes, target_size: Tuple[int, int] = (1200, 675), quality: int = 85) -> bytes:
    """
    Memotong gambar menjadi rasio 16:9 (center crop) dan mengompresinya
    ke format WebP sesuai standar performa web Travelista 2026 (< 400 KB).
    """
    im = Image.open(io.BytesIO(image_bytes))
    if im.mode in ("RGBA", "P"):
        im = im.convert("RGB")

    target_w, target_h = target_size
    target_aspect = target_w / target_h
    img_aspect = im.width / im.height

    if img_aspect > target_aspect:
        # Gambar lebih lebar dari 16:9 -> crop sisi kiri & kanan
        new_w = int(im.height * target_aspect)
        left = (im.width - new_w) // 2
        im_cropped = im.crop((left, 0, left + new_w, im.height))
    else:
        # Gambar lebih tinggi dari 16:9 -> crop sisi atas & bawah
        new_h = int(im.width / target_aspect)
        top = (im.height - new_h) // 2
        im_cropped = im.crop((0, top, im.width, top + new_h))

    im_resized = im_cropped.resize((target_w, target_h), Image.Resampling.LANCZOS)

    out_buf = io.BytesIO()
    im_resized.save(out_buf, format="WEBP", quality=quality, method=6)
    return out_buf.getvalue()


def fetch_wikimedia_image(topic: str, title: str = "") -> Optional[Tuple[bytes, str, str]]:
    """
    Mencari foto asli berlisensi bebas (Creative Commons / Public Domain) dari Wikipedia Indonesia.
    Sangat diutamakan untuk topik Sejarah & Cagar Budaya agar 100% akurat secara arkeologis.
    """
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) TravelistaEditorial/2.0"}
    candidates = [
        topic.strip().replace(" ", "_"),
        topic.strip().title().replace(" ", "_"),
    ]
    if "candi" in topic.lower():
        candidates.append("Percandian_" + topic.replace("Candi", "").strip().title().replace(" ", "_"))
        candidates.append("Kompleks_" + topic.strip().title().replace(" ", "_"))
        candidates.append("Situs_" + topic.replace("Candi", "").strip().title().replace(" ", "_"))

    for slug in candidates:
        url = f"https://id.wikipedia.org/wiki/{urllib.parse.quote(slug)}"
        try:
            r = requests.get(url, headers=headers, timeout=6)
            if r.status_code != 200:
                continue

            # Cari tag <meta property="og:image" content="...">
            m = re.search(r'<meta\s+property=["\']og:image["\']\s+content=["\']([^"\']+)["\']', r.text, flags=re.IGNORECASE)
            if not m:
                continue

            img_url = html.unescape(m.group(1).strip())
            # Abaikan jika ikon, peta, logo, atau stub
            img_lower = img_url.lower()
            if any(k in img_lower for k in ["logo", "icon", "stub", "flag", "peta", "map", ".svg", ".gif"]):
                continue

            ir = requests.get(img_url, headers=headers, timeout=10)
            if ir.status_code == 200 and len(ir.content) > 15_000:
                # Verifikasi ukuran dimensi
                test_im = Image.open(io.BytesIO(ir.content))
                if test_im.width >= 500 and test_im.height >= 300:
                    optimized_webp = crop_and_optimize_webp(ir.content)
                    return optimized_webp, img_url, f"Foto dokumenter {topic} via Wikimedia Commons"
        except Exception as e:
            print(f"[Image Hunter] Info cek Wikimedia untuk {slug}: {e}")
            continue

    return None


def generate_ai_image(prompt: str) -> Optional[Tuple[bytes, str, str]]:
    """
    Men-generate gambar AI fotorealistis menggunakan model FLUX / SDXL
    beresolusi tinggi 1200x675 (rasio 16:9).
    """
    encoded_prompt = urllib.parse.quote(prompt[:400])
    ai_url = f"https://image.pollinations.ai/prompt/{encoded_prompt}?width=1200&height=675&nologo=true&seed=42"

    headers = {"User-Agent": "Mozilla/5.0 TravelistaEditorial/2.0"}
    try:
        r = requests.get(ai_url, headers=headers, timeout=25)
        if r.status_code == 200 and len(r.content) > 20_000:
            optimized_webp = crop_and_optimize_webp(r.content)
            return optimized_webp, ai_url, "AI Generated Editorial Photography (16:9 WebP)"
    except Exception as e:
        print(f"[Image Hunter] Gagal generate AI image: {e}")

    return None


def upload_to_supabase_storage(file_bytes: bytes, file_name: str, bucket_name: str = "article-covers") -> Optional[str]:
    """
    Mengunggah file WebP ke bucket Supabase Storage jika SUPABASE_URL & SUPABASE_KEY tersedia.
    Mengembalikan URL publik HTTPS langsung.
    """
    supabase_url = os.getenv("SUPABASE_URL")
    if not supabase_url:
        db_host = os.getenv("POSTGRES_HOST", "")
        if "supabase.co" in db_host:
            project_ref = db_host.replace("db.", "").replace(".supabase.co", "")
            supabase_url = f"https://{project_ref}.supabase.co"

    supabase_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_KEY") or os.getenv("SUPABASE_ANON_KEY")

    if not supabase_url or not supabase_key:
        return None

    upload_endpoint = f"{supabase_url.rstrip('/')}/storage/v1/object/{bucket_name}/{file_name}"
    headers = {
        "Authorization": f"Bearer {supabase_key}",
        "apiKey": supabase_key,
        "Content-Type": "image/webp",
        "x-upsert": "true",
    }

    try:
        r = requests.post(upload_endpoint, data=file_bytes, headers=headers, timeout=12)
        if r.status_code in (200, 201):
            public_url = f"{supabase_url.rstrip('/')}/storage/v1/object/public/{bucket_name}/{file_name}"
            return public_url
        else:
            print(f"[Image Hunter] Supabase storage upload response ({r.status_code}): {r.text[:200]}")
    except Exception as e:
        print(f"[Image Hunter] Gagal upload ke Supabase Storage: {e}")

    return None


def acquire_cover_image(
    topic: str,
    title: str,
    genre: str,
    slug: str,
    editorial_angle: str = "",
    prefer_real_first: bool = True
) -> Dict[str, Any]:
    """
    Fungsi Utama: Mengakuisisi gambar sampul 16:9 WebP (< 400KB)
    dengan pendekatan Hybrid (Akurat & Cocok):
    1. Cek foto asli Wikimedia Commons (prioritas utama cagar budaya/sejarah).
    2. Fallback ke Generative AI (FLUX 16:9) jika foto asli tidak ada.
    3. Simpan salinan lokal & upload ke Supabase Storage jika credential ada.
    """
    print(f"\n[Image Hunter] Mencari gambar sampul 16:9 untuk: '{title}' ({genre})...")

    alt_text = f"Pemandangan dan dokumentasi {topic} untuk artikel {title} di Travelista.id"
    clean_slug = _slugify(slug)
    file_name = f"{clean_slug}.webp"
    local_path = os.path.join(LOCAL_COVERS_DIR, file_name)

    image_bytes = None
    source_type = "unknown"
    original_url = ""

    # Tier 1: Coba cari foto asli di Wikimedia
    if prefer_real_first:
        wiki_res = fetch_wikimedia_image(topic, title)
        if wiki_res:
            image_bytes, original_url, desc = wiki_res
            source_type = "wikimedia_real"
            print(f"[Image Hunter] [OK] Berhasil menemukan foto asli dari Wikimedia Commons: {original_url[:60]}...")

    # Tier 2: AI Generatif jika belum ada foto
    if not image_bytes:
        print(f"[Image Hunter] Merumuskan prompt visual AI berdasarkan konteks RAG...")
        prompt = build_vision_prompt(topic, title, genre, editorial_angle)
        ai_res = generate_ai_image(prompt)
        if ai_res:
            image_bytes, original_url, desc = ai_res
            source_type = "ai_generative"
            print(f"[Image Hunter] [OK] Berhasil men-generate gambar AI (16:9 WebP).")

    # Fallback darurat jika gagal semua
    if not image_bytes:
        # Buat dummy 1200x675 gradient placeholder agar tidak null
        im = Image.new("RGB", (1200, 675), color=(41, 128, 185))
        buf = io.BytesIO()
        im.save(buf, format="WEBP", quality=80)
        image_bytes = buf.getvalue()
        source_type = "fallback_placeholder"
        original_url = "https://images.unsplash.com/photo-1507525428034-b723cf961d3e"

    # Simpan file lokal
    with open(local_path, "wb") as f:
        f.write(image_bytes)

    file_size_kb = round(len(image_bytes) / 1024, 2)

    # Tier 3: Upload ke Supabase Storage jika dikonfigurasi
    public_storage_url = upload_to_supabase_storage(image_bytes, file_name)
    final_cover_url = public_storage_url or original_url

    return {
        "cover_image_url": final_cover_url,
        "cover_image_alt": alt_text,
        "source_type": source_type,
        "original_source_url": original_url,
        "dimensions": "1200x675",
        "aspect_ratio": "16:9",
        "format": "webp",
        "file_size_kb": file_size_kb,
        "local_filepath": local_path,
        "file_name": file_name,
        "storage_uploaded": bool(public_storage_url),
    }
