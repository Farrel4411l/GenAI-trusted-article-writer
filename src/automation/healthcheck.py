"""
Modul Healthcheck & Early Warning System untuk Otomasi Redaksi Travelista AI.
Memantau kesehatan GitHub Actions cron job, integritas workflow YAML,
dan keterpenuhan Bank Naskah H-1 (4 artikel / hari) di Supabase.
"""
import requests
import datetime
from zoneinfo import ZoneInfo
from typing import Dict, Any, List

WIB_TZ = ZoneInfo("Asia/Jakarta")
GITHUB_REPO = "Farrel4411l/GenAI-trusted-article-writer"
WORKFLOW_ID = "398953240"
SCHEDULED_TIME_STR = "21:15 WIB"


def check_github_actions_health(timeout: int = 5) -> Dict[str, Any]:
    """
    Memeriksa status riil GitHub Actions workflow & riwayat eksekusi terakhir via GitHub API.
    """
    res = {
        "is_reachable": False,
        "workflow_state": "unknown",
        "workflow_name": "Travelista Daily Automated Editorial",
        "last_run_id": None,
        "last_run_event": None,
        "last_run_conclusion": "unknown",
        "last_run_date_wib": "-",
        "last_run_url": f"https://github.com/{GITHUB_REPO}/actions",
        "next_cron_hint": f"Setiap malam pukul {SCHEDULED_TIME_STR} (14:15 UTC)",
        "error_detail": "",
    }

    try:
        # 1. Cek State Workflow
        wf_url = f"https://api.github.com/repos/{GITHUB_REPO}/actions/workflows/{WORKFLOW_ID}"
        r_wf = requests.get(wf_url, timeout=timeout)
        if r_wf.status_code == 200:
            wf_data = r_wf.json()
            res["is_reachable"] = True
            res["workflow_state"] = wf_data.get("state", "active")
            res["workflow_name"] = wf_data.get("name", res["workflow_name"])

        # 2. Cek Riwayat Run Terakhir
        runs_url = f"https://api.github.com/repos/{GITHUB_REPO}/actions/runs?per_page=3"
        r_runs = requests.get(runs_url, timeout=timeout)
        if r_runs.status_code == 200:
            runs_data = r_runs.json().get("workflow_runs", [])
            if runs_data:
                latest_run = runs_data[0]
                res["is_reachable"] = True
                res["last_run_id"] = latest_run.get("id")
                res["last_run_event"] = latest_run.get("event")
                res["last_run_conclusion"] = latest_run.get("conclusion")
                res["last_run_url"] = latest_run.get("html_url")

                # Konversi waktu UTC ke WIB
                created_utc_str = latest_run.get("created_at")
                if created_utc_str:
                    try:
                        dt_utc = datetime.datetime.fromisoformat(created_utc_str.replace("Z", "+00:00"))
                        dt_wib = dt_utc.astimezone(WIB_TZ)
                        res["last_run_date_wib"] = dt_wib.strftime("%d %b %Y, %H:%M WIB")
                    except Exception:
                        res["last_run_date_wib"] = created_utc_str

    except Exception as e:
        res["error_detail"] = str(e)

    return res


def evaluate_system_health(
    saved_articles: List[Dict[str, Any]],
    gh_health: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Mengevaluasi secara menyeluruh apakah sistem dalam kondisi:
    - 'healthy' (Hijau: Cron aktif, artikel lengkap 4)
    - 'warning' (Kuning: Ada keterlambatan / naskah belum genap 4)
    - 'critical' (Merah: Cron GitHub gagal atau bot mogok)
    """
    now_wib = datetime.datetime.now(WIB_TZ)
    today_str = now_wib.strftime("%Y-%m-%d")

    # Hitung artikel yang dibuat hari ini atau kemarin
    articles_by_date: Dict[str, List[Dict[str, Any]]] = {}
    for a in saved_articles:
        run_d = str(a.get("run_date") or a.get("created_at") or "")[:10]
        if run_d:
            articles_by_date.setdefault(run_d, []).append(a)

    latest_date = max(articles_by_date.keys()) if articles_by_date else "-"
    latest_batch_count = len(articles_by_date.get(latest_date, []))

    gh_conclusion = gh_health.get("last_run_conclusion", "unknown")
    wf_state = gh_health.get("workflow_state", "active")

    # Deteksi Masalah
    alerts = []
    level = "healthy"

    # 1. Peringatan Kegagalan GitHub Actions
    if gh_conclusion == "failure":
        level = "critical"
        alerts.append("Eksekusi GitHub Actions terakhir GAGAL (terdeteksi error pada pipeline runner).")
    elif wf_state != "active" and gh_health.get("is_reachable"):
        level = "critical"
        alerts.append(f"Workflow GitHub Actions berstatus '{wf_state}' (tidak aktif).")

    # 2. Peringatan Kekurangan Naskah (< 4 artikel)
    if latest_batch_count > 0 and latest_batch_count < 4:
        if level != "critical":
            level = "warning"
        alerts.append(f"Bank Naskah pada tanggal {latest_date} hanya berisi {latest_batch_count}/4 artikel (kurang {4 - latest_batch_count} genre).")

    # 3. Peringatan Stale / Tertinggal (> 24 jam belum ada naskah baru)
    if latest_date != "-":
        try:
            dt_latest = datetime.datetime.strptime(latest_date, "%Y-%m-%d").date()
            days_gap = (now_wib.date() - dt_latest).days
            if days_gap > 1:
                level = "critical"
                alerts.append(f"Tidak ada naskah baru selama {days_gap} hari terakhir (terakhir terisi {latest_date}).")
        except Exception:
            pass

    # Status & Badge
    if level == "healthy":
        badge = "🟢 SISTEM SEHAT & NORMAL"
        summary = "GitHub Actions Cron aktif dan Bank Naskah H-1 (4 artikel/hari) beroperasi tepat waktu."
    elif level == "warning":
        badge = "🟡 PERHATIAN REDAKSI"
        summary = "Sistem berjalan, namun kuota Bank Naskah belum genap 4 artikel harian."
    else:
        badge = "🔴 PERINGATAN KRITIS"
        summary = "Terdeteksi kendala pada otomatisasi atau jadwal runner GitHub Actions."

    return {
        "level": level,
        "badge": badge,
        "summary": summary,
        "alerts": alerts,
        "latest_date": latest_date,
        "latest_batch_count": latest_batch_count,
        "gh_health": gh_health,
        "evaluated_at": now_wib.strftime("%d %b %Y, %H:%M:%S WIB"),
    }
