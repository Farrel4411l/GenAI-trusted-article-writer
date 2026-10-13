import os
import sys

if sys.stdout.encoding.lower() != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')

sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from dotenv import load_dotenv
from langgraph.graph import StateGraph, END
from src.agents.writer_agent import AgentState, writer_node
from src.agents.reviewer_agent import reviewer_node
from src.retriever.search import search_context

load_dotenv()

def retrieve_node(state: AgentState):
    """
    Node pertama: Mengambil konteks dari database pgvector berdasarkan topik.
    """
    print(f"\n[Retriever] Mencari konteks untuk topik: '{state['topic']}'")
    
    # Ambil konteks berformat metadata dari 15 dokumen terbaik
    model_id = state.get("writer_model", "groq/qwen/qwen3.8-27b")
    context_text, grader_tokens = search_context(state['topic'], model_id, k=15)
    
    if not context_text.strip():
        print("[Retriever] PERINGATAN: Konteks tidak ditemukan di database!")
        context_text = "Tidak ada informasi terkait di database."
        
    return {
        "context": context_text,
        "grader_tokens": state.get("grader_tokens", 0) + grader_tokens
    }

def should_continue(state: AgentState):
    """
    Fungsi logika percabangan (Conditional Edge).
    Menentukan apakah draf disetujui, direvisi, atau dibatalkan karena batas iterasi.
    """
    max_retries = int(os.getenv("MAX_RETRIES", "3"))
    
    if state["is_passed"]:
        return "end"
    elif state["revision_count"] > max_retries:
        print(f"\n[Orchestrator] Batas revisi maksimum ({max_retries}) tercapai. Draf mungkin masih mengandung halusinasi.")
        return "end"
    else:
        return "revise"

def build_graph():
    """
    Membangun arsitektur LangGraph (Multi-Agent Flow).
    """
    # Inisialisasi State Graph
    workflow = StateGraph(AgentState)
    
    # Daftarkan Nodes
    workflow.add_node("retriever", retrieve_node)
    workflow.add_node("writer", writer_node)
    workflow.add_node("reviewer", reviewer_node)
    
    # Daftarkan Edges (Alur)
    workflow.set_entry_point("retriever")
    workflow.add_edge("retriever", "writer")
    workflow.add_edge("writer", "reviewer")
    
    # Conditional Edge dari Reviewer
    workflow.add_conditional_edges(
        "reviewer",
        should_continue,
        {
            "end": END,
            "revise": "writer"
        }
    )
    
    # Compile Graph
    app = workflow.compile()
    return app

if __name__ == "__main__":
    # Script untuk Uji Coba (Bisa dijalankan di terminal)
    print("=== PENGUJIAN MULTI-AGENT RAG ===")
    app = build_graph()
    
    # Topik uji coba (Gunakan sesuatu yang kira-kira ada di Wikipedia yang diunduh)
    # Anda dapat menggantinya sesuai keinginan
    topik = "Siapa saja presiden Indonesia dan kapan masa jabatannya?"
    
    initial_state = {
        "topic": topik,
        "context": "",
        "draft": "",
        "revision_notes": "",
        "revision_count": 1,
        "is_passed": False
    }
    
    print("Memulai alur eksekusi...")
    # Menjalankan graph
    result = app.invoke(initial_state)
    
    print("\n\n" + "="*50)
    print("HASIL AKHIR ARTIKEL:")
    print("="*50)
    print(result["draft"])
