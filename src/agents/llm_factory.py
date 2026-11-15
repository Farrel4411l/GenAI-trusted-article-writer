import os
import time
from typing import Any, Dict, List, Optional
from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_groq import ChatGroq
from langchain_cohere import ChatCohere
from langchain_openai import ChatOpenAI

load_dotenv()

# Circuit breaker memori sementara (detik timestamp) saat model terkena 429/413
_MODEL_COOLDOWN_UNTIL: Dict[str, float] = {}

_HIGH_TPM_CANDIDATES: List[str] = [
    "cohere/command-a-plus-05-2026",
    "gemini/gemini-3.5-flash",
]

_ALL_FAILOVER_CANDIDATES: List[str] = [
    "cohere/command-a-plus-05-2026",
    "gemini/gemini-3.5-flash",
    "groq/openai/gpt-oss-120b",
    "groq/openai/gpt-oss-20b",
    "groq/qwen/qwen3.8-27b",
]


def _has_api_key(model_identifier: str) -> bool:
    """Memastikan API key untuk provider kandidat tersedia."""
    provider = model_identifier.split("/", 1)[0].lower() if "/" in model_identifier else "gemini"
    if provider == "groq":
        return bool(os.getenv("GROQ_API_KEY"))
    if provider == "cohere":
        return bool(os.getenv("COHERE_API_KEY"))
    if provider == "openrouter":
        return bool(os.getenv("OPENROUTER_API_KEY"))
    return bool(os.getenv("GEMINI_API_KEY"))


def _is_gemini_exhausted_safe() -> bool:
    try:
        from src.automation.model_router import is_gemini_quota_exhausted
        return is_gemini_quota_exhausted()
    except Exception:
        return False


def _mark_gemini_exhausted_safe() -> None:
    try:
        from src.automation.model_router import mark_gemini_exhausted
        mark_gemini_exhausted()
    except Exception:
        pass


def _build_raw_llm(
    model_identifier: str,
    temperature: Optional[float] = None,
    max_tokens: Optional[int] = None,
):
    """Membangun instance LangChain ChatModel mentah untuk provider tertentu."""
    if "/" not in model_identifier:
        provider = "gemini"
        model_name = "gemini-3.5-flash"
    else:
        provider, model_name = model_identifier.split("/", 1)

    provider = provider.lower()
    temp = 0.7 if temperature is None else temperature

    if provider == "groq":
        default_groq_max = 800 if "qwen" in model_name.lower() else 1000
        effective_max = max_tokens if max_tokens is not None else default_groq_max
        return ChatGroq(
            temperature=temp,
            model_name=model_name,
            max_tokens=effective_max,
            api_key=os.getenv("GROQ_API_KEY"),
        )
    elif provider == "cohere":
        kwargs: Dict[str, Any] = {
            "temperature": temp,
            "model": model_name,
            "cohere_api_key": os.getenv("COHERE_API_KEY"),
        }
        if max_tokens is not None:
            kwargs["max_tokens"] = max_tokens
        return ChatCohere(**kwargs)
    elif provider == "openrouter":
        kwargs_or: Dict[str, Any] = {
            "temperature": temp,
            "model": model_name,
            "api_key": os.getenv("OPENROUTER_API_KEY"),
            "base_url": "https://openrouter.ai/api/v1",
        }
        if max_tokens is not None:
            kwargs_or["max_tokens"] = max_tokens
        return ChatOpenAI(**kwargs_or)
    else:
        kwargs_gm: Dict[str, Any] = {
            "model": model_name,
            "temperature": temp,
            "api_key": os.getenv("GEMINI_API_KEY"),
        }
        if max_tokens is not None:
            kwargs_gm["max_output_tokens"] = max_tokens
        return ChatGoogleGenerativeAI(**kwargs_gm)


def _classify_api_error(err_str: str) -> Dict[str, bool]:
    low = err_str.lower()
    is_payload_tpm = any(
        k in low for k in ("413", "too large", "request too large", "tokens per minute", "tpm", "request size", "context length")
    )
    is_daily = any(
        k in low for k in ("per day", "tpd", "rpd", "free_tier_requests", "daily limit")
    )
    is_retryable = is_payload_tpm or is_daily or any(
        k in low for k in ("429", "502", "503", "504", "rate limit", "rate_limit", "otpm", "resource_exhausted", "quota", "overloaded", "temporarily unavailable", "timeout", "timed out")
    )
    return {
        "is_retryable": is_retryable,
        "is_payload_tpm": is_payload_tpm,
        "is_daily": is_daily,
    }


def _get_failover_chain(primary_id: str, prefer_high_tpm: bool = False) -> List[str]:
    now = time.time()
    pool = list(_HIGH_TPM_CANDIDATES if prefer_high_tpm else _ALL_FAILOVER_CANDIDATES)
    if prefer_high_tpm:
        for c in _ALL_FAILOVER_CANDIDATES:
            if c not in pool:
                pool.append(c)

    chain: List[str] = []
    for cand in pool:
        if cand == primary_id:
            continue
        if not _has_api_key(cand):
            continue
        if cand.startswith("gemini/") and _is_gemini_exhausted_safe():
            continue
        if _MODEL_COOLDOWN_UNTIL.get(cand, 0) > now:
            continue
        chain.append(cand)
    return chain


class ResilientChatModel:
    """
    Wrapper adaptif untuk ChatModel LangChain agar kebal terhadap:
    - Error 413 (Request Too Large / Groq 8.000 TPM ceiling)
    - Error 429 (Rate Limit RPM/TPM/OTPM) & 503 API Timeout
    dengan mekanisme Circuit-Breaker + Failover Lintas-Provider otomatis.
    """

    def __init__(self, model_identifier: str):
        self.model_identifier = model_identifier
        self._temperature_override: Optional[float] = None
        self._max_tokens_override: Optional[int] = None
        self._inner = _build_raw_llm(model_identifier)

    @property
    def temperature(self) -> Optional[float]:
        if self._temperature_override is not None:
            return self._temperature_override
        return getattr(self._inner, "temperature", None)

    @temperature.setter
    def temperature(self, value: float) -> None:
        self._temperature_override = value
        if hasattr(self._inner, "temperature"):
            try:
                self._inner.temperature = value
            except Exception:
                pass

    @property
    def max_tokens(self) -> Optional[int]:
        if self._max_tokens_override is not None:
            return self._max_tokens_override
        return getattr(self._inner, "max_tokens", None)

    @max_tokens.setter
    def max_tokens(self, value: int) -> None:
        self._max_tokens_override = value
        if hasattr(self._inner, "max_tokens"):
            try:
                self._inner.max_tokens = value
            except Exception:
                pass

    def _effective_fallback_max_tokens(self, cand_id: str) -> Optional[int]:
        if self._max_tokens_override is None:
            return None
        # Model reasoning (GPT-OSS / Command A+ / Qwen) membutuhkan token penalaran sebelum teks akhir
        is_reasoning = any(k in cand_id.lower() for k in ("gpt-oss", "command-a", "qwen"))
        if is_reasoning and self._max_tokens_override < 300:
            return 350
        return self._max_tokens_override

    def invoke(self, *args, **kwargs):
        now = time.time()
        in_cooldown = _MODEL_COOLDOWN_UNTIL.get(self.model_identifier, 0) > now
        gemini_dead = self.model_identifier.startswith("gemini/") and _is_gemini_exhausted_safe()

        candidates: List[str] = []
        if not in_cooldown and not gemini_dead:
            candidates.append(self.model_identifier)
        else:
            print(f"[LLM Router Guard] '{self.model_identifier}' sedang cooldown/limit, langsung memakai failover aktif...")

        candidates.extend(_get_failover_chain(self.model_identifier, prefer_high_tpm=False))
        if self.model_identifier not in candidates:
            candidates.append(self.model_identifier)

        last_err: Optional[Exception] = None
        tried = set()

        idx = 0
        while idx < len(candidates):
            cand = candidates[idx]
            idx += 1
            if cand in tried:
                continue
            tried.add(cand)

            try:
                if cand == self.model_identifier:
                    return self._inner.invoke(*args, **kwargs)
                fb_llm = _build_raw_llm(
                    cand,
                    temperature=self._temperature_override,
                    max_tokens=self._effective_fallback_max_tokens(cand),
                )
                resp = fb_llm.invoke(*args, **kwargs)
                print(f"[LLM Failover OK] Berhasil dialihkan dari '{self.model_identifier}' -> '{cand}'.")
                return resp
            except Exception as e:
                last_err = e
                cls = _classify_api_error(str(e))
                if not cls["is_retryable"]:
                    raise

                cooldown_sec = 3600 if cls["is_daily"] else 75
                _MODEL_COOLDOWN_UNTIL[cand] = time.time() + cooldown_sec
                if cand.startswith("gemini/") and cls["is_daily"]:
                    _mark_gemini_exhausted_safe()

                print(f"[LLM Limit/Error] '{cand}' terkendala ({type(e).__name__}: {str(e)[:120]}). Mencari jalur failover...")

                if cls["is_payload_tpm"]:
                    # Untuk error 413/TPM 8k Groq, sisipkan kandidat High-TPM di antrean depan
                    for hi in _get_failover_chain(cand, prefer_high_tpm=True):
                        if hi not in tried and hi not in candidates[idx:]:
                            candidates.insert(idx, hi)

        # Upaya pemulihan terakhir setelah jeda singkat 18 detik untuk reset window RPM
        recovery_pool = [
            c for c in ("gemini/gemini-3.5-flash", "cohere/command-a-plus-05-2026", "groq/openai/gpt-oss-120b")
            if _has_api_key(c) and not (c.startswith("gemini/") and _is_gemini_exhausted_safe())
        ]
        if recovery_pool:
            print("[LLM Recovery] Semua kandidat sempat terkena burst limit. Menunggu 18 detik lalu mencoba ulang...")
            time.sleep(18)
            for rec in recovery_pool:
                try:
                    rec_llm = _build_raw_llm(
                        rec,
                        temperature=self._temperature_override,
                        max_tokens=self._effective_fallback_max_tokens(rec),
                    )
                    return rec_llm.invoke(*args, **kwargs)
                except Exception as e_rec:
                    last_err = e_rec

        if last_err:
            raise last_err
        raise RuntimeError(f"Tidak ada model LLM yang tersedia untuk '{self.model_identifier}'.")

    def __getattr__(self, name: str) -> Any:
        return getattr(self._inner, name)


def get_llm(model_identifier: str):
    """
    Factory function untuk menginisiasi LLM sesuai nama/provider.
    Format model_identifier: "provider/model_name"
    Contoh: "groq/llama3-8b-8192", "cohere/command-r", "gemini/gemini-3.5-flash", "openrouter/meta-llama/llama-3-8b-instruct:free"
    Dilengkapi ResilientChatModel untuk auto-failover 429/413 lintas-provider.
    """
    return ResilientChatModel(model_identifier)
