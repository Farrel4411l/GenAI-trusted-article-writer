import os
from typing import TypedDict, List
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_google_genai import ChatGoogleGenerativeAI
from src.agents.prompts import WRITER_SYSTEM_PROMPT

# Definisi State/Memory yang dibawa-bawa dalam Graph (Siklus)
class AgentState(TypedDict):
    topic: str
    context: str
    draft: str
    revision_notes: str
    revision_count: int
    is_passed: bool

def writer_node(state: AgentState):
    """
    Node untuk Agent Writer. Bertugas membuat draf atau merevisi draf.
    """
    print(f"\n[Agent Writer] Mulai menulis... (Iterasi ke-{state['revision_count']})")
    
    # Inisialisasi LLM Writer (Sesuai paper: menggunakan Gemini-1.5-Pro)
    model = ChatGoogleGenerativeAI(
        model=os.getenv("MODEL_WRITER", "gemini-3.5-flash"),
        google_api_key=os.getenv("GEMINI_API_KEY"),
        temperature=0.7 # Sedikit kreativitas untuk penulisan
    )
    
    # Merakit Prompt
    user_content = f"TOPIK:\n{state['topic']}\n\nKONTEKS ASLI:\n{state['context']}"
    
    if state.get("revision_notes"):
        user_content += f"\n\nCATATAN REVISI SEBELUMNYA:\n{state['revision_notes']}\n\nTolong perbaiki draf agar mematuhi catatan revisi di atas!"
        
    messages = [
        SystemMessage(content=WRITER_SYSTEM_PROMPT),
        HumanMessage(content=user_content)
    ]
    
    response = model.invoke(messages)
    content = response.content
    if isinstance(content, list):
        content = content[0].get("text", str(content)) if isinstance(content[0], dict) else str(content[0])
        
    # Update State dengan draft terbaru
    return {"draft": content}
