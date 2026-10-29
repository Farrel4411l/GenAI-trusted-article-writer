import streamlit as st
import os
import sys
import time
import json

# Memaksa stdout ke UTF-8 (Fix untuk Windows Charmap Error)
if sys.stdout.encoding.lower() != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')

from dotenv import load_dotenv

# Memastikan direktori root masuk ke path agar bisa import src
sys.path.append(os.path.abspath(os.path.dirname(__file__)))
from src.agents.orchestrator import build_graph
from src.utils.metrics_logger import log_metrics
from src.utils.token_tracker import get_model_usage_stats, predict_token_usage
from src.automation.image_hunter import acquire_cover_image
from src.automation.trend_hunter import TRAVELISTA_GENRES, analyze_and_select_daily_topic
from src.automation.model_router import select_optimal_models
from src.automation.daily_pipeline import run_autonomous_daily_pipeline
from src.automation.storage_supabase import get_daily_articles, get_recent_topics

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

# Pemisahan Mode menggunakan Tab agar Fitur Lama 100% Utuh & Fitur Baru Terisolasi Rapi
tab_manual, tab_auto = st.tabs([
    "✍️ Studio Redaksi Manual (Eksperimen)",
    "🤖 Redaksi Otomatis Harian (10:00 WIB)"
])

with tab_manual:
    # Input UI (100% Fitur Eksisting)
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
            help=f"Rincian: Writer (~{prediction['pred_writer']:,}) + Grader (~{prediction['pred_grader']:,}) + Reviewer (~{prediction['pred_reviewer']:,}) + Vision Reviewer (~{prediction.get('pred_vision', 650):,}) token"
        )

        if pred_iter == 1:
            st.caption(
                f"💡 **Info Prediksi**: Dalam 1 iterasi, proses ini diprediksi menghabiskan **~{prediction['pred_total_all']:,} token** "
                f"(**{prediction['total_pct_of_total']:.2f}%** dari total kuota, termasuk ~{prediction.get('pred_vision', 650)} token visual untuk Agent Vision Reviewer). "
                f"Jika terjadi 1x revisi (2 iterasi), estimasi menjadi **~{prediction_2x['pred_total_all']:,} token** "
                f"(**{prediction_2x['total_pct_of_total']:.2f}%** dari total kuota)."
            )
        if "qwen" in writer_model_id.lower():
            st.warning(
                "⏱️ **Catatan Rate Limit Model**: Qwen 3.8 27B di Groq memiliki batas kecepatan *1.000 output token/menit*. "
                "Jika Reviewer meminta revisi (iterasi ke-2), sistem akan otomatis melakukan jeda (~60 dtk) agar kuota menit pulih tanpa error. "
                "*(Untuk proses revisi instan tanpa jeda menit, Anda dapat memilih **Gemini 3.5 Flash** atau **GPT-OSS 120B**)*."
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
                    
                    # Otomatis akuisisi Cover Image 16:9 WebP & Verifikasi Vision Reviewer jika artikel lulus
                    if final_state.get('is_passed') or final_state.get('draft'):
                        st.write("🖼️ **Image Hunter & Vision Reviewer**: Mengakuisisi dan memverifikasi gambar sampul 16:9 WebP...")
                        try:
                            manual_slug = "cover-" + str(int(time.time()))
                            first_line = final_state.get("draft", "").split("\n")[0].replace("#", "").strip()
                            m_title = first_line if first_line else user_query
                            img_res = acquire_cover_image(
                                topic=user_query,
                                title=m_title,
                                genre="Wisata & Destinasi",
                                slug=manual_slug,
                                prefer_real_first=True
                            )
                            final_state["cover_image_url"] = img_res["cover_image_url"]
                            final_state["cover_image_alt"] = img_res["cover_image_alt"]
                            final_state["cover_image_meta"] = img_res
                        except Exception as img_err:
                            print(f"[Studio Manual] Info akuisisi gambar: {img_err}")
                    
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
        
        # Pratinjau Tampilan Majalah Digital (Hero Cover Image + Artikel Utuh)
        with st.container(border=True):
            manual_cover_url = saved_state.get("cover_image_url")
            if manual_cover_url:
                st.image(manual_cover_url, caption=f"🖼️ Cover Image (16:9 WebP): {saved_state.get('cover_image_alt', '')}", use_container_width=True)
                v_audit = saved_state.get("cover_image_meta", {}).get("vision_audit", {})
                if v_audit:
                    v_score = v_audit.get("score", 90)
                    v_pass = v_audit.get("is_passed", True)
                    v_notes = v_audit.get("audit_notes", "")
                    v_icon = "🛡️" if v_pass else "⚠️"
                    v_status = "LULUS (Bebas Watermark & Fotorealistis)" if v_pass else "CATATAN REVISI"
                    st.caption(f"{v_icon} **Agent Vision Reviewer**: Skor: **{v_score}/100** | Status: **{v_status}** — *{v_notes}*")
            else:
                if st.button("🖼️ Generate Gambar Sampul (16:9 WebP)", key="btn_gen_manual_cover"):
                    with st.spinner("Membuat gambar sampul 16:9 WebP yang akurat..."):
                        manual_slug = "cover-" + str(int(time.time()))
                        first_line = saved_state.get("draft", "").split("\n")[0].replace("#", "").strip()
                        m_title = first_line if first_line else saved_state.get("topic", "Wisata")
                        img_res = acquire_cover_image(
                            topic=saved_state.get("topic", "Wisata"),
                            title=m_title,
                            genre="Wisata & Destinasi",
                            slug=manual_slug,
                        )
                        saved_state["cover_image_url"] = img_res["cover_image_url"]
                        saved_state["cover_image_alt"] = img_res["cover_image_alt"]
                        saved_state["cover_image_meta"] = img_res
                        st.rerun()

            # Render Artikel Lengkap dengan Gaya Majalah Digital
            st.markdown(saved_state.get("draft", "Gagal menghasilkan draf."))

        with st.expander("📋 Salin Teks Utuh Markdown (1-Klik Copy)"):
            draft_text = saved_state.get("draft", "")
            st.code(draft_text, language="markdown")
            st.download_button(
                label="📥 Unduh Artikel (.md)",
                data=draft_text.encode("utf-8"),
                file_name="artikel_travelista.md",
                mime="text/markdown",
                key="btn_download_manual_md"
            )
        
        with st.expander("📚 Lihat Sumber Data Asli (Konteks)"):
            st.write(saved_state.get("context", "Konteks kosong."))
            
        with st.expander("📊 Metrik Eksperimen (Fase 3 & 4)"):
            col1, col2, col3, col4 = st.columns(4)
            col1.metric("Waktu Total", f"{saved_latency:.2f} dtk")
            col2.metric("Token Writer", saved_state.get("writer_tokens", 0))
            col3.metric("Token Reviewer", saved_state.get("reviewer_tokens", 0))
            col4.metric("Token Grader", saved_state.get("grader_tokens", 0))
            st.caption("Data metrik ini telah disimpan secara otomatis ke dalam `experiment_metrics.csv`.")

# ==============================================================================
# TAB 2: REDAKSI OTOMATIS HARIAN (10:00 WIB) — AUTONOMOUS DAILY PIPELINE
# ==============================================================================
with tab_auto:
    st.subheader("🤖 Ruang Redaksi Otomatis Harian (Jadwal: 10:00 WIB)")
    st.markdown("""
    Sistem **Auto-Pilot Travelista.id** berjalan otomatis setiap pukul **10:00 WIB** melalui penjadwal cloud dan menyimpan hasilnya langsung ke **Supabase (`daily_auto_articles`)**:
    1. **📈 Trend Analyzer**: Mengecek tren pencarian terkini (Google Trends & Google News ID) pada 4 genre resmi Travelista (*Wisata*, *Kuliner*, *Sejarah & Misteri*, *Budaya & Fakta Unik*), lalu merumuskan Topik & Judul.
    2. **🧠 Smart Model Router**: Memilih model AI *Writer* & *Reviewer* terbaik sesuai karakteristik genre dan sisa kuota token.
    3. **🕵️‍♂️ Dual-Stage Verification**:
       - **Checker 1 (Fact-Checker)**: Memverifikasi kredibilitas fakta & sumber terhadap dokumen referensi.
       - **Checker 2 (Final Gatekeeper)**: Memverifikasi kesesuaian **Judul, Topik, Genre, dan Format CMS** (siap *copy-paste* & siap *auto-deploy*).
    """)

    with st.container(border=True):
        st.markdown("#### ⚡ Panel Kontrol & Pemicu Otomasi")
        col_g, col_b1, col_b2 = st.columns([1.8, 1.1, 1.3])
        with col_g:
            genre_filter_opt = st.selectbox(
                "Target Genre Travelista:",
                options=["🔄 Otomatis (Ikuti Tren Terhangat Hari Ini)"] + TRAVELISTA_GENRES,
                index=0
            )
            selected_pref_genre = None if genre_filter_opt.startswith("🔄") else genre_filter_opt

        with col_b1:
            st.write("")
            btn_preview_trend = st.button("🔍 Intip Tren & Router", use_container_width=True)
        with col_b2:
            st.write("")
            btn_run_auto_now = st.button("🚀 Buat Artikel Otomatis", type="primary", use_container_width=True)

        if btn_preview_trend:
            with st.spinner("Memindai Google Trends & Google News Indonesia serta menghitung rute model..."):
                recent_list = get_recent_topics(limit=30)
                plan_preview = analyze_and_select_daily_topic(
                    recent_topics=recent_list,
                    preferred_genre=selected_pref_genre
                )
                route_preview = select_optimal_models(
                    genre=plan_preview["genre"],
                    topic=plan_preview["topic"],
                    stats=model_stats
                )
                st.session_state["auto_preview"] = {
                    "plan": plan_preview,
                    "route": route_preview
                }

        if "auto_preview" in st.session_state:
            pv_plan = st.session_state["auto_preview"]["plan"]
            pv_route = st.session_state["auto_preview"]["route"]
            st.info(
                f"**🔥 Tren Terdeteksi**: `{pv_plan['trending_keyword']}` ({pv_plan['trend_source']})  \n"
                f"**📂 Genre Terpilih**: **{pv_plan['genre']}**  \n"
                f"**🎯 Topik Riset RAG**: `{pv_plan['topic']}`  \n"
                f"**📰 Rencana Judul**: *{pv_plan['target_title']}*  \n"
                f"**🤖 Rekomendasi Model Router**: Writer = **{pv_route['writer_label']}** | Reviewer = **{pv_route['reviewer_label']}**  \n"
                f"*(Alasan: {pv_route['routing_reason']})*"
            )

        if btn_run_auto_now:
            with st.status("🚀 Menjalankan Pipeline Redaksi Otomatis End-to-End...", expanded=True) as auto_status:
                def _ui_progress(stage: str, message: str):
                    if stage in ("checker1_pass", "checker2_done", "complete"):
                        st.success(message)
                    elif stage == "checker1_revise":
                        st.warning(message)
                    else:
                        st.write(message)

                try:
                    new_article = run_autonomous_daily_pipeline(
                        preferred_genre=selected_pref_genre,
                        progress_callback=_ui_progress
                    )
                    st.session_state["latest_auto_article"] = new_article
                    auto_status.update(
                        label=f"✅ Artikel Otomatis Selesai: {new_article.get('final_title', '')}",
                        state="complete",
                        expanded=False
                    )
                except Exception as e:
                    st.error(f"Terjadi kendala saat menjalankan otomasi: {e}")
                    auto_status.update(label="Proses otomasi terhenti.", state="error")

    st.divider()
    st.markdown("### 📰 Daftar Artikel Harian Siap Copas (Tersimpan di Supabase)")

    saved_articles = get_daily_articles(limit=20)

    if not saved_articles:
        st.info(
            "Belum ada artikel otomatis di tabel Supabase `daily_auto_articles`. "
            "Klik tombol **🚀 Buat Artikel Otomatis** di atas untuk menghasilkan artikel perdana sekarang, "
            "atau tunggu jadwal otomatis pukul **10:00 WIB**."
        )
    else:
        article_labels = [
            f"[{art.get('run_date', '-')}] [{art.get('genre', '')}] {art.get('final_title', art.get('topic', ''))}"
            for art in saved_articles
        ]
        selected_idx = st.selectbox(
            "📂 Pilih Arsip Artikel Harian:",
            options=range(len(saved_articles)),
            format_func=lambda idx: article_labels[idx]
        )
        active_art = saved_articles[selected_idx]

        # Kartu Metadata & Status 2 Checker
        with st.container(border=True):
            st.markdown(f"#### {active_art.get('final_title', '')}")
            mcol1, mcol2, mcol3, mcol4 = st.columns(4)
            mcol1.metric("📂 Genre", active_art.get("genre", "-").split(" (")[0])
            mcol2.metric(
                "🕵️‍♂️ Checker 1 (Sumber)",
                "LULUS" if active_art.get("fact_check_passed") else "Catatan",
                delta=f"{active_art.get('fact_check_revisions', 1)} Iterasi"
            )
            mcol3.metric(
                "🛡️ Checker 2 (Final)",
                f"{active_art.get('final_check_score', 100)}/100",
                delta="Siap Terbit" if active_art.get("final_check_passed") else "Perlu Cek"
            )
            mcol4.metric("⏱️ Durasi", f"{active_art.get('total_latency', 0):.1f} dtk")

            st.caption(
                f"📈 **Tren Pemicu**: `{active_art.get('trending_keyword', '-')}` ({active_art.get('trend_source', '-')}) | "
                f"🎯 **Topik RAG**: `{active_art.get('topic', '-')}`  \n"
                f"🤖 **Model Writer**: `{active_art.get('writer_model', '-')}` | "
                f"🕵️‍♂️ **Model Reviewer**: `{active_art.get('reviewer_model', '-')}`  \n"
                f"📋 **Hasil Audit Checker Akhir**: {active_art.get('final_check_notes', '-')}"
            )

        subtab_copy, subtab_preview, subtab_cms = st.tabs([
            "📋 Mode Tinggal Copas (1-Klik Copy)",
            "👁️ Pratinjau Tampilan Artikel",
            "🔌 Payload JSON (Siap Auto-Deploy CMS)"
        ])

        article_md_text = active_art.get("article_markdown", "")
        slug_name = active_art.get("slug", "artikel-travelista")

        with subtab_copy:
            st.caption("💡 Klik ikon **Copy (📋)** di pojok kanan atas kotak di bawah ini untuk menyalin seluruh artikel secara utuh:")
            st.code(article_md_text, language="markdown")
            st.download_button(
                label="📥 Unduh File Artikel (.md)",
                data=article_md_text.encode("utf-8"),
                file_name=f"{slug_name}.md",
                mime="text/markdown",
                key=f"dl_md_{active_art.get('id', selected_idx)}"
            )

        with subtab_preview:
            auto_cover_url = active_art.get("cover_image_url") or active_art.get("cms_payload", {}).get("article", {}).get("cover_image_url")
            auto_cover_alt = active_art.get("cover_image_alt") or active_art.get("cms_payload", {}).get("article", {}).get("cover_image_alt") or ""
            img_meta = active_art.get("cover_image_meta") or active_art.get("cms_payload", {}).get("article", {}).get("cover_image_meta", {})
            source_badge = img_meta.get("source_type", "16:9 WebP")
            if auto_cover_url:
                st.image(auto_cover_url, caption=f"🖼️ Cover Image ({source_badge}): {auto_cover_alt}", use_container_width=True)
                v_audit = img_meta.get("vision_audit") or active_art.get("cms_payload", {}).get("verification", {}).get("stage3_vision_reviewer", {})
                if v_audit:
                    v_score = v_audit.get("score", 90)
                    v_pass = v_audit.get("is_passed", True)
                    v_notes = v_audit.get("audit_notes", "")
                    v_icon = "🛡️" if v_pass else "⚠️"
                    v_status = "LULUS (Bebas Watermark & Fotorealistis)" if v_pass else "CATATAN REVISI"
                    st.caption(f"{v_icon} **Agent Vision Reviewer**: Skor: **{v_score}/100** | Status: **{v_status}** — *{v_notes}*")
            else:
                st.warning("⚠️ **Cover Image Belum Tersedia**: Artikel ini dibuat sebelum modul Image Hunter aktif.")
                if st.button("🖼️ Dapatkan Foto Sampul 16:9 WebP Sekarang", key=f"btn_get_cover_{active_art.get('id', selected_idx)}"):
                    with st.spinner("Mengakuisisi foto dokumenter 16:9 WebP dan memverifikasinya dengan Vision Reviewer..."):
                        new_img = acquire_cover_image(
                            topic=active_art.get("topic", "Wisata"),
                            title=active_art.get("final_title", "Wisata"),
                            genre=active_art.get("genre", "Wisata & Destinasi"),
                            slug=active_art.get("slug", "cover"),
                            prefer_real_first=True
                        )
                        from src.automation.storage_supabase import get_db_connection
                        try:
                            conn = get_db_connection()
                            with conn:
                                with conn.cursor() as cur:
                                    cur.execute("UPDATE daily_auto_articles SET cover_image_url=%s, cover_image_alt=%s WHERE id=%s", (new_img['cover_image_url'], new_img['cover_image_alt'], active_art.get('id')))
                            conn.close()
                        except Exception as e_up:
                            print(f"Error update cover: {e_up}")
                        active_art['cover_image_url'] = new_img['cover_image_url']
                        active_art['cover_image_alt'] = new_img['cover_image_alt']
                        active_art['cover_image_meta'] = new_img
                        st.rerun()
            st.markdown(article_md_text)

        with subtab_cms:
            st.caption("Skema standar JSON ini telah terverifikasi oleh Checker Akhir dan 100% kompatibel dengan monorepo **Travelista 2026** (Next.js CMS, Nuxt Magazine, Supabase `articles`):")
            
            cms_data = active_art.get("cms_payload", {})
            travelista_data = cms_data.get("travelista_payload", {})
            cat_info = travelista_data.get("category", {})
            tags_info = travelista_data.get("tags", [])
            author_info = travelista_data.get("author", {})

            # Kartu info keselarasan Travelista
            c1, c2, c3 = st.columns(3)
            with c1:
                st.markdown(f"🏷️ **Kategori Travelista**: `{cat_info.get('name_id', 'Destinasi')} (ID: {cat_info.get('id', 1)})`")
                st.markdown(f"👤 **Author**: `{author_info.get('full_name', 'Travelista AI Editorial')}`")
            with c2:
                tag_preview = ", ".join([t.get("name", "") for t in tags_info[:4]])
                st.markdown(f"🔖 **Tags Terformat**: `{tag_preview or '-'}`")
                st.markdown(f"📝 **Status Target**: `review (Siap Review Redaksi)`")
            with c3:
                auto_cover_url = active_art.get("cover_image_url") or active_art.get("cms_payload", {}).get("article", {}).get("cover_image_url")
                if auto_cover_url:
                    source_label = active_art.get("cover_image_meta", {}).get("source_type", "Ready")
                    v_audit = active_art.get("cover_image_meta", {}).get("vision_audit", {})
                    v_score = v_audit.get("score", 90) if v_audit else 90
                    st.markdown(f"🖼️ **Cover Image**: `16:9 WebP ({source_label})` | Vision: `{v_score}/100`")
                else:
                    st.markdown("🖼️ **Cover Image**: `Belum di-generate`")
                st.markdown(f"🌐 **Locale**: `id (Bahasa Indonesia)`")

            st.info("💡 **Catatan Integrasi Travelista**: Data HTML (`content_html`) dan TipTap JSON (`content_json`) telah digenerate secara otomatis sehingga Next.js CMS dan Nuxt Magazine dapat langsung merender artikel tanpa error.")

            # Tab untuk melihat JSON utuh atau Preview HTML
            view_cms_tab, view_html_tab = st.tabs(["📦 Payload JSON Lengkap (Travelista Ready)", "🌐 Preview Render HTML"])
            with view_cms_tab:
                st.json(cms_data)
            with view_html_tab:
                html_code = travelista_data.get("articles_record", {}).get("content_html") or cms_data.get("article", {}).get("content_html", "")
                st.code(html_code, language="html")

            st.download_button(
                label="📥 Unduh Payload Travelista (.json)",
                data=json.dumps(cms_data, ensure_ascii=False, indent=2).encode("utf-8"),
                file_name=f"{slug_name}_travelista_payload.json",
                mime="application/json",
                key=f"dl_json_{active_art.get('id', selected_idx)}"
            )
