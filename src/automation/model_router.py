import os
import time
from typing import Dict, Any, List, Optional
from dotenv import load_dotenv
from src.utils.token_tracker import get_model_usage_stats, MODEL_QUOTAS

load_dotenv()

# Matriks Urutan Prioritas Model Berdasarkan Genre Travelista
# Catatan Arsitektur: Model Writer juga digunakan oleh Agent Grader di `orchestrator.py`.
# Gemini 3.5 Flash tidak memiliki batasan max_tokens=1000 di llm_factory.py maupun pemotongan
# reasoning token pada max_tokens=60 di search.py, sehingga sangat optimal sebagai Writer+Grader,
# dipasangkan secara Cross-Model dengan GPT-OSS 120B / 20B (Groq) atau Command A+ sebagai Reviewer.
GENRE_MODEL_PREFERENCES: Dict[str, Dict[str, List[str]]] = {
    "Wisata & Destinasi (Travel)": {
        "writer": [
            "gemini/gemini-3.5-flash",
            "groq/openai/gpt-oss-120b",
            "groq/qwen/qwen3.8-27b",
            "cohere/command-a-plus-05-2026",
        ],
        "reviewer": [
            "groq/openai/gpt-oss-120b",
            "cohere/command-a-plus-05-2026",
            "groq/openai/gpt-oss-20b",
            "groq/qwen/qwen3.8-27b",
            "gemini/gemini-3.5-flash",
        ],
        "rationale": (
            "Genre Wisata & Destinasi membutuhkan narasi panjang 5-8 paragraf yang utuh tanpa "
            "pemotongan token output (dipilih Gemini 3.5 Flash sebagai Writer+Grader) dan "
            "diverifikasi silang oleh GPT-OSS 120B (Groq) / Command A+ (Cohere) sebagai Fact-Checker."
        ),
    },
    "Kuliner Nusantara": {
        "writer": [
            "gemini/gemini-3.5-flash",
            "groq/openai/gpt-oss-120b",
            "groq/qwen/qwen3.8-27b",
            "cohere/command-a-plus-05-2026",
        ],
        "reviewer": [
            "cohere/command-a-plus-05-2026",
            "groq/openai/gpt-oss-120b",
            "groq/openai/gpt-oss-20b",
            "groq/qwen/qwen3.8-27b",
            "gemini/gemini-3.5-flash",
        ],
        "rationale": (
            "Genre Kuliner Nusantara menuntut deskripsi mendalam 5-8 paragraf beserta sitasi lengkap "
            "(Gemini 3.5 Flash sebagai Writer+Grader) dengan evaluasi lintas-model oleh Command A+ (Cohere, 40K TPM) / GPT-OSS 120B (Groq)."
        ),
    },
    "Sejarah & Misteri Lokal": {
        "writer": [
            "gemini/gemini-3.5-flash",
            "groq/openai/gpt-oss-120b",
            "groq/qwen/qwen3.8-27b",
            "cohere/command-a-plus-05-2026",
        ],
        "reviewer": [
            "groq/openai/gpt-oss-120b",
            "cohere/command-a-plus-05-2026",
            "groq/openai/gpt-oss-20b",
            "groq/qwen/qwen3.8-27b",
            "gemini/gemini-3.5-flash",
        ],
        "rationale": (
            "Genre Sejarah & Misteri Lokal padat akan angka tahun, nama tokoh, dan kronologi "
            "sehingga menggunakan Gemini 3.5 Flash (konteks luas untuk sintesis multi-dokumen & Grader) "
            "serta GPT-OSS 120B (Groq) / Command A+ (Cohere) sebagai Fact-Checker berpenalaran tinggi."
        ),
    },
    "Budaya & Fakta Unik": {
        "writer": [
            "gemini/gemini-3.5-flash",
            "groq/openai/gpt-oss-120b",
            "groq/qwen/qwen3.8-27b",
            "cohere/command-a-plus-05-2026",
        ],
        "reviewer": [
            "cohere/command-a-plus-05-2026",
            "groq/openai/gpt-oss-120b",
            "groq/openai/gpt-oss-20b",
            "groq/qwen/qwen3.8-27b",
            "gemini/gemini-3.5-flash",
        ],
        "rationale": (
            "Genre Budaya & Fakta Unik memerlukan sintesis lintas-sumber yang presisi "
            "(Gemini 3.5 Flash sebagai Writer+Grader) dan verifikasi fakta oleh Command A+ (Cohere, 40K TPM) / GPT-OSS 120B (Groq)."
        ),
    },
}

_GEMINI_EXHAUSTED = False
_GEMINI_EXHAUSTED_UNTIL = 0.0
_GEMINI_EXHAUSTED_TTL_SECONDS = 3600.0


def is_gemini_quota_exhausted() -> bool:
    global _GEMINI_EXHAUSTED, _GEMINI_EXHAUSTED_UNTIL
    now = time.time()
    if os.getenv("GEMINI_EXHAUSTED", "false").lower() in ("true", "1", "yes"):
        if _GEMINI_EXHAUSTED_UNTIL and now >= _GEMINI_EXHAUSTED_UNTIL:
            os.environ.pop("GEMINI_EXHAUSTED", None)
        else:
            return True
    if _GEMINI_EXHAUSTED:
        if _GEMINI_EXHAUSTED_UNTIL and now < _GEMINI_EXHAUSTED_UNTIL:
            return True
        _GEMINI_EXHAUSTED = False
        _GEMINI_EXHAUSTED_UNTIL = 0.0
    flag_candidates = [
        os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "gemini_exhausted.flag"),
        "gemini_exhausted.flag",
    ]
    for flag_path in flag_candidates:
        if os.path.exists(flag_path):
            try:
                with open(flag_path, "r") as f:
                    ts = float((f.read() or "0").strip())
                if (now - ts) < _GEMINI_EXHAUSTED_TTL_SECONDS:
                    return True
                os.remove(flag_path)
            except Exception:
                return True
    return False


def mark_gemini_exhausted():
    global _GEMINI_EXHAUSTED, _GEMINI_EXHAUSTED_UNTIL
    now = time.time()
    _GEMINI_EXHAUSTED = True
    _GEMINI_EXHAUSTED_UNTIL = now + _GEMINI_EXHAUSTED_TTL_SECONDS
    os.environ["GEMINI_EXHAUSTED"] = "true"
    try:
        with open("gemini_exhausted.flag", "w") as f:
            f.write(str(now))
    except Exception:
        pass

MIN_SAFE_REMAINING_TOKENS = 15_000


def _is_provider_key_available(model_id: str) -> bool:
    """Memastikan API key untuk provider model tersebut tersedia di environment."""
    provider = model_id.split("/", 1)[0].lower() if "/" in model_id else "gemini"
    if provider == "groq":
        return bool(os.getenv("GROQ_API_KEY"))
    elif provider == "cohere":
        return bool(os.getenv("COHERE_API_KEY"))
    elif provider == "openrouter":
        return bool(os.getenv("OPENROUTER_API_KEY"))
    else:
        return bool(os.getenv("GEMINI_API_KEY"))


def _has_sufficient_quota(model_id: str, stats: Dict[str, Dict[str, Any]]) -> bool:
    """Mengecek apakah sisa kuota token model masih di atas batas aman."""
    if model_id.startswith("gemini/") and is_gemini_quota_exhausted():
        return False
    info = stats.get(model_id)
    if not info:
        return True
    return info.get("remaining_tokens", 100_000) >= MIN_SAFE_REMAINING_TOKENS


def select_optimal_models(
    genre: str,
    topic: str = "",
    stats: Optional[Dict[str, Dict[str, Any]]] = None
) -> Dict[str, Any]:
    """
    Memilih pasangan Model Writer & Model Reviewer terbaik secara otomatis
    berdasarkan Genre, Kompleksitas Topik, Ketersediaan API Key, dan Sisa Kuota Token.
    Juga mengutamakan Cross-Model Pairing (Writer != Reviewer) untuk mencegah bias evaluasi.
    """
    if stats is None:
        stats = get_model_usage_stats("experiment_metrics.csv", filter_today=False)

    prefs = GENRE_MODEL_PREFERENCES.get(
        genre,
        GENRE_MODEL_PREFERENCES["Wisata & Destinasi (Travel)"]
    )

    # 1. Pilih Writer Model terbaik yang API Key-nya aktif & kuotanya aman
    chosen_writer = None
    for candidate in prefs["writer"]:
        if _is_provider_key_available(candidate) and _has_sufficient_quota(candidate, stats):
            chosen_writer = candidate
            break
    if not chosen_writer:
        # Fallback jika kuota menipis
        for candidate in prefs["writer"]:
            if _is_provider_key_available(candidate):
                chosen_writer = candidate
                break
    if not chosen_writer:
        chosen_writer = "gemini/gemini-3.5-flash"

    # 2. Pilih Reviewer Model terbaik (diutamakan berbeda model dari Writer agar objektif)
    chosen_reviewer = None
    for candidate in prefs["reviewer"]:
        if (
            candidate != chosen_writer
            and _is_provider_key_available(candidate)
            and _has_sufficient_quota(candidate, stats)
        ):
            chosen_reviewer = candidate
            break

    # Jika tidak ada yang berbeda, izinkan model yang tersedia dan kuotanya aman
    if not chosen_reviewer:
        for candidate in prefs["reviewer"]:
            if _is_provider_key_available(candidate) and _has_sufficient_quota(candidate, stats):
                chosen_reviewer = candidate
                break
    if not chosen_reviewer:
        chosen_reviewer = "gemini/gemini-3.5-flash"

    writer_meta = MODEL_QUOTAS.get(chosen_writer, {"label": chosen_writer})
    reviewer_meta = MODEL_QUOTAS.get(chosen_reviewer, {"label": chosen_reviewer})
    writer_rem = stats.get(chosen_writer, {}).get("remaining_tokens", 0)
    reviewer_rem = stats.get(chosen_reviewer, {}).get("remaining_tokens", 0)

    routing_reason = (
        f"{prefs['rationale']} "
        f"Writer dipilih **{writer_meta['label']}** (sisa kuota: {writer_rem:,} token) "
        f"dan Reviewer dipilih **{reviewer_meta['label']}** (sisa kuota: {reviewer_rem:,} token) "
        f"untuk menjaga objektivitas *cross-model evaluation*."
    )

    return {
        "writer_model": chosen_writer,
        "writer_label": writer_meta["label"],
        "reviewer_model": chosen_reviewer,
        "reviewer_label": reviewer_meta["label"],
        "planner_model": chosen_reviewer,
        "routing_reason": routing_reason,
    }
