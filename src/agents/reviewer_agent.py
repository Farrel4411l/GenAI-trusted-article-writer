import os
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_google_genai import ChatGoogleGenerativeAI
from src.agents.prompts import REVIEWER_SYSTEM_PROMPT
from src.agents.writer_agent import AgentState

def reviewer_node(state: AgentState):
    """
    Node untuk Agent Reviewer. Bertugas mengecek halusinasi pada draf Writer.
    """
    print(f"\n[Agent Reviewer] Sedang memverifikasi draf...")
    
    # Inisialisasi LLM Reviewer (Sesuai paper: menggunakan Gemini-1.5-Pro)
    # Suhu = 0.0 agar objektif dan deterministik (sesuai standar Scopus)
    model = ChatGoogleGenerativeAI(
        model=os.getenv("MODEL_WRITER", "gemini-3.5-flash"),
        google_api_key=os.getenv("GEMINI_API_KEY"),
        temperature=0.0 
    )
    
    user_content = f"TOPIK:\n{state['topic']}\n\nKONTEKS ASLI (Kebenaran):\n{state['context']}\n\nDRAF ARTIKEL:\n{state['draft']}"
    
    messages = [
        SystemMessage(content=REVIEWER_SYSTEM_PROMPT),
        HumanMessage(content=user_content)
    ]
    
    import time
    max_attempts = 3
    for attempt in range(max_attempts):
        try:
            response = model.invoke(messages)
            break
        except Exception as e:
            if "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e):
                if attempt < max_attempts - 1:
                    print(f"Limit API tercapai. Menunggu 30 detik sebelum mencoba lagi... (Percobaan {attempt+1}/{max_attempts})")
                    time.sleep(30)
                else:
                    raise e
            else:
                raise e
                
    content = response.content
    if isinstance(content, list):
        content = content[0].get("text", str(content)) if isinstance(content[0], dict) else str(content[0])
    
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
        
    return {
        "is_passed": is_passed,
        "revision_notes": revision_notes,
        "revision_count": state["revision_count"] + 1
    }
