import os
import time
from typing import TypedDict, List
from langchain_core.messages import HumanMessage, SystemMessage
from src.agents.prompts import WRITER_SYSTEM_PROMPT
from src.agents.llm_factory import get_llm

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
            if "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e) or "rate limit" in str(e).lower():
                if attempt < max_attempts - 1:
                    print(f"Limit API (429/OTPM) tercapai. Menunggu 45 detik agar kuota token pulih... (Percobaan {attempt+1}/{max_attempts})")
                    time.sleep(45)
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
        content = content[0].get("text", str(content)) if isinstance(content[0], dict) else str(content[0])
        
    # Update State dengan draft terbaru dan metrik
    return {
        "draft": content,
        "writer_tokens": current_tokens
    }
