import os
import time
from langchain_core.messages import HumanMessage, SystemMessage
from src.agents.prompts import REVIEWER_SYSTEM_PROMPT
from src.agents.writer_agent import AgentState
from src.agents.llm_factory import get_llm

def reviewer_node(state: AgentState):
    """
    Node untuk Agent Reviewer. Bertugas mengecek halusinasi pada draf Writer.
    """
    reviewer_model_name = state.get("reviewer_model", "gemini/gemini-3.5-flash")
    print(f"\n[Agent Reviewer] Sedang memverifikasi draf menggunakan {reviewer_model_name}...")
    
    # Inisialisasi LLM Reviewer (Suhu di-override ke 0.0 di factory atau di sini,
    # tapi kita gunakan factory default 0.7 untuk saat ini, idealnya 0.0)
    # Untuk simplifikasi, llm_factory sudah kita buat, kita gunakan langsung.
    model = get_llm(reviewer_model_name)
    
    # Memaksa temperature ke 0.0 jika didukung model object
    if hasattr(model, "temperature"):
        model.temperature = 0.0
    
    user_content = f"TOPIK:\n{state['topic']}\n\nKONTEKS ASLI (Kebenaran):\n{state['context']}\n\nDRAF ARTIKEL:\n{state['draft']}"
    
    messages = [
        SystemMessage(content=REVIEWER_SYSTEM_PROMPT),
        HumanMessage(content=user_content)
    ]
    
    max_attempts = 3
    for attempt in range(max_attempts):
        try:
            response = model.invoke(messages)
            break
        except Exception as e:
            if "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e) or "rate limit" in str(e).lower():
                if attempt < max_attempts - 1:
                    print(f"Limit API tercapai. Menunggu 30 detik sebelum mencoba lagi... (Percobaan {attempt+1}/{max_attempts})")
                    time.sleep(30)
                else:
                    raise e
            else:
                raise e
                
    content = response.content
    if isinstance(content, list):
        draft_text = ""
        for item in content:
            if isinstance(item, dict) and "text" in item:
                draft_text += item["text"] + "\n"
            elif isinstance(item, str):
                draft_text += item + "\n"
        content = draft_text
    
    feedback = content.strip()
    
    is_passed = False
    revision_notes = ""
    
    # Mengecek keputusan Reviewer
    if feedback.upper().startswith("LULUS") or "LULUS" in feedback[:15].upper():
        is_passed = True
        print("[Agent Reviewer] KEPUTUSAN: LULUS (Tidak terdeteksi halusinasi)")
    else:
        is_passed = False
        revision_notes = feedback
        print(f"[Agent Reviewer] KEPUTUSAN: REVISI DIBUTUHKAN\nCatatan: {revision_notes}")
        
    # Ekstraksi Token Usage
    tokens = 0
    if hasattr(response, "usage_metadata") and response.usage_metadata:
        tokens = response.usage_metadata.get("total_tokens", 0)
    elif hasattr(response, "response_metadata") and "token_usage" in response.response_metadata:
        tokens = response.response_metadata["token_usage"].get("total_tokens", 0)
        
    current_tokens = state.get("reviewer_tokens", 0) + tokens
    
    return {
        "is_passed": is_passed,
        "revision_notes": revision_notes,
        "revision_count": state.get("revision_count", 0) + 1,
        "reviewer_tokens": current_tokens
    }
