"""
Script Eksekutor Otomasi Harian Travelista AI (09:00 WIB).
Bulan ke-1: Memproduksi 4 artikel harian (1 artikel per genre resmi Travelista: Wisata, Kuliner, Sejarah, Budaya).
Dapat dijalankan oleh GitHub Actions Cron Job, Windows Task Scheduler, atau secara manual via terminal:
    python run_daily_job.py                          # Otomatis buat 4 artikel (1 per genre) & kirim ke CMS
    python run_daily_job.py --genre "Kuliner"        # Buat 1 artikel genre tertentu saja
    python run_daily_job.py --no-send                # Mode uji coba lokal (tanpa kirim ke CMS)
"""
import argparse
import os
import sys

if sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")

sys.path.append(os.path.abspath(os.path.dirname(__file__)))

from dotenv import load_dotenv
load_dotenv()

from src.automation.trend_hunter import TRAVELISTA_GENRES
from src.automation.travelista_sender import send_article_to_travelista_cms


def main():
    parser = argparse.ArgumentParser(description="Travelista Autonomous Daily Article Generator (09:00 WIB - 4 Artikel Harian)")
    parser.add_argument(
        "--genre",
        type=str,
        default=None,
        help=f"Opsional: Paksa 1 genre spesifik dari {TRAVELISTA_GENRES}. Jika dikosongkan (default Bulan ke-1), sistem memproduksi 4 artikel harian untuk semua genre."
    )
    parser.add_argument(
        "--auto-send",
        action="store_true",
        default=True,
        help="Otomatis mengirim artikel yang selesai ke CMS Travelista via Webhook (default: True)."
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

    # Tentukan genre yang akan diproses:
    # Jika --genre dispesifikasikan, proses 1 genre tersebut.
    # Jika dikosongkan, jalankan mode Rekomendasi Bulan ke-1: 4 artikel (1 per genre resmi).
    if args.genre:
        target_genres = [args.genre]
    else:
        target_genres = TRAVELISTA_GENRES

    print("=================================================================")
    print(f"🚀 MEMULAI REDAKSI OTOMATIS HARIAN TRAVELISTA.ID (09:00 WIB | BULAN KE-1: {len(target_genres)} ARTIKEL)")
    print(f"📋 Target Genre: {', '.join(target_genres)}")
    print("=================================================================")

    should_send = args.auto_send and not args.no_send
    env_force_no = os.getenv("AUTO_SEND_TO_CMS", "true").lower() in ("false", "0", "no")
    if env_force_no:
        should_send = False

    target_url = args.cms_url or os.getenv("TRAVELISTA_CMS_URL", "")
    target_key = args.api_key or os.getenv("TRAVELISTA_CMS_API_KEY", "")

    results = []

    from src.automation.daily_pipeline import run_autonomous_daily_pipeline

    for idx, current_genre in enumerate(target_genres, 1):
        print(f"\n[{idx}/{len(target_genres)}] 📝 Memulai pembuatan artikel genre: '{current_genre}'...")
        try:
            result = run_autonomous_daily_pipeline(preferred_genre=current_genre)
            results.append(result)

            print(f"   ✅ Judul: {result.get('final_title')}")
            print(f"   ⏱️  Waktu: {result.get('total_latency')}s | Checker 2: {result.get('final_check_score')}/100")

            # ── Auto-Dispatch ke CMS Travelista via Webhook ────────────
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
                print("   ℹ️ Kirim ke CMS dilewati (--no-send aktif).")

        except Exception as e:
            print(f"   ❌ Gagal memproses genre '{current_genre}': {e}")

    # ── Ringkasan Rekapitulasi Akhir ──────────────────────────────────────────
    print("\n=================================================================")
    print(f"📊 REKAPITULASI {len(results)}/{len(target_genres)} ARTIKEL HARIAN SELESAI DIPRODUKSI (09:00 WIB)")
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
