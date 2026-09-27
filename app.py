import streamlit as st
import os
import sys
from dotenv import load_dotenv

# Memastikan direktori root masuk ke path agar bisa import src
sys.path.append(os.path.abspath(os.path.dirname(__file__)))
from src.agents.orchestrator import build_graph

# Load environment variables
load_dotenv()

# Setup Halaman
st.set_page_config(page_title="Multi-Agent RAG | Anti-Halusinasi", page_icon="🤖", layout="centered")

st.title("🤖 AI Penulis Artikel (Bebas Halusinasi)")
st.markdown("""
Aplikasi cerdas ini ditenagai oleh **Multi-Agent RAG (LangGraph)**.
Sistem ini menggunakan dua agen kecerdasan buatan yang bekerja sama:
*   ✍️ **Agent Writer**: Bertugas menulis draf berdasarkan sumber (konteks) asli.
*   🕵️‍♂️ **Agent Reviewer**: Bertugas sebagai *Fact-Checker* ketat yang akan menegur Writer jika berhalusinasi/mengarang.
""")
st.divider()

# Inisialisasi Graph
# (Tanpa cache agar selalu memuat prompt dan database terbaru jika ada perubahan)
def get_graph():
    return build_graph()

app_graph = get_graph()

# Input UI
topic = st.text_input("🔍 Topik atau Pertanyaan Anda:", placeholder="Contoh: Siapa saja tokoh Ikatan Ahli Arkeologi Indonesia?")

if st.button("Mulai Menulis", type="primary"):
    if not topic.strip():
        st.warning("Silakan masukkan topik terlebih dahulu!")
    else:
        initial_state = {
            "topic": topic,
            "context": "",
            "draft": "",
            "revision_notes": "",
            "revision_count": 1,
            "is_passed": False
        }
        
        final_state = initial_state.copy()
        
        # UI Status Progress
        with st.status("Sistem Multi-Agent sedang bekerja...", expanded=True) as status:
            st.write("📡 **Menghubungkan ke Database...**")
            
            # LangGraph Stream untuk menangkap aksi agen secara real-time
            try:
                for event in app_graph.stream(initial_state):
                    for node_name, state_update in event.items():
                        # Update status internal untuk dipantau
                        final_state.update(state_update)
                        
                        if node_name == "retriever":
                            st.write(f"✅ **Database**: Berhasil menarik dokumen sumber.")
                        elif node_name == "writer":
                            iterasi = final_state.get('revision_count', 1)
                            st.write(f"✍️ **Agent Writer**: Menulis draf (Iterasi ke-{iterasi})...")
                        elif node_name == "reviewer":
                            if final_state.get('is_passed'):
                                st.success(f"🕵️‍♂️ **Agent Reviewer**: KEPUTUSAN: **LULUS**! Tidak ditemukan halusinasi.")
                            else:
                                st.error("🕵️‍♂️ **Agent Reviewer**: KEPUTUSAN: **DITOLAK / REVISI**")
                                st.warning(f"Catatan Reviewer: {final_state.get('revision_notes', '')}")
                
                status.update(label=f"Proses Selesai dalam {final_state['revision_count'] - 1} iterasi!", state="complete", expanded=False)
                
            except Exception as e:
                st.error(f"Terjadi kesalahan: {str(e)}")
                status.update(label="Proses gagal.", state="error")
                st.stop()
        
        # Tampilan Hasil
        st.subheader("📄 Hasil Akhir Artikel")
        st.info(final_state.get("draft", "Gagal menghasilkan draf."))
        
        with st.expander("📚 Lihat Sumber Data Asli (Konteks)"):
            st.write(final_state.get("context", "Konteks kosong."))
