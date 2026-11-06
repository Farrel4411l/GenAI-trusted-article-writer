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

## 3. Arsitektur 8 Tahap (*End-to-End Autonomous Pipeline*)

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

### Tahap 6: Penjadwalan Cron Job 09:00 WIB & Alur Pengiriman Terkendali (`.github/workflows/daily_editorial.yml`, `run_daily_job.py`, `src/automation/travelista_sender.py`)
- **Strategi Volume Penerbitan Bertahap (SEO Golden Ratio)**:
  - **Bulan ke-1 (Fase Kalibrasi, Testing, & Validasi Redaksi)**: Memproduksi **4 artikel harian (1 artikel per genre resmi Travelista: Wisata, Kuliner, Sejarah, Budaya)** setiap pukul **09:00 WIB** (02:00 UTC) secara berurutan (*batch mode*).
  - **Alur Kerja Terkendali (Human-in-the-Loop Validation)**:
    - **Fase Uji Coba (Mode 1 Sandbox - Default)**: Seluruh 4 artikel disimpan ke database Supabase (`daily_auto_articles`) dan siap ditinjau secara transparan melalui Streamlit UI (`tab_auto`). Redaktur/Farrel memeriksa konsistensi kualitas artikel sebelum dikirim ke CMS produksi.
    - **Fase Otomatis Penuh (Mode 2 Auto-Dispatch)**: Begitu kualitas artikel dinilai konsisten stabil, flag `AUTO_SEND_TO_CMS='true'` diaktifkan sehingga artikel langsung terkirim otomatis ke endpoint CMS Travelista (`/api/articles/receive`) dengan status `review`.
  - **Bulan ke-2 ke Depan (Fase Scale-Up Google Discover)**: Ditingkatkan menjadi **8 artikel harian (2 artikel per genre resmi)** dengan dua edisi penayangan: Edisi Pagi (09:00 WIB) dan Edisi Sore (16:30 WIB) untuk memicu Google Discover harian.
- **Eksekusi 100% Cloud Autonomous (GitHub Actions)**:
  - Menggunakan GitHub Actions dengan jadwal `cron: '0 2 * * *'` (02:00 UTC = **09:00 WIB** setiap hari secara otomatis).
  - Menggunakan Repository Secrets yang telah terkonfigurasi di GitHub (`DATABASE_URL`, `GEMINI_API_KEY`, `GROQ_API_KEY`, `COHERE_API_KEY`, `OPENROUTER_API_KEY`).
  - Menjalankan `python run_daily_job.py` yang memproduksi 4 artikel harian lengkap beserta foto sampul 16:9 WebP.

### Tahap 7: Automated 16:9 WebP Cover Image Pipeline & Legal Disclaimer (`src/automation/image_hunter.py`)
- **Standar Format Travelista 2026**: Rasio aspek **16:9 landscape** (`1200 x 675` px), format kompresi **WebP (< 400 KB)** untuk LCP performa tinggi, serta SEO `cover_image_alt`.
- **Kewajiban Cover Image Selalu Ada (*Mandatory Generation*)**: Setiap artikel wajib memiliki foto sampul visual. Sistem menjamin ketersediaan gambar melalui hierarki: foto dokumenter Wikimedia Commons $\rightarrow$ AI generatif fotorealistis FLUX $\rightarrow$ AI retry $\rightarrow$ fallback editorial placeholder.
- **Transparansi Disclaimer & Atribusi Hukum**:
  - Foto dokumenter nyata: *"Foto dokumentasi fotografi otentik via Wikimedia Commons (Lisensi Creative Commons / Public Domain) untuk tujuan informasi edukasi editorial."*
  - Gambar AI generatif: *"Ilustrasi visual editorial diproduksi dengan bantuan AI Generatif (16:9 WebP) dan telah diverifikasi bebas watermark serta fotorealistis oleh Agent Vision Reviewer."*
  - Disclaimer disematkan ke dalam metadata artikel dan dirender tepat di bawah gambar di antarmuka majalah.
- **Atribusi Penulis (Author Assignment)**:
  - Default author ditetapkan atas nama **Farrel** (`TRAVELISTA_AUTHOR_NAME="Farrel"`), menghubungkan kepemilikan artikel langsung ke profil penulis magang di CMS Travelista.

### Tahap 8: Agent Vision Reviewer & Visual Quality Loop (`src/automation/vision_reviewer.py`)
- **Peran & Fungsi**: Bertindak sebagai *Senior Photography Editor & Visual Fact-Checker* menggunakan Multimodal Vision AI (`gemini-3.5-flash`).
- **Pemeriksaan Ketat 4 Parameter**:
  1. `has_watermark`: Mendeteksi watermark AI, logo, font melayang, teks stok foto, atau stempel otomatis.
  2. `is_photorealistic`: Memastikan foto tampak seperti jepretan kamera profesional 35mm (bukan kartun, anime, lukisan digital, render 3D plastik, atau CGI).
  3. `is_culturally_accurate`: Memvalidasi orisinalitas objek, arsitektur, dan suasana agar sesuai dengan konteks budaya lokal Indonesia.
  4. `score` & `audit_notes`: Memberikan skor kelayakan terbit (1-100) dan catatan editorial transparan.
- **Loop Verifikasi & Fallback Otomatis**:
  - Jika kandidat gambar AI DITOLAK (karena ada watermark atau tampak kartun), sistem secara otomatis melakukan fallback ke foto dokumenter asli berlisensi bebas (Wikimedia Commons) atau melakukan retry dengan seed & prompt ekstra ketat.
  - Status audit disematkan ke dalam metadata `vision_audit` dan ditampilkan sebagai badge keamanan visual di Streamlit UI.

### Tahap 9: Hands-Free Monitoring & Editorial Dashboard Tracking
- **Zero Manual Writing**: Redaksi dan programmer tidak perlu menulis teks atau menekan tombol pengiriman.
- **Titik Pantau Terpusat**:
  1. **CMS Travelista (`/dashboard/articles`)**: Artikel otomatis masuk ke antrean **Review** dengan seluruh metadata, kategori, tags, foto sampul, dan TipTap AST siap pakai.
  2. **CMS Laporan (`/dashboard/report`)**: Memantau statistik performa tayang, agregasi views, dan tren kategori.
  3. **Streamlit UI (`app.py`)**: Berfungsi sebagai monitor diagnostik AI (metrik kuota token, evaluasi skor fact-checker, audit foto, dan log pengiriman).

---

## 4. Daftar File yang Dibuat / Diperbarui
- [x] `implementationplan.md` & `implementation_plan_travelista.md` (Dokumentasi Blueprint Otomasi Harian & Webhook)
- [x] `src/automation/__init__.py`
- [x] `src/automation/travelista_sender.py` (Klien HTTP POST Webhook ke CMS Travelista `/api/articles/receive`)
- [x] `src/automation/vision_reviewer.py` (Agent Vision Reviewer untuk inspeksi multimodal, deteksi watermark, dan evaluasi fotorealistis)
- [x] `src/automation/image_hunter.py` (Modul Hybrid Vision-RAG, anti-watermark prompt, konversi WebP 16:9, dan audit loop)
- [x] `src/automation/travelista_adapter.py` (Adapter TipTap AST JSON & Nuxt HTML kompatibel Monorepo 2026)
- [x] `src/automation/storage_supabase.py` (Manajemen tabel `daily_auto_articles` di Supabase)
- [x] `src/automation/trend_hunter.py` (Pencari tren Google Trends/News ID & perumus Genre/Topik/Judul)
- [x] `src/automation/model_router.py` (Pemilih otomatis Model Writer & Reviewer berbasis Genre & Kuota)
- [x] `src/automation/final_checker_agent.py` (Checker ke-2 untuk validasi Judul, Topik, Genre, Format CMS, & metadata visual)
- [x] `src/automation/daily_pipeline.py` (Orkestrator otomasi harian End-to-End dengan notifikasi Vision Reviewer)
- [x] `run_daily_job.py` (Script CLI eksekutor harian dengan dukungan `--auto-send` & `--no-send` untuk Cron 09:00 WIB)
- [x] `.github/workflows/daily_editorial.yml` (Konfigurasi GitHub Actions Cron Cloud Otomatis 09:00 WIB & Secret Envs)
- [x] `app.py` (Penambahan Pratinjau Cover Image 16:9 WebP, Badge Vision Reviewer, dan Tombol Dispatch CMS)

---

## 5. Konfigurasi GitHub Repository Secrets (Untuk Eksekusi Cloud 100% Mandiri)
Agar GitHub Actions dapat berjalan otomatis di cloud tanpa dependensi lokal, daftarkan secrets berikut di repositori GitHub (**Settings > Secrets and variables > Actions > New repository secret**):
- `DATABASE_URL`: URL PostgreSQL / Supabase untuk cache riwayat tren & deduplikasi topik.
- `GEMINI_API_KEY`: API Key Google Gemini (untuk Writer/Reviewer & Multimodal Vision Reviewer).
- `GROQ_API_KEY`: API Key Groq (untuk Model Router & Cross-Model Fact-Checker).
- `COHERE_API_KEY`: API Key Cohere (untuk artikel Sejarah & Misteri).
- `OPENROUTER_API_KEY`: (Opsional) Fallback provider model.
- `TRAVELISTA_CMS_URL`: URL publik CMS Travelista (misal: `https://travelista-2026-cms.vercel.app` atau domain produksi).
- `TRAVELISTA_CMS_API_KEY`: Secret Key yang cocok dengan `AUTO_ARTICLE_SECRET_KEY` di server CMS.
