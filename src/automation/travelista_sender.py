import os
import requests
from typing import Dict, Any, Tuple
from dotenv import load_dotenv

load_dotenv()

DEFAULT_CMS_URL = "http://localhost:3001"
DEFAULT_API_KEY = "travelista-ai-secret-2026"


def send_article_to_travelista_cms(
    payload: Dict[str, Any],
    cms_url: str = "",
    api_key: str = ""
) -> Tuple[bool, str, Dict[str, Any]]:
    """
    Mengirim payload artikel hasil generate AI ke API endpoint CMS Travelista:
    POST /api/articles/receive
    
    Returns:
        (is_success, message, response_data)
    """
    target_url = (cms_url or os.getenv("TRAVELISTA_CMS_URL") or DEFAULT_CMS_URL).rstrip("/")
    endpoint = f"{target_url}/api/articles/receive"
    
    secret_key = api_key or os.getenv("TRAVELISTA_CMS_API_KEY") or os.getenv("AUTO_ARTICLE_SECRET_KEY") or DEFAULT_API_KEY

    headers = {
        "Content-Type": "application/json",
        "x-api-key": secret_key,
        "User-Agent": "Travelista-AI-Sender/2.0",
    }

    try:
        response = requests.post(endpoint, json=payload, headers=headers, timeout=20)
        
        try:
            res_data = response.json()
        except Exception:
            res_data = {"raw_text": response.text[:300]}

        if response.status_code == 200 and res_data.get("success"):
            art_info = res_data.get("data", {})
            msg = (
                f"Berhasil terkirim ke CMS Travelista! "
                f"Artikel ID: {art_info.get('article_id')}, Status: '{art_info.get('status')}'."
            )
            return True, msg, res_data
        elif response.status_code == 401:
            return False, "Gagal terkirim: API Key tidak cocok (Unauthorized 401).", res_data
        else:
            err_msg = res_data.get("error") or f"HTTP {response.status_code}"
            return False, f"CMS mengembalikan kesalahan: {err_msg}", res_data

    except requests.exceptions.ConnectionError:
        return False, (
            f"Tidak dapat terhubung ke server CMS di '{target_url}'. "
            "Pastikan aplikasi CMS Travelista sedang berjalan (misal: pnpm dev:cms di port 3001)."
        ), {}
    except requests.exceptions.Timeout:
        return False, "Koneksi ke CMS Travelista mengalami timeout (lebih dari 20 detik).", {}
    except Exception as e:
        return False, f"Terjadi kesalahan tak terduga saat pengiriman: {e}", {}
