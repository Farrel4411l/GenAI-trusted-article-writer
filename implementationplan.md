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

---

## 6. Rencana Pengembangan Lanjutan (Usulan Upgrade Diskusi Mentor): *Search-Intent Trend Intelligence & Non-Destructive SEO Packaging*

Bagian ini disusun berdasarkan hasil riset silang antara repositori AI (`cobapenelitianpart3`) dan monorepo produksi **Travelista 2026** (`apps/magazine`, `apps/cms`, serta skema database `001_initial_schema.sql` dan `seed.sql`). Tujuannya adalah meningkatkan kapabilitas **Analisis Tren** dan **On-Page SEO** agar Travelista mampu mendominasi halaman pertama Google (*Top-of-Mind Travel Portal*) **tanpa melanggar prinsip *Zero-Touch Core Architecture* dan aturan ketat Anti-Halusinasi RAG**.

### 6.1. Hasil Audit Keselarasan Visi & Infrastruktur Eksisting Travelista 2026
Dari penelusuran kode pada monorepo `travelista-2026`, ditemukan bahwa:
1. **Identitas & Positioning Resmi (`001_initial_schema.sql` & `seed.sql`)**:
   - Tagline resmi: *"Jelajahi Nusantara Bersamamu — Portal berita perjalanan dan wisata terbaik Indonesia."*
   - Travelista adalah **Majalah Jurnalistik Perjalanan, Budaya, & Kuliner (*Editorial Travel Magazine*)**, bukan katalog *listing* harga seperti OTA (*Online Travel Agent*), namun memiliki ekosistem pendukung berupa portal `apps/tiketing` (Tiket Kapal & Paket Wisata).
   - Taksonomi tag resmi di database (`seed.sql`) sudah dirancang untuk menangkap **Wilayah** (`Bali`, `Yogyakarta`, `Labuan Bajo`, `Raja Ampat`, dll.) dan **Gaya/Niat Perjalanan (*Travel Mood/Intent*)** (`Wisata Alam`, `Wisata Budaya`, `Wisata Kuliner`, `Backpacker`, `Luxury Travel`, `Family Travel`, `Solo Travel`, `Weekend Getaway`).
2. **Kapabilitas SEO Bawaan di Frontend Nuxt 4 (`apps/magazine`)**:
   - Halaman baca artikel (`[year]/[month]/[day]/[slug].vue`) **sudah memiliki**:
     - `NewsArticle` & `BreadcrumbList` JSON-LD otomatis.
     - `SpeakableSpecification` (Google Assistant / AI Overview ready) yang menargetkan selector `['h1', '.article-excerpt', '.article-content p:first-child']`.
     - Pemisahan antara `article.title` (judul editorial di halaman) dan `article.meta_title` (judul SEO di `<title>` browser & SERP Google), serta pemisahan antara `article.excerpt` (lead ringkasan di bawah judul) dan `article.meta_description`.
     - Mesin rekomendasi **Artikel Terkait (`fetchRelatedArticles` di `useArticles.ts`)** berbasis rumus skor tertimbang:
       $$\text{Score} = (\text{Shared Tags} \times 2) + (\text{Same Category} \times 3) + \text{Recency Boost}$$
     - Indeks pencarian teks penuh Bahasa Indonesia (`idx_articles_fts` menggunakan `to_tsvector('indonesian', title || excerpt)`).

### 6.2. Batasan Kritis: Apa yang TIDAK BOLEH Dilakukan (Menjaga Kemurnian Riset & Anti-Halusinasi)
Agar peningkatan SEO **tidak membawa perubahan destruktif** yang merusak eksperimen ilmiah maupun kredibilitas jurnalistik Travelista, 3 hal berikut **DILARANG** dilakukan:
1. **Dilarang Memaksa AI Menulis Harga Tiket, Jam Operasional, atau Angka Budget Tanpa Sumber RAG**:
   - Basis pengetahuan RAG kita bersumber dari Wikipedia Indonesia & Wikivoyage (`pgvector`) yang bersifat ensiklopedis dan historis/geografis, bukan database tarif komersial harian.
   - Memaksa `Writer Agent` menulis harga tiket atau itinerary biaya akan memicu halusinasi dan menyebabkan draf **ditolak oleh Checker 1 (`reviewer_agent.py`)**.
2. **Dilarang Mengubah Prompt Inti 5–8 Paragraf pada `src/agents/prompts.py`**:
   - Mesin inti (`writer_agent.py`, `reviewer_agent.py`, `orchestrator.py`) harus tetap murni menghasilkan 5–8 paragraf naratif terverifikasi agar metrik riset (`experiment_metrics.csv`) tetap konsisten.
3. **Dilarang Mengubah Skema Tabel Database Produksi (`001_initial_schema.sql`)**:
   - Seluruh peningkatan SEO harus memanfaatkan kolom yang sudah tersedia di tabel `public.articles` (`title`, `meta_title`, `excerpt`, `meta_description`, `content_html`, `content_json`, dan `tags`).

### 6.3. Empat (4) Peningkatan Strategis yang Sejalan 100% dengan Travelista (Non-Destructive Upgrades)

Seluruh peningkatan ditempatkan secara terisolasi di dalam folder `src/automation/` (Tahap Pra-Penulisan di `trend_hunter.py` dan Tahap Pasca-Verifikasi di `final_checker_agent.py` & `travelista_adapter.py`):

#### Upgrade A: *Search-Intent & Google Autocomplete Enrichment* (`src/automation/trend_hunter.py`)
Mengubah analisis tren dari sekadar "pembaca berita pasif" menjadi **mesin pemetaan niat pencarian wisata (*Travel Search Intent*)**:
1. **Filter Relevansi Wisata & Gaya Hidup (*Editorial Travel Filter*)**:
   - Menyaring berita birokrasi/politik murni dari RSS Google News agar topik yang terpilih selalu memiliki sudut pandang **daya tarik destinasi, pengalaman liburan (*healing/eksplorasi*), keunikan budaya, atau kelezatan kuliner**.
2. **Integrasi *Google Search Autocomplete Indonesia* (Tanpa API Key Berbayar)**:
   - Saat sebuah kandidat topik/entitas ditemukan (misal: `"Desa Wisata Nglanggeran"` atau `"Danau Toba"`), sistem memanggil endpoint publik `suggestqueries.google.com` (`hl=id&gl=ID`) untuk memanen **kata kunci pencarian nyata (*long-tail keywords*)** yang diketik masyarakat Indonesia.
3. **Kesadaran Musim & Kalender Liburan (*Seasonal Context*)**:
   - Menambahkan konteks waktu (misal: *akhir pekan / weekend getaway*, *musim liburan*, atau *suasana healing alam*) ke dalam `editorial_angle` tanpa melanggar fakta dokumen sumber.

#### Upgrade B: *Dual-Title Strategy (`title` vs `meta_title`) & Speakable `excerpt`* (`src/automation/final_checker_agent.py` & `travelista_adapter.py`)
Memaksimalkan fitur yang sudah ada di Nuxt 4 `apps/magazine` namun belum diisi secara terpisah oleh bot AI:
1. **`final_title` (Judul Editorial Majalah)**: Tetap bergaya jurnalistik majalah perjalanan yang elegan dan inspiratif.
2. **`meta_title` (Judul SERP Google $\le 60$ Karakter)**: Dioptimasi khusus dengan *Primary Keyword* di bagian depan agar menonjol di halaman 1 Google (contoh: *"Wisata Desa Nglanggeran Gunungkidul: Daya Tarik & Sejarah"*).
3. **`excerpt` (Ringkasan *Speakable* & Indeks FTS)**: Membuat 1–2 kalimat ringkasan padat yang menjawab langsung inti topik (*Direct Answer*). Di web Travelista, `excerpt` ini dirender dengan garis aksen kuning (*saffron*), diindeks oleh PostgreSQL *Full-Text Search*, dan ditargetkan oleh `SpeakableSpecification` untuk *Google AI Overviews*.
4. **`meta_description` (120–155 Karakter)**: Dirancang khusus dengan *call-to-action* halus untuk meningkatkan rasio klik (*Click-Through Rate* / CTR) dari mesin pencari.

#### Upgrade C: *Smart Taxonomy Tagging* untuk Mengaktifkan *Topic Cluster* (`src/automation/final_checker_agent.py`)
Menyelaraskan pembuatan tag dengan algoritma `fetchRelatedArticles` di `apps/magazine/app/composables/useArticles.ts`:
- Alih-alih membuat 5 tag acak yang selalu berbeda tiap hari, `Checker 2` diinstruksikan memilih kombinasi **5 Tag Terstandarisasi**:
  1. **1–2 Tag Lokasi/Destinasi Induk** (contoh: `Yogyakarta`, `Bali`, `Lombok`, `Sumatera Barat`, `Jawa Timur`).
  2. **1–2 Tag Niat/Gaya Perjalanan Standar Travelista** (contoh: `Wisata Alam`, `Wisata Budaya`, `Wisata Kuliner`, `Weekend Getaway`, `Family Travel`, `Solo Travel`).
  3. **1–2 Tag Entitas Spesifik Artikel**.
- **Dampak Langsung**: Artikel lintas-genre yang membahas wilayah atau suasana serupa akan otomatis saling terhubung di widget **"Artikel Terkait"** pada web Travelista (memperkuat *Topical Authority* di mata Googlebot).

#### Upgrade D: *Post-Verification Subheadings (`H2`) & Automated Internal Linking* (`src/automation/final_checker_agent.py`)
Dilakukan **SETELAH** draf lulus dari `Checker 1 (Fact-Checker)` sehingga tidak mengganggu validasi 5–8 paragraf di mesin inti:
1. **Penyisipan Sub-Judul Kontekstual (`## H2`)**:
   - Mengelompokkan 5–8 paragraf yang sudah terverifikasi menjadi 2–3 sub-bagian ber-heading `## (H2)` yang memuat kata kunci turunan, sehingga artikel mudah dipindai (*scannable*) oleh pembaca maupun *crawler* Google.
2. **Injeksi *Internal Link ("Baca Juga")* Otomatis dari Database Supabase**:
   - Mengecek arsip artikel yang sudah tersimpan di Supabase untuk kategori atau wilayah yang berkaitan, lalu menyisipkan tautan internal kontekstual guna mencegah halaman terisolasi (*orphan pages*).
3. **Rincian Skor SEO di Checker 2**:
   - Memperkaya `final_check_notes` dengan indikator kepatuhan SEO (*Keyword di Judul/Meta*, *Panjang Meta Ideal*, *Struktur H2*, dan *Kelengkapan Sitasi*).

### 6.4. Matriks Perbandingan Dampak (Sebelum vs Sesudah Upgrade)

| Komponen | Kondisi Saat Ini | Setelah Upgrade (Usulan Fase 2) | Dampak terhadap Mesin Inti RAG |
| :--- | :--- | :--- | :--- |
| **Pemilihan Tren** | Hanya RSS berita umum (sering bias berita seremonial/birokrasi) | RSS Berita + **Google Autocomplete Suggest ID** + Filter *Travel/Healing Intent* | **0% Perubahan** pada `search.py` / `orchestrator.py` |
| **Judul & Meta** | `meta_title` & `excerpt` disamakan dengan `title` & `meta_description` | Dipisah khusus: `title` (Jurnalistik), `meta_title` (SERP $\le 60$ kar), `excerpt` (*Speakable* AI), `meta_description` (CTR) | **0% Perubahan** pada database schema (kolom sudah tersedia di CMS) |
| **Struktur Baca** | 5–8 paragraf polos tanpa sub-judul | 5–8 paragraf terverifikasi + **2–3 Sub-judul `H2`** & tautan **"Baca Juga"** pasca-verifikasi | **0% Perubahan** pada aturan `writer_agent.py` & `reviewer_agent.py` |
| **Koneksi Antar-Artikel** | Tag acak per artikel (skor *Related Articles* rendah) | **Standarisasi Tag Wilayah & Mood** sesuai `seed.sql` Travelista | Mengaktifkan *Topic Cluster* otomatis di frontend Nuxt 4 |

