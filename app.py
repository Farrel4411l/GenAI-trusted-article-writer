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
from src.utils.token_tracker import get_model_usage_stats, predict_token_usage

# Load environment variables
load_dotenv()

# Sinkronisasi Secrets Streamlit Cloud ke os.environ
try:
    for k, v in st.secrets.items():
        if isinstance(v, str):
            os.environ[k] = v
except Exception:
    pass

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

# Daftar opsi model
model_options = {
    "Gemini 3.5 Flash": "gemini/gemini-3.5-flash",
    "Qwen 3.8 27B (Groq)": "groq/qwen/qwen3.8-27b",
    "GPT-OSS 120B (Groq)": "groq/openai/gpt-oss-120b",
    "GPT-OSS 20B (Groq)": "groq/openai/gpt-oss-20b",
    "Command A+ (Cohere)": "cohere/command-a-plus-05-2026",
}

# Ambil statistik kuota dan sisa token masing-masing model
model_stats = get_model_usage_stats("experiment_metrics.csv", filter_today=False)

def format_model_option(option_label: str) -> str:
    m_id = model_options[option_label]
    st_info = model_stats.get(m_id, {})
    rem = st_info.get("remaining_tokens", 0)
    rem_pct = st_info.get("remaining_pct", 100.0)
    return f"{option_label} — Sisa: {rem:,} token ({rem_pct:.1f}%)"

# UI Model Selection & Kuota Token di Sidebar
with st.sidebar:
    st.header("⚙️ Konfigurasi Eksperimen Model")
    
    writer_choice = st.selectbox(
        "Pilih Model Writer (Generator):",
        list(model_options.keys()),
        index=1,
        format_func=format_model_option
    )
    reviewer_choice = st.selectbox(
        "Pilih Model Reviewer (Evaluator):",
        list(model_options.keys()),
        index=0,
        format_func=format_model_option
    )
    
    writer_model_id = model_options[writer_choice]
    reviewer_model_id = model_options[reviewer_choice]

    st.divider()
    st.subheader("🔋 Sisa Kuota Token Masing-Masing Model")
    for label, m_id in model_options.items():
        info = model_stats[m_id]
        rem_tokens = info["remaining_tokens"]
        total_quota = info["total_quota"]
        rem_pct = info["remaining_pct"]
        used_tokens = info["used_tokens"]
        used_pct = info["used_pct"]

        st.markdown(f"**{label}**")
        st.progress(min(1.0, max(0.0, rem_pct / 100.0)))
        st.caption(
            f"Sisa: **{rem_tokens:,}** / {total_quota:,} token (**{rem_pct:.2f}%**)  \n"
            f"Terpakai: {used_tokens:,} token ({used_pct:.2f}%)"
        )

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

# Panel Status Sisa Token Model Terpilih (Saat Awal Dibuka)
with st.expander("📊 Lihat Ringkasan Sisa Token Seluruh Opsi Model (Angka & Persen)", expanded=True):
    cols_quota = st.columns(len(model_options))
    for idx, (label, m_id) in enumerate(model_options.items()):
        info = model_stats[m_id]
        short_label = label.split(" (")[0]
        cols_quota[idx].metric(
            label=short_label,
            value=f"{info['remaining_tokens']:,}",
            delta=f"{info['remaining_pct']:.1f}% tersisa",
            help=f"Total Kuota: {info['total_quota']:,} token | Terpakai: {info['used_tokens']:,} token ({info['used_pct']:.2f}%)"
        )

# Input UI
topic = st.text_input("🔍 Topik atau Pertanyaan Anda:", placeholder="Contoh: Sejarah Suku Baduy")

# Panel Prediksi Pemakaian Token (Sebelum Menekan Enter / Mesin Berjalan)
with st.container(border=True):
    col_pred_head, col_pred_iter = st.columns([2.2, 1.2])
    with col_pred_head:
        st.markdown("#### 🔮 Prediksi Konsumsi Token (Pra-Eksekusi)")
        st.caption("Estimasi otomatis sebelum mesin dijalankan berdasarkan model terpilih & kompleksitas topik.")
    with col_pred_iter:
        pred_iter = st.selectbox(
            "Asumsi Siklus Iterasi:",
            options=[1, 2, 3],
            index=0,
            format_func=lambda x: f"{x} Iterasi ({'Lulus Langsung' if x == 1 else f'{x-1}x Revisi'})"
        )

    prediction = predict_token_usage(
        writer_model_id=writer_model_id,
        reviewer_model_id=reviewer_model_id,
        topic=topic,
        expected_iterations=pred_iter,
        stats=model_stats
    )
    prediction_2x = predict_token_usage(
        writer_model_id=writer_model_id,
        reviewer_model_id=reviewer_model_id,
        topic=topic,
        expected_iterations=2,
        stats=model_stats
    )

    pcol1, pcol2, pcol3 = st.columns(3)
    pcol1.metric(
        label=f"✍️ Writer + Grader ({writer_choice.split(' (')[0]})",
        value=f"~{prediction['pred_writer_total']:,} token",
        delta=f"-{prediction['writer_pct_of_total']:.2f}% dari total ({prediction['writer_pct_of_remaining']:.2f}% sisa)",
        delta_color="inverse",
        help=f"Rincian: Writer ~{prediction['pred_writer']:,} token + Grader ~{prediction['pred_grader']:,} token"
    )
    pcol2.metric(
        label=f"🕵️‍♂️ Reviewer ({reviewer_choice.split(' (')[0]})",
        value=f"~{prediction['pred_reviewer']:,} token",
        delta=f"-{prediction['reviewer_pct_of_total']:.2f}% dari total ({prediction['reviewer_pct_of_remaining']:.2f}% sisa)",
        delta_color="inverse",
        help=f"Estimasi pemakaian token evaluasi untuk {pred_iter} iterasi"
    )
    pcol3.metric(
        label="⚡ Total Prediksi Eksekusi",
        value=f"~{prediction['pred_total_all']:,} token",
        delta=f"-{prediction['total_pct_of_total']:.2f}% dari total ({prediction['total_pct_of_remaining']:.2f}% sisa)",
        delta_color="inverse",
        help=f"Total gabungan dari kapasitas kuota {prediction['combined_total_quota']:,} token"
    )

    if pred_iter == 1:
        st.caption(
            f"💡 **Info Prediksi**: Dalam 1 iterasi, proses ini diprediksi menghabiskan **~{prediction['pred_total_all']:,} token** "
            f"(**{prediction['total_pct_of_total']:.2f}%** dari total kuota). "
            f"Jika terjadi 1x revisi (2 iterasi), estimasi menjadi **~{prediction_2x['pred_total_all']:,} token** "
            f"(**{prediction_2x['total_pct_of_total']:.2f}%** dari total kuota)."
        )

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
        
        # Simpan ke session_state agar tidak hilang jika terjadi rerun
        st.session_state["final_state"] = final_state
        st.session_state["total_latency"] = total_latency

        # Ekstraksi dan Log Metrik
        try:
            log_metrics(final_state, total_latency)
        except Exception as e:
            st.warning(f"Gagal menyimpan metrik ke CSV: {e}")

# Tampilan Hasil (Persisten)
if "final_state" in st.session_state:
    saved_state = st.session_state["final_state"]
    saved_latency = st.session_state.get("total_latency", 0)

    st.subheader("📄 Hasil Akhir Artikel (Siap Terbit)")
    st.info(saved_state.get("draft", "Gagal menghasilkan draf."))
    
    with st.expander("📚 Lihat Sumber Data Asli (Konteks)"):
        st.write(saved_state.get("context", "Konteks kosong."))
        
    with st.expander("📊 Metrik Eksperimen (Fase 3 & 4)"):
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Waktu Total", f"{saved_latency:.2f} dtk")
        col2.metric("Token Writer", saved_state.get("writer_tokens", 0))
        col3.metric("Token Reviewer", saved_state.get("reviewer_tokens", 0))
        col4.metric("Token Grader", saved_state.get("grader_tokens", 0))
        st.caption("Data metrik ini telah disimpan secara otomatis ke dalam `experiment_metrics.csv`.")
