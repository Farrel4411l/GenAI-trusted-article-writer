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

### Tahap 6: Penjadwalan Bank Naskah H-1 (21:15 WIB) & Sistem Anti-Gagal 4-Artikel (`.github/workflows/daily_editorial.yml`, `run_daily_job.py`, `src/automation/travelista_sender.py`)

#### A. Rasionalisasi Strategis: Mengapa Bank Naskah H-1 (Pukul 21:15 WIB)?
Dalam sistem redaksi media digital profesional (seperti Detik, Kompas, dan IDN Times), proses produksi konten selalu dipersiapkan **satu malam sebelumnya (*Evening Staging / Bank Naskah H-1*)** dan tidak pernah diproduksi mendadak di pagi hari jam tayang.
1. **Disiplin Jadwal Redaksi (09:00 WIB Siap 100%)**:
   - Jika artikel diproduksi pada malam hari (pukul **21:15 WIB / 14:15 UTC**), proses riset AI, penulisan naskah, fact-checking, dan audit cover foto selesai sebelum tengah malam.
   - Saat tim redaksi masuk kerja pukul 08:30 WIB keesokan paginya, seluruh 4 artikel harian telah tersimpan rapi di dashboard dengan status `Review`.
   - Tepat pukul **09:00 WIB**, tim redaksi benar-benar **hanya perlu meninjau dan langsung menekan tombol Publish** tanpa risiko keterlambatan server.
2. **Eliminasi Delay Queue GitHub Actions (Menghindari Menit `:00`)**:
   - Server GitHub Actions gratis mengalami penumpukan antrean ribuan repositori di menit bulat `:00` (seperti `02:00 UTC` / 09:00 WIB) yang menyebabkan *delay* eksekusi hingga beberapa jam.
   - Dengan memindahkan jadwal ke **14:15 UTC (21:15 WIB)** menggunakan menit acak `:15`, server cloud GitHub langsung mengeksekusi pipeline tanpa hambatan antrean.
3. **Relevansi Google Trends Tetap 100% Akurat**:
   - 4 genre resmi Travelista (*Wisata*, *Kuliner*, *Sejarah*, *Budaya*) adalah konten **Lifestyle, Edukasi, dan Perjalanan**, BUKAN *breaking news* kilat yang basi dalam hitungan jam.
   - Siklus hidup tren (*trend shelf-life*) topik wisata dan kuliner bertahan berhari-hari hingga berminggu-minggu.
   - Tren yang ditarik pukul 21:00 malam merefleksikan akumulasi minat pencarian masyarakat Indonesia sepanjang hari, sehingga saat terbit keesokan paginya pukul 09:00 WIB (~11 jam kemudian), konten tersebut mendarat tepat pada siklus baca pagi audiens.

#### B. Arsitektur Anti-Gagal 4-Artikel Harian (100% Reliability Guarantee)
Untuk menjamin agar kuota 4 artikel harian selalu tercapai genap dan tidak ada genre yang tertinggal (mencegah insiden seperti kegagalan parsial 3 artikel), sistem menerapkan 4 lapis proteksi:
1. **Cooldown Jeda 15 Detik Antar-Genre**:
   Memberikan jeda istirahat 15 detik setelah setiap genre selesai diproduksi guna mencegah terbentur batasan *Rate Limit* (Requests-Per-Minute / RPM) pada kuota API Gemini dan Groq.
2. **Smart Retry Loop (3x Percobaan dengan Exponential Backoff)**:
   Setiap genre memiliki toleransi retry otomatis hingga 3 kali percobaan dengan jeda bertingkat (10 detik, 20 detik, 30 detik). Jika percobaan pertama terkena kendala jaringan atau batas kuota sesaat, sistem otomatis menunggu dan mencoba kembali tanpa menggugurkan proses.
3. **Fallback Topic Reservoir (`CURATED_EVERGREEN_POOL`)**:
   Jika pencarian kueri Google News atau server Wikimedia mengalami gangguan koneksi, sistem secara adaptif mengambil topik cadangan terverifikasi dari repositori budaya/wisata Nusantara yang kaya fakta di Wikipedia ID.
4. **Sweep Recovery Pass**:
   Di akhir perulangan utama, sistem memeriksa apakah ada genre yang belum selesai (`len(results) < 4`). Jika ada, sistem mengeksekusi putaran pemulihan khusus (*sweep pass*) untuk menuntaskan genre yang tertinggal hingga kuota 4 artikel terpenuhi sempurna.

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
