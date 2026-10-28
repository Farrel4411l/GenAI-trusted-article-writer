# Implementation Plan: Autonomous Daily Editorial Pipeline (Travelista AI)

Dokumen ini adalah cetak biru (*blueprint*) resmi pengembangan fitur **Pembuatan Artikel Otomatis Harian (Autonomous Daily Editorial Pipeline)** pada sistem Multi-Agent RAG Travelista.id. Dokumen ini dibuat sebagai acuan kerja presisi agar pengembangan tetap terarah dan **tidak menyentuh atau merusak fitur utama yang sudah berjalan stabil**.

---

## 1. Prinsip Utama: *Zero-Touch Core Architecture*
1. **Isolasi Modul Baru**: Seluruh fitur otomasi harian ditempatkan di dalam direktori baru `src/automation/` dan skrip pemicu `run_daily_job.py`.
2. **Keutuhan Mesin Inti**: File inti yang sudah berjalan stabil (`src/agents/orchestrator.py`, `src/agents/writer_agent.py`, `src/agents/reviewer_agent.py`, `src/agents/prompts.py`, `src/retriever/search.py`, dan `src/utils/token_tracker.py`) **TIDAK DIUBAH** logika intinya.
3. **Antarmuka Non-Intrusif**: Pada `app.py`, fitur manual yang sudah ada tetap dipertahankan 100% di Tab Utama (`✍️ Studio Redaksi Manual`), sementara fitur otomasi harian ditambahkan pada Tab Kedua (`🤖 Redaksi Otomatis Harian`).

---

## 2. Daftar Genre Resmi Travelista.id
Sistem pencarian tren dan penulisan otomatis dibatasi secara ketat pada 4 genre resmi Travelista:
1. **Wisata & Destinasi (Travel)**: Destinasi wisata alam, taman nasional, pulau, gunung, pantai, dan panduan perjalanan di Indonesia.
2. **Kuliner Nusantara**: Makanan tradisional, minuman khas daerah, sejarah kuliner, dan filosofi hidangan lokal Indonesia.
3. **Sejarah & Misteri Lokal**: Sejarah kerajaan/candi, bangunan kolonial bersejarah, mitos lokal, dan kisah misteri tempat ikonik di Nusantara.
4. **Budaya & Fakta Unik**: Tradisi adat, suku bangsa, seni pertunjukan, warisan budaya (Batik, Wayang, dll.), dan keunikan geografi/sosial Indonesia.

---

## 3. Arsitektur 6 Tahap (*End-to-End Autonomous Pipeline*)

### Tahap 1: Trend Analyzer & Editorial Planner (`src/automation/trend_hunter.py`)
- **Sumber Tren**:
  - Google Trends Daily RSS Indonesia (`geo=ID`).
  - Google News RSS Indonesia spesifik untuk 4 klaster genre Travelista.
  - Pool kurasi topik Nusantara sebagai pengaya (*enrichment*) agar pencarian konteks di Wikipedia/pgvector selalu kaya fakta.
- **Anti-Duplikasi Topik**: Mengecek tabel `daily_auto_articles` di Supabase untuk menghindari topik yang sudah pernah ditulis dalam 30 hari terakhir.
- **Output Terstruktur**:
  - `genre`: Salah satu dari 4 genre resmi Travelista.
  - `trending_keyword`: Kata kunci/isu yang sedang ramai dicari.
  - `trend_source`: Sumber tren (Google Trends / Google News ID).
  - `topic`: Kueri entitas bersih untuk pencarian RAG (`search.py`), misal `"Kawah Ijen dan Banyuwangi"`.
  - `target_title`: Judul artikel jurnalistik yang memikat dan SEO-friendly.
  - `editorial_angle`: Panduan sudut pandang penulisan bagi Agent Writer.

### Tahap 2: Smart Model Router (`src/automation/model_router.py`)
- **Fungsi**: Memilih kombinasi terbaik `writer_model` dan `reviewer_model` secara otomatis berdasarkan **Genre**, **Kompleksitas Topik**, dan **Sisa Kuota Token** (`token_tracker.py`).
- **Matriks Spesialisasi**:
  - *Wisata & Destinasi* / *Kuliner Nusantara* (Narasi mengalir & deskriptif):
    - Prioritas Writer: `groq/openai/gpt-oss-120b` $\rightarrow$ `gemini/gemini-3.5-flash` $\rightarrow$ `cohere/command-a-plus-05-2026` $\rightarrow$ `groq/qwen/qwen3.8-27b`.
    - Prioritas Reviewer: `gemini/gemini-3.5-flash` $\rightarrow$ `cohere/command-a-plus-05-2026` $\rightarrow$ `groq/openai/gpt-oss-20b`.
  - *Sejarah & Misteri Lokal* / *Budaya & Fakta Unik* (Sintesis fakta padat & akurasi historis):
    - Prioritas Writer: `cohere/command-a-plus-05-2026` $\rightarrow$ `gemini/gemini-3.5-flash` $\rightarrow$ `groq/openai/gpt-oss-120b`.
    - Prioritas Reviewer: `gemini/gemini-3.5-flash` $\rightarrow$ `cohere/command-a-plus-05-2026` $\rightarrow$ `groq/openai/gpt-oss-120b`.
- **Quota & API Key Guard**: Memastikan API Key tersedia di environment dan sisa kuota model $\ge 15.000$ token.

### Tahap 3: Eksekusi Inti RAG + Writer + Fact-Checker (`src/agents/orchestrator.py`)
- Memanggil `build_graph()` yang sudah ada.
- **Checker 1 (`reviewer_agent.py`)**: Melakukan *Fact-Checking* ketat terhadap kredibilitas sumber dan memastikan tidak ada klaim halusinasi di luar konteks asli.

### Tahap 4: Checker Akhir / Final Gatekeeper (`src/automation/final_checker_agent.py`)
- **Checker 2 (Post-Fact-Check Verification)**: Bekerja setelah artikel selesai dari Checker 1.
- **Tugas Pemeriksaan & Pengemasan**:
  1. **Kesesuaian Judul (`Title Alignment`)**: Memastikan judul utama (`# Judul`) terpasang rapi dan sesuai dengan isi serta `target_title`.
  2. **Kesesuaian Topik & Genre (`Topic & Genre Compliance`)**: Memvalidasi apakah narasi telah mencerminkan genre yang ditentukan (`Wisata`, `Kuliner`, `Sejarah & Misteri`, atau `Budaya & Fakta Unik`).
  3. **Kesesuaian Format (`Format & Structure Check`)**: Memastikan struktur 5–8 paragraf utuh dan bagian `**Sumber Referensi:**` di akhir artikel berisi tautan unik yang valid.
  4. **Standarisasi Skema CMS (`Auto-Deploy Readiness`)**: Mengekstrak paket JSON standar (`title`, `slug`, `genre`, `meta_description`, `tags`, `content_markdown`, `references`) agar siap di-copas redaksi maupun dikirim via Webhook/API CMS ke depannya.

### Tahap 5: Penyimpanan Cloud Supabase (`src/automation/storage_supabase.py`)
- Membuat dan mengelola tabel `daily_auto_articles` di Supabase PostgreSQL tanpa menyentuh tabel vektor `langchain_pg_embedding`.
- Menyimpan seluruh hasil artikel harian, metadata tren, alasan pemilihan model, status Checker 1 & Checker 2, serta payload JSON CMS.

### Tahap 6: Penjadwalan Cron Job 10:00 WIB (`.github/workflows/daily_editorial.yml` & `run_daily_job.py`)
- Menggunakan GitHub Actions dengan jadwal `cron: '0 3 * * *'` (03:00 UTC = **10:00 WIB** setiap hari).
- Menjalankan `python run_daily_job.py` secara otomatis di cloud dan menyimpan hasilnya ke Supabase sehingga tim redaksi tinggal menyalin (*copy-paste*) artikel yang sudah matang di Streamlit UI.

---

## 4. Daftar File yang Dibuat / Diperbarui
- [x] `implementationplan.md` & `implementation_plan_travelista.md` (Dokumentasi Blueprint)
- [x] `src/automation/__init__.py`
- [x] `src/automation/storage_supabase.py` (Manajemen tabel `daily_auto_articles` di Supabase)
- [x] `src/automation/trend_hunter.py` (Pencari tren Google Trends/News ID & perumus Genre/Topik/Judul)
- [x] `src/automation/model_router.py` (Pemilih otomatis Model Writer & Reviewer berbasis Genre & Kuota)
- [x] `src/automation/final_checker_agent.py` (Checker ke-2 untuk validasi Judul, Topik, Genre, dan Format CMS)
- [x] `src/automation/daily_pipeline.py` (Orkestrator otomasi harian End-to-End)
- [x] `run_daily_job.py` (Script CLI eksekutor harian untuk Cron Job pukul 10:00 WIB)
- [x] `.github/workflows/daily_editorial.yml` (Konfigurasi GitHub Actions Cron 10:00 WIB)
- [x] `app.py` (Penambahan Tab `🤖 Redaksi Otomatis Harian (10:00 WIB)` tanpa mengubah fitur Tab Manual)
