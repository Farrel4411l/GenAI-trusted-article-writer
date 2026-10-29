import csv
import os
import re
from datetime import datetime
from typing import Dict, Any

# Konfigurasi Kuota Token (Budget Harian / Eksperimen) & Profil Rata-rata per Iterasi untuk Tiap Model
MODEL_QUOTAS: Dict[str, Dict[str, Any]] = {
    "gemini/gemini-3.5-flash": {
        "label": "Gemini 3.5 Flash",
        "provider": "Google Gemini",
        "total_quota": 250_000,
        "tpm_limit": 250_000,
        "base_writer_per_iter": 4_200,
        "base_reviewer_per_iter": 4_800,
        "base_grader_tokens": 280,
    },
    "groq/qwen/qwen3.8-27b": {
        "label": "Qwen 3.8 27B (Groq)",
        "provider": "Groq Cloud",
        "total_quota": 100_000,
        "tpm_limit": 8_000,
        "base_writer_per_iter": 4_300,
        "base_reviewer_per_iter": 5_200,
        "base_grader_tokens": 280,
    },
    "groq/openai/gpt-oss-120b": {
        "label": "GPT-OSS 120B (Groq)",
        "provider": "Groq Cloud",
        "total_quota": 100_000,
        "tpm_limit": 8_000,
        "base_writer_per_iter": 4_500,
        "base_reviewer_per_iter": 5_800,
        "base_grader_tokens": 350,
    },
    "groq/openai/gpt-oss-20b": {
        "label": "GPT-OSS 20B (Groq)",
        "provider": "Groq Cloud",
        "total_quota": 150_000,
        "tpm_limit": 8_000,
        "base_writer_per_iter": 4_100,
        "base_reviewer_per_iter": 5_500,
        "base_grader_tokens": 260,
    },
    "cohere/command-a-plus-05-2026": {
        "label": "Command A+ (Cohere)",
        "provider": "Cohere",
        "total_quota": 150_000,
        "tpm_limit": 40_000,
        "base_writer_per_iter": 4_600,
        "base_reviewer_per_iter": 7_500,
        "base_grader_tokens": 320,
    },
}


def get_model_usage_stats(csv_path: str = "experiment_metrics.csv", filter_today: bool = False) -> Dict[str, Dict[str, Any]]:
    """
    Membaca riwayat pemakaian token dari experiment_metrics.csv dan menghitung:
    - Sisa token (angka & persentase) untuk setiap opsi model
    - Rata-rata historis pemakaian token per iterasi
    """
    stats: Dict[str, Dict[str, Any]] = {}
    for model_id, cfg in MODEL_QUOTAS.items():
        stats[model_id] = {
            "label": cfg["label"],
            "provider": cfg["provider"],
            "total_quota": cfg["total_quota"],
            "tpm_limit": cfg["tpm_limit"],
            "used_tokens": 0,
            "writer_runs_tokens": [],
            "reviewer_runs_tokens": [],
            "grader_runs_tokens": [],
        }

    today_str = datetime.now().strftime("%Y-%m-%d")

    if os.path.isfile(csv_path):
        try:
            with open(csv_path, mode="r", encoding="utf-8") as f:
                reader = csv.reader(f)
                rows = list(reader)
                for row in rows[1:]:  # lewati header
                    if not row or len(row) < 8:
                        continue
                    timestamp = row[0].strip()
                    if filter_today and not timestamp.startswith(today_str):
                        continue

                    writer_model = row[2].strip()
                    reviewer_model = row[3].strip()
                    try:
                        revisions = max(1, int(row[4]))
                    except Exception:
                        revisions = 1

                    try:
                        writer_tokens = int(float(row[6]))
                    except Exception:
                        writer_tokens = 0

                    try:
                        reviewer_tokens = int(float(row[7]))
                    except Exception:
                        reviewer_tokens = 0

                    grader_tokens = 0
                    if len(row) >= 10:
                        try:
                            grader_tokens = int(float(row[8]))
                        except Exception:
                            grader_tokens = 0

                    if writer_model in stats:
                        stats[writer_model]["used_tokens"] += (writer_tokens + grader_tokens)
                        if writer_tokens >= 1000:
                            stats[writer_model]["writer_runs_tokens"].append(writer_tokens / revisions)
                        if grader_tokens > 0:
                            stats[writer_model]["grader_runs_tokens"].append(grader_tokens)

                    if reviewer_model in stats:
                        stats[reviewer_model]["used_tokens"] += reviewer_tokens
                        if reviewer_tokens >= 1000:
                            stats[reviewer_model]["reviewer_runs_tokens"].append(reviewer_tokens / revisions)
        except Exception as e:
            print(f"[TokenTracker] Gagal membaca CSV: {e}")

    # Hitung sisa kuota (angka & persen) dan rata-rata per iterasi
    for model_id, data in stats.items():
        cfg = MODEL_QUOTAS[model_id]
        total = data["total_quota"]
        used = data["used_tokens"]
        remaining = max(0, total - used)
        remaining_pct = round((remaining / total) * 100, 2) if total > 0 else 0.0
        used_pct = round((used / total) * 100, 2) if total > 0 else 0.0

        w_list = data["writer_runs_tokens"]
        r_list = data["reviewer_runs_tokens"]
        g_list = data["grader_runs_tokens"]

        avg_writer = int((sum(w_list) / len(w_list) + cfg["base_writer_per_iter"]) / 2) if w_list else cfg["base_writer_per_iter"]
        avg_reviewer = int((sum(r_list) / len(r_list) + cfg["base_reviewer_per_iter"]) / 2) if r_list else cfg["base_reviewer_per_iter"]
        avg_grader = int((sum(g_list) / len(g_list) + cfg["base_grader_tokens"]) / 2) if g_list else cfg["base_grader_tokens"]

        data["remaining_tokens"] = remaining
        data["remaining_pct"] = remaining_pct
        data["used_pct"] = used_pct
        data["avg_writer_per_iter"] = avg_writer
        data["avg_reviewer_per_iter"] = avg_reviewer
        data["avg_grader_tokens"] = avg_grader

    return stats


def predict_token_usage(
    writer_model_id: str,
    reviewer_model_id: str,
    topic: str = "",
    expected_iterations: int = 1,
    stats: Dict[str, Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Memprediksi jumlah token dan persentase kuota yang akan dihabiskan
    sebelum mesin dijalankan.
    """
    if stats is None:
        stats = get_model_usage_stats()

    w_stat = stats.get(writer_model_id, next(iter(stats.values())))
    r_stat = stats.get(reviewer_model_id, next(iter(stats.values())))

    # Faktor kompleksitas topik (jumlah sub-topik / panjang kata)
    cleaned_topic = topic.strip()
    if cleaned_topic:
        parts = [p.strip() for p in re.split(r'\b(?:dan|serta|atau|vs|versus|dengan)\b|[,&/+]', cleaned_topic, flags=re.IGNORECASE) if len(p.strip()) >= 3]
        num_entities = max(1, len(parts))
        word_count = len(cleaned_topic.split())
    else:
        num_entities = 1
        word_count = 3

    # Penyesuaian dinamis berdasarkan kompleksitas topik
    entity_multiplier = 1.0 + (0.08 * (num_entities - 1)) + min(0.05, word_count * 0.005)

    pred_grader = int(w_stat["avg_grader_tokens"] * (1.0 + 0.15 * (num_entities - 1)))
    pred_writer_1x = int(w_stat["avg_writer_per_iter"] * entity_multiplier)
    pred_reviewer_1x = int(r_stat["avg_reviewer_per_iter"] * entity_multiplier)

    pred_vision = 650  # Estimasi inspeksi visual Agent Vision Reviewer (Gemini 3.5 Flash)

    pred_writer = pred_writer_1x * expected_iterations
    pred_reviewer = pred_reviewer_1x * expected_iterations
    pred_writer_total = pred_writer + pred_grader  # Grader memakai model Writer
    pred_total_all = pred_writer_total + pred_reviewer + pred_vision

    # Persentase terhadap Total Kuota & Sisa Kuota Model Writer
    w_total_quota = w_stat["total_quota"]
    w_rem_quota = max(1, w_stat["remaining_tokens"])
    writer_pct_of_total = round((pred_writer_total / w_total_quota) * 100, 2)
    writer_pct_of_remaining = round((pred_writer_total / w_rem_quota) * 100, 2)

    # Persentase terhadap Total Kuota & Sisa Kuota Model Reviewer
    r_total_quota = r_stat["total_quota"]
    r_rem_quota = max(1, r_stat["remaining_tokens"])
    reviewer_pct_of_total = round((pred_reviewer / r_total_quota) * 100, 2)
    reviewer_pct_of_remaining = round((pred_reviewer / r_rem_quota) * 100, 2)

    # Jika model Writer dan Reviewer sama, gabungkan terhadap satu kuota yang sama
    same_model = (writer_model_id == reviewer_model_id)
    if same_model:
        combined_total_quota = w_total_quota
        combined_rem_quota = w_rem_quota
    else:
        combined_total_quota = w_total_quota + r_total_quota
        combined_rem_quota = w_rem_quota + r_rem_quota

    total_pct_of_total = round((pred_total_all / combined_total_quota) * 100, 2)
    total_pct_of_remaining = round((pred_total_all / combined_rem_quota) * 100, 2)

    return {
        "num_entities": num_entities,
        "expected_iterations": expected_iterations,
        "pred_grader": pred_grader,
        "pred_writer": pred_writer,
        "pred_writer_total": pred_writer_total,
        "pred_reviewer": pred_reviewer,
        "pred_vision": pred_vision,
        "pred_total_all": pred_total_all,
        "writer_pct_of_total": writer_pct_of_total,
        "writer_pct_of_remaining": writer_pct_of_remaining,
        "reviewer_pct_of_total": reviewer_pct_of_total,
        "reviewer_pct_of_remaining": reviewer_pct_of_remaining,
        "total_pct_of_total": total_pct_of_total,
        "total_pct_of_remaining": total_pct_of_remaining,
        "same_model": same_model,
        "combined_total_quota": combined_total_quota,
        "combined_rem_quota": combined_rem_quota,
    }
