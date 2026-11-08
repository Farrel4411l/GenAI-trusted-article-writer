"""
Script Eksekutor Otomasi Harian Travelista AI (Bank Naskah H-1: 21:15 WIB untuk Tayang 09:00 WIB).
Bulan ke-1: Memproduksi 4 artikel harian (1 artikel per genre resmi Travelista: Wisata, Kuliner, Sejarah, Budaya).
Dilengkapi dengan Sistem Anti-Gagal (Cooldown RPM, Exponential Retry 3x, dan Sweep Recovery Pass) agar selalu genap 4 artikel per hari.

Dapat dijalankan oleh GitHub Actions Cron Job, Windows Task Scheduler, atau secara manual via terminal:
    python run_daily_job.py                          # Otomatis buat 4 artikel (1 per genre) & simpan di Supabase
    python run_daily_job.py --genre "Kuliner"        # Buat 1 artikel genre tertentu saja
    python run_daily_job.py --auto-send              # Mode produksi: langsung kirim ke CMS Travelista
    python run_daily_job.py --no-send                # Mode uji coba lokal / sandbox (default)
"""
import argparse
import os
import sys
import time

if sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")

sys.path.append(os.path.abspath(os.path.dirname(__file__)))

from dotenv import load_dotenv
load_dotenv()

from src.automation.trend_hunter import TRAVELISTA_GENRES
from src.automation.travelista_sender import send_article_to_travelista_cms

MAX_GENRE_RETRIES = 3
RETRY_BACKOFF_SECONDS = [10, 20, 30]
COOLDOWN_BETWEEN_GENRES = 15  # Detik jeda antar genre untuk mencegah rate-limit RPM


def execute_single_genre_with_retry(genre_name: str, max_retries: int = MAX_GENRE_RETRIES):
    """
    Mengeksekusi pipeline pembuatan artikel untuk 1 genre tertentu dengan mekanisme
    retry loop otomatis dan exponential backoff jika terjadi kendala jaringan/rate limit.
    """
    from src.automation.daily_pipeline import run_autonomous_daily_pipeline

    last_error = None
    for attempt in range(1, max_retries + 1):
        try:
            if attempt > 1:
                backoff_time = RETRY_BACKOFF_SECONDS[min(attempt - 2, len(RETRY_BACKOFF_SECONDS) - 1)]
                print(f"   🔄 [Percobaan {attempt}/{max_retries}] Mengulang genre '{genre_name}' setelah jeda {backoff_time}s...")
                time.sleep(backoff_time)

            result = run_autonomous_daily_pipeline(preferred_genre=genre_name)
            return result
        except Exception as e:
            last_error = e
            print(f"   ⚠️ Percobaan {attempt}/{max_retries} untuk genre '{genre_name}' gagal: {e}")

    raise RuntimeError(f"Gagal memproses genre '{genre_name}' setelah {max_retries} percobaan: {last_error}")


def main():
    parser = argparse.ArgumentParser(
        description="Travelista Autonomous Daily Article Generator (Bank Naskah H-1: 21:15 WIB untuk Tayang 09:00 WIB)"
    )
    parser.add_argument(
        "--genre",
        type=str,
        default=None,
        help=f"Opsional: Paksa 1 genre spesifik dari {TRAVELISTA_GENRES}. Jika dikosongkan (default Bulan ke-1), sistem memproduksi 4 artikel harian untuk semua genre."
    )
    parser.add_argument(
        "--auto-send",
        action="store_true",
        default=False,
        help="Kirim artikel yang selesai ke CMS Travelista via Webhook (default: False / Mode 1 Sandbox)."
    )
    parser.add_argument(
        "--no-send",
        action="store_true",
        default=False,
        help="Melewatkan pengiriman ke CMS Travelista (hanya simpan di database lokal & Supabase)."
    )
    parser.add_argument(
        "--cms-url",
        type=str,
        default=None,
        help="URL CMS Travelista (opsional, override TRAVELISTA_CMS_URL di .env)."
    )
    parser.add_argument(
        "--api-key",
        type=str,
        default=None,
        help="API Key Webhook CMS Travelista (opsional, override TRAVELISTA_CMS_API_KEY di .env)."
    )
    args = parser.parse_args()

    # Jika --genre dispesifikasikan, proses 1 genre tersebut.
    # Jika dikosongkan, jalankan mode Rekomendasi Bulan ke-1: 4 artikel (1 per genre resmi).
    if args.genre:
        target_genres = [args.genre]
    else:
        target_genres = list(TRAVELISTA_GENRES)

    print("=================================================================")
    print(f"🚀 MEMULAI REDAKSI OTOMATIS HARIAN TRAVELISTA.ID (BANK NASKAH H-1: 21:15 WIB)")
    print(f"🎯 Target Rilis Redaksi: Pukul 09:00 WIB Hari H (100% Siap Publish)")
    print(f"📋 Target Genre ({len(target_genres)} Artikel): {', '.join(target_genres)}")
    print("=================================================================")

    # Mode 1 Sandbox (Default): Aman 100%, hanya simpan di Supabase & Streamlit pribadi
    env_send = os.getenv("AUTO_SEND_TO_CMS", "false").lower() in ("true", "1", "yes")
    should_send = (args.auto_send or env_send) and not args.no_send

    target_url = args.cms_url or os.getenv("TRAVELISTA_CMS_URL", "")
    target_key = args.api_key or os.getenv("TRAVELISTA_CMS_API_KEY", "")

    results = []
    completed_genres = set()

    # ── Putaran Utama (Primary Pass) dengan Jeda Cooldown ──────────────
    for idx, current_genre in enumerate(target_genres, 1):
        print(f"\n[{idx}/{len(target_genres)}] 📝 Memproses artikel genre: '{current_genre}'...")
        try:
            result = execute_single_genre_with_retry(current_genre)
            results.append(result)
            completed_genres.add(current_genre)

            print(f"   ✅ Judul: {result.get('final_title')}")
            print(f"   ⏱️  Waktu: {result.get('total_latency')}s | Checker 2: {result.get('final_check_score')}/100")

            # Auto-Dispatch ke CMS jika diizinkan
            if should_send:
                cms_payload = result.get("cms_payload", {})
                if cms_payload:
                    ok, msg, _ = send_article_to_travelista_cms(
                        payload=cms_payload,
                        cms_url=target_url,
                        api_key=target_key
                    )
                    if ok:
                        print(f"   🎉 Terkirim ke CMS: {msg}")
                    else:
                        print(f"   ⚠️ Peringatan Kirim: {msg}")
                else:
                    print("   ⚠️ Payload CMS kosong, kirim dilewati.")
            else:
                print("   ℹ️ Kirim ke CMS dilewati (Mode 1 Sandbox aktif).")

        except Exception as e:
            print(f"   ❌ Gagal memproses genre '{current_genre}' pada putaran utama: {e}")

        # Cooldown jeda antar genre untuk menjaga kestabilan kuota RPM API
        if idx < len(target_genres):
            print(f"   ⏳ Cooldown sistem {COOLDOWN_BETWEEN_GENRES} detik sebelum genre berikutnya...")
            time.sleep(COOLDOWN_BETWEEN_GENRES)

    # ── Putaran Pemulihan (Sweep Recovery Pass) Anti-Gagal ────────────
    # Jika ada genre yang gagal pada putaran utama, lakukan recovery pass agar selalu genap 4 artikel!
    missing_genres = [g for g in target_genres if g not in completed_genres]
    if missing_genres:
        print("\n=================================================================")
        print(f"🛠️ MENJALANKAN SWEEP RECOVERY PASS UNTUK {len(missing_genres)} GENRE YANG TERTINGGAL")
        print("=================================================================")
        time.sleep(20)  # Istirahat ekstra sebelum recovery

        for recovery_idx, rec_genre in enumerate(missing_genres, 1):
            print(f"\n[Recovery {recovery_idx}/{len(missing_genres)}] 🚑 Memulihkan genre: '{rec_genre}'...")
            try:
                result = execute_single_genre_with_retry(rec_genre, max_retries=2)
                results.append(result)
                completed_genres.add(rec_genre)
                print(f"   🎉 BERHASIL DIPULIHKAN: {result.get('final_title')}")

                if should_send:
                    cms_payload = result.get("cms_payload", {})
                    if cms_payload:
                        send_article_to_travelista_cms(payload=cms_payload, cms_url=target_url, api_key=target_key)
            except Exception as e_rec:
                print(f"   ❌ Recovery genre '{rec_genre}' tetap gagal: {e_rec}")

    # ── Ringkasan Rekapitulasi Akhir ──────────────────────────────────────────
    print("\n=================================================================")
    print(f"📊 REKAPITULASI {len(results)}/{len(target_genres)} ARTIKEL HARIAN SELESAI DIPRODUKSI")
    print(f"📅 Status: Bank Naskah H-1 Siap Tayang Pukul 09:00 WIB Hari H")
    print("=================================================================")
    for i, r in enumerate(results, 1):
        print(f"{i}. [{r.get('genre')}]")
        print(f"   Judul : {r.get('final_title')}")
        print(f"   Slug  : /{r.get('slug')}")
        print(f"   Cover : {r.get('cover_image_url') or 'Placeholder'} (16:9 WebP)")
        print(f"   Skor  : {r.get('final_check_score')}/100 | Waktu: {r.get('total_latency')}s")
    print("=================================================================")


if __name__ == "__main__":
    main()
