import os
import json
import pandas as pd
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from dotenv import load_dotenv
from typing import List, Dict
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_google_genai import ChatGoogleGenerativeAI
from src.retriever.search import search_context
from src.agents.orchestrator import build_graph

load_dotenv()

# --- 1. SETUP MODEL EVALUATOR (JUDGE) ---
# Menggunakan Gemini-3.5-Flash sebagai Judge untuk menilai Faithfulness (Halusinasi)
judge_model = ChatGoogleGenerativeAI(
    model=os.getenv("MODEL_JUDGE", "gemini-3.5-flash"),
    temperature=0.0
)

def evaluate_faithfulness(question: str, context: str, answer: str) -> float:
    """
    Simulasi metrik 'Faithfulness' dari RAGAS.
    Menggunakan LLM Judge untuk mengekstrak klaim dan memverifikasi apakah klaim
    tersebut didukung oleh konteks. Menghasilkan skor 0.0 - 1.0.
    """
    if not answer.strip() or "tidak terdapat informasi" in answer.lower():
        # Jika model jujur mengatakan tidak ada info, itu berarti sangat setia pada konteks (Faithful = 1.0)
        return 1.0
        
    prompt = f"""
Anda adalah penilai objektivitas (Judge).
Tugas Anda adalah menilai 'Faithfulness' (Kesetiaan pada konteks) dari sebuah jawaban.

KONTEKS:
{context}

PERTANYAAN:
{question}

JAWABAN:
{answer}

Langkah-langkah:
1. Ekstrak semua klaim spesifik dari JAWABAN.
2. Untuk setiap klaim, periksa apakah klaim tersebut BISA DIBUKTIKAN oleh KONTEKS.
3. Hitung skor: (Jumlah klaim yang didukung konteks) / (Total klaim).

Keluarkan HANYA skor akhir dalam bentuk angka desimal antara 0.0 hingga 1.0.
Contoh keluaran: 0.8
"""
    try:
        response = judge_model.invoke([HumanMessage(content=prompt)])
        score_content = response.content
        if isinstance(score_content, list):
            score_str = score_content[0].get("text", str(score_content)) if isinstance(score_content[0], dict) else str(score_content[0])
        else:
            score_str = score_content
        score_str = score_str.strip()
        
        # Ekstrak angka saja jika ada teks tambahan
        import re
        match = re.search(r"0\.\d+|1\.0|0|1", score_str)
        return float(match.group()) if match else 0.0
    except Exception as e:
        print(f"Error evaluasi: {e}")
        return 0.0

# --- 2. PIPELINE BASELINE (RAG STANDAR TANPA AGEN) ---
def run_baseline_rag(topic: str) -> Dict:
    """Menjalankan sistem RAG standar (Sekali jalan tanpa Reviewer)"""
    contexts = search_context(topic, k=3)
    context_text = "\n\n".join(contexts) if contexts else "Tidak ada konteks."
    
    writer = ChatGoogleGenerativeAI(
        model=os.getenv("MODEL_WRITER", "gemini-3.5-flash"),
        temperature=0.7
    )
    
    prompt = f"""Tulis artikel tentang TOPIK berikut berdasarkan KONTEKS saja.
TOPIK: {topic}
KONTEKS: {context_text}
"""
    response = writer.invoke([HumanMessage(content=prompt)])
    answer = response.content
    if isinstance(answer, list):
        answer = answer[0].get("text", str(answer)) if isinstance(answer[0], dict) else str(answer[0])
        
    return {"context": context_text, "answer": answer}

# --- 3. PIPELINE MULTI-AGENT (YANG KITA BUAT) ---
def run_multi_agent_rag(topic: str) -> Dict:
    """Menjalankan LangGraph Multi-Agent RAG"""
    app = build_graph()
    initial_state = {
        "topic": topic, "context": "", "draft": "",
        "revision_notes": "", "revision_count": 1, "is_passed": False
    }
    result = app.invoke(initial_state)
    return {"context": result["context"], "answer": result["draft"], "revisions": result["revision_count"] - 1}

# --- 4. EKSEKUSI ABLATION STUDY ---
if __name__ == "__main__":
    print("=== MEMULAI ABLATION STUDY (Baseline vs Multi-Agent) ===")
    
    # 3 Pertanyaan Uji Coba
    test_queries = [
        "Siapa nama presiden Mesir yang dibunuh pada 6 Oktober 1981?",
        "Siapa saja tokoh Ikatan Ahli Arkeologi Indonesia?",
        "Apa ibu kota dari negara Australia?" # Pertanyaan jebakan (Out of Context)
    ]
    
    results = []
    
    for i, query in enumerate(test_queries, 1):
        print(f"\n--- Menguji Pertanyaan {i}/3: '{query}' ---")
        
        # 1. Uji Baseline
        print("[1] Menjalankan Baseline RAG...")
        base_res = run_baseline_rag(query)
        base_score = evaluate_faithfulness(query, base_res["context"], base_res["answer"])
        
        # 2. Uji Multi-Agent
        print("[2] Menjalankan Multi-Agent RAG...")
        agent_res = run_multi_agent_rag(query)
        agent_score = evaluate_faithfulness(query, agent_res["context"], agent_res["answer"])
        
        results.append({
            "Pertanyaan": query,
            "Baseline_Answer": base_res["answer"][:100] + "...",
            "Baseline_Faithfulness": base_score,
            "MultiAgent_Answer": agent_res["answer"][:100] + "...",
            "MultiAgent_Revisions": agent_res["revisions"],
            "MultiAgent_Faithfulness": agent_score
        })
        print(f"Skor Faithfulness -> Baseline: {base_score} | Multi-Agent: {agent_score}")
        
    # --- 5. EKSPOR KE CSV ---
    df = pd.DataFrame(results)
    df.to_csv("ablation_study_results.csv", index=False)
    print("\n=== EVALUASI SELESAI ===")
    print("Hasil telah diekspor ke 'ablation_study_results.csv'.")
    print("\nRingkasan Hasil:")
    print(df[["Pertanyaan", "Baseline_Faithfulness", "MultiAgent_Faithfulness"]])
