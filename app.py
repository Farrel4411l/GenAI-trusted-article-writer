import streamlit as st
import os
import sys
import time

# Memaksa stdout ke UTF-8 (Fix untuk Windows Charmap Error)
if sys.stdout.encoding.lower() != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')

from dotenv import load_dotenv

# Memastikan direktori root masuk ke path agar bisa import src
sys.path.append(os.path.abspath(os.path.dirname(__file__)))
from src.agents.orchestrator import build_graph
from src.utils.metrics_logger import log_metrics

# Load environment variables
load_dotenv()

# Setup Halaman
st.set_page_config(page_title="Travelista AI Editorial", page_icon="✍️", layout="centered")

st.title("✍️ Travelista AI Editorial (Multi-Agent RAG)")
st.markdown("""
Aplikasi cerdas ini ditenagai oleh **Multi-Agent RAG (LangGraph)** khusus dirancang untuk dapur redaksi **Travelista.id**.
*   **🧑‍💻 Agent Writer**: Bertugas sebagai Jurnalis Senior yang merangkai artikel Travel/Kuliner/Misteri panjang (5-8 paragraf) dengan sumber terpercaya.
*   **🕵️‍♂️ Agent Reviewer**: Bertugas sebagai Pemimpin Redaksi untuk Fact-Checking ketat dan memastikan gaya bahasa serta sumber referensi ditulis.
""")
st.divider()

def get_graph():
    return build_graph()

app_graph = get_graph()

# UI Model Selection di Sidebar
with st.sidebar:
    st.header("⚙️ Konfigurasi Eksperimen Model")
    model_options = {
        "Gemini 3.5 Flash": "gemini/gemini-3.5-flash",
        "Qwen 3.8 27B (Groq)": "groq/qwen/qwen3.8-27b",
        "GPT-OSS 120B (Groq)": "groq/openai/gpt-oss-120b",
        "GPT-OSS 20B (Groq)": "groq/openai/gpt-oss-20b",
        "Command A+ (Cohere)": "cohere/command-a-plus-05-2026",
    }
    
    writer_choice = st.selectbox("Pilih Model Writer (Generator):", list(model_options.keys()), index=1)
    reviewer_choice = st.selectbox("Pilih Model Reviewer (Evaluator):", list(model_options.keys()), index=0)
    
    writer_model_id = model_options[writer_choice]
    reviewer_model_id = model_options[reviewer_choice]

    st.divider()
    st.subheader("💾 Unduh Data Riset")
    if os.path.exists("experiment_metrics.csv"):
        with open("experiment_metrics.csv", "rb") as f:
            st.download_button(
                label="📥 Unduh experiment_metrics.csv",
                data=f,
                file_name="experiment_metrics.csv",
                mime="text/csv",
                use_container_width=True
            )
    else:
        st.caption("Belum ada data eksperimen tersimpan.")

# Input UI
topic = st.text_input("🔍 Topik atau Pertanyaan Anda:", placeholder="Contoh: Sejarah Suku Baduy")

if st.button("Mulai Menulis", type="primary"):
    if not topic.strip():
        st.warning("Silakan masukkan topik terlebih dahulu!")
    else:
        start_time = time.time()
        
        initial_state = {
            "topic": topic,
            "context": "",
            "draft": "",
            "revision_notes": "",
            "revision_count": 1,
            "is_passed": False,
            "writer_model": writer_model_id,
            "reviewer_model": reviewer_model_id,
            "writer_tokens": 0,
            "reviewer_tokens": 0,
            "grader_tokens": 0,
            "start_time": start_time
        }
        
        final_state = initial_state.copy()
        
        # UI Status Progress
        with st.status("Sistem Redaksi Multi-Agent sedang bekerja...", expanded=True) as status:
            st.write("📡 **Mencari referensi jurnalistik di database / Wikipedia...**")
            
            try:
                for event in app_graph.stream(initial_state):
                    for node_name, state_update in event.items():
                        final_state.update(state_update)
                        
                        if node_name == "retriever":
                            st.write(f"✅ **Database**: Berhasil menemukan/mengunduh dokumen referensi.")
                        elif node_name == "writer":
                            iterasi = final_state.get('revision_count', 1)
                            st.write(f"✍️ **Agent Writer**: Menulis draf (Iterasi ke-{iterasi}) dengan {writer_choice}...")
                        elif node_name == "reviewer":
                            if final_state.get('is_passed'):
                                st.success(f"🕵️‍♂️ **Agent Reviewer ({reviewer_choice})**: KEPUTUSAN: **LULUS**! Artikel sudah sesuai standar.")
                            else:
                                st.error(f"🕵️‍♂️ **Agent Reviewer ({reviewer_choice})**: KEPUTUSAN: **DITOLAK / REVISI**")
                                st.warning(f"Catatan Pemred: {final_state.get('revision_notes', '')}")
                
                status.update(label=f"Proses Selesai dalam {final_state.get('revision_count', 2) - 1} iterasi!", state="complete", expanded=False)
                
            except Exception as e:
                st.error(f"Terjadi kesalahan: {str(e)}")
                status.update(label="Proses gagal.", state="error")
                st.stop()
        
        end_time = time.time()
        total_latency = end_time - start_time
        
        # Ekstraksi dan Log Metrik
        try:
            log_metrics(final_state, total_latency)
        except Exception as e:
            st.warning(f"Gagal menyimpan metrik ke CSV: {e}")
        
        # Tampilan Hasil
        st.subheader("📄 Hasil Akhir Artikel (Siap Terbit)")
        st.info(final_state.get("draft", "Gagal menghasilkan draf."))
        
        with st.expander("📚 Lihat Sumber Data Asli (Konteks)"):
            st.write(final_state.get("context", "Konteks kosong."))
            
        with st.expander("📊 Metrik Eksperimen (Fase 3 & 4)"):
            col1, col2, col3, col4 = st.columns(4)
            col1.metric("Waktu Total", f"{total_latency:.2f} dtk")
            col2.metric("Token Writer", final_state.get("writer_tokens", 0))
            col3.metric("Token Reviewer", final_state.get("reviewer_tokens", 0))
            col4.metric("Token Grader", final_state.get("grader_tokens", 0))
            st.caption("Data metrik ini telah disimpan secara otomatis ke dalam `experiment_metrics.csv`.")
