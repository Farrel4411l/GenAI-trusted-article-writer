"""
Script Eksekutor Otomasi Harian Travelista AI (10:00 WIB).
Dapat dijalankan oleh GitHub Actions Cron Job, Windows Task Scheduler, atau secara manual via terminal:
    python run_daily_job.py
    python run_daily_job.py --genre "Kuliner Nusantara"
"""
import argparse
import os
import sys

if sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")

sys.path.append(os.path.abspath(os.path.dirname(__file__)))

from dotenv import load_dotenv
load_dotenv()

from src.automation.daily_pipeline import run_autonomous_daily_pipeline
from src.automation.trend_hunter import TRAVELISTA_GENRES


def main():
    parser = argparse.ArgumentParser(description="Travelista Autonomous Daily Article Generator (10:00 WIB)")
    parser.add_argument(
        "--genre",
        type=str,
        default=None,
        help=f"Opsional: Paksa genre tertentu dari {TRAVELISTA_GENRES}. Jika dikosongkan, sistem memilih otomatis berdasarkan tren."
    )
    args = parser.parse_args()

    print("=================================================================")
    print("🚀 MEMULAI PROSES REDAKSI OTOMATIS HARIAN TRAVELISTA.ID (10:00 WIB)")
    print("=================================================================")

    result = run_autonomous_daily_pipeline(preferred_genre=args.genre)

    print("\n=================================================================")
    print("✅ RINGKASAN ARTIKEL HARIAN SIAP TERBIT")
    print("=================================================================")
    print(f"Waktu Eksekusi      : {result.get('run_date')}")
    print(f"Genre Terpilih      : {result.get('genre')}")
    print(f"Tren Pemicu         : {result.get('trending_keyword')} ({result.get('trend_source')})")
    print(f"Topik Riset RAG     : {result.get('topic')}")
    print(f"Judul Final         : {result.get('final_title')}")
    print(f"Slug URL            : {result.get('slug')}")
    print(f"Model Writer        : {result.get('writer_model')}")
    print(f"Model Reviewer      : {result.get('reviewer_model')}")
    print(f"Status Checker 1    : {'LULUS' if result.get('fact_check_passed') else 'REVISI MAKS'} ({result.get('fact_check_revisions')} iterasi)")
    print(f"Status Checker 2    : {'LULUS' if result.get('final_check_passed') else 'PERLU REVIEW'} (Skor: {result.get('final_check_score')}/100)")
    print(f"Catatan Checker 2   : {result.get('final_check_notes')}")
    print(f"Total Waktu         : {result.get('total_latency')} detik")
    print("=================================================================")


if __name__ == "__main__":
    main()
