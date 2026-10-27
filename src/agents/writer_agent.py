import os
import re
import time
from typing import TypedDict, List
from langchain_core.messages import HumanMessage, SystemMessage
from src.agents.prompts import WRITER_SYSTEM_PROMPT
from src.agents.llm_factory import get_llm

def deduplicate_references(draft_text: str) -> str:
    """
    Membersihkan dan mendeduplikasi daftar 'Sumber Referensi' di bagian akhir artikel
    agar URL yang sama tidak diulang berkali-kali.
    """
    pattern = re.compile(r'(?i)(\*{0,2}sumber referensi:?\*{0,2})')
    match = pattern.search(draft_text)
    if not match:
        return draft_text

    split_idx = match.start()
    body = draft_text[:split_idx].rstrip()
    header = match.group(1)
    ref_block = draft_text[match.end():].strip()

    seen_urls = set()
    unique_lines = []

    for line in ref_block.splitlines():
        line_clean = line.strip()
        if not line_clean:
            continue
        # Hapus nomor urut atau bullet di awal baris
        item_text = re.sub(r'^(?:\d+[\.\)]\s*|[-*•]\s*)', '', line_clean).strip()
        if not item_text:
            continue

        # Cari URL di dalam format markdown [Judul](URL) atau URL langsung
        url_match = re.search(r'\((https?://[^\s\)]+)\)|https?://[^\s\)]+', item_text)
        key = url_match.group(1) if (url_match and url_match.group(1)) else (url_match.group(0) if url_match else item_text.lower())

        if key not in seen_urls:
            seen_urls.add(key)
            unique_lines.append(item_text)

    if not unique_lines:
        return draft_text

    formatted_refs = "\n".join(f"{i}. {item}" for i, item in enumerate(unique_lines, start=1))
    return f"{body}\n\n{header}\n{formatted_refs}"

# Definisi State/Memory yang dibawa-bawa dalam Graph (Siklus)
class AgentState(TypedDict):
    topic: str
    context: str
    draft: str
    revision_notes: str
    revision_count: int
    is_passed: bool
    writer_model: str
    reviewer_model: str
    # --- PHASE 3 METRICS ---
    writer_tokens: int
    reviewer_tokens: int
    grader_tokens: int
    start_time: float

def writer_node(state: AgentState):
    """
    Node untuk Agent Writer. Bertugas membuat draf atau merevisi draf.
    """
    writer_model_name = state.get("writer_model", "gemini/gemini-3.5-flash")
    print(f"\n[Agent Writer] Mulai menulis dengan model {writer_model_name}... (Iterasi ke-{state.get('revision_count', 1)})")
    
    # Inisialisasi LLM Writer dari Factory
    model = get_llm(writer_model_name)
    
    # Merakit Prompt
    user_content = f"TOPIK:\n{state['topic']}\n\nKONTEKS ASLI:\n{state['context']}"
    
    if state.get("revision_notes"):
        user_content += f"\n\nCATATAN REVISI SEBELUMNYA:\n{state['revision_notes']}\n\nTolong perbaiki draf agar mematuhi catatan revisi di atas!"
        
    messages = [
        SystemMessage(content=WRITER_SYSTEM_PROMPT),
        HumanMessage(content=user_content)
    ]
    
    max_attempts = 3
    for attempt in range(max_attempts):
        try:
            response = model.invoke(messages)
            break
        except Exception as e:
            err_str = str(e).lower()
            if "429" in str(e) or "resource_exhausted" in err_str or "rate limit" in err_str or "otpm" in err_str:
                if attempt < max_attempts - 1:
                    # Turunkan max_tokens jika model mendukung untuk meringankan beban OTPM
                    if hasattr(model, "max_tokens") and model.max_tokens:
                        model.max_tokens = max(600, model.max_tokens - 100)
                    print(f"Batas kecepatan API (429/OTPM) tercapai. Menunggu 60 detik agar sliding window 1 menit pulih... (Percobaan {attempt+1}/{max_attempts})")
                    time.sleep(60)
                else:
                    raise e
            else:
                raise e
                
    # Ekstraksi Token Usage
    tokens = 0
    if hasattr(response, "usage_metadata") and response.usage_metadata:
        tokens = response.usage_metadata.get("total_tokens", 0)
    elif hasattr(response, "response_metadata") and "token_usage" in response.response_metadata:
        tokens = response.response_metadata["token_usage"].get("total_tokens", 0)
        
    current_tokens = state.get("writer_tokens", 0) + tokens
                
    content = response.content
    if isinstance(content, list):
        draft_text = ""
        for item in content:
            if isinstance(item, dict) and "text" in item:
                draft_text += item["text"]
            elif isinstance(item, str):
                draft_text += item
        content = draft_text

    content = deduplicate_references(content)

    # Update State dengan draft terbaru dan metrik
    return {
        "draft": content,
        "writer_tokens": current_tokens
    }
