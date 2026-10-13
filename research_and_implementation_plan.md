# Rencana Implementasi Teknis: Pencarian Dinamis & Multi-Model Integrations

Dokumen ini adalah rencana implementasi **kode teknis** yang difokuskan pada penggabungan model AI berbeda dan modifikasi alat pencari, sejalan dengan roadmap dan metrik akademis baru (Lihat `master_roadmap.md` dan `research_methodology_metrics.md`).

## 1. Modifikasi Modul `search.py` (Pencarian Dinamis & Legal)
Saat ini, `search_context()` hanya mencari di pgvector.
**Rencana Kode Baru:**
1. Jika hasil query dari `pgvector` memberikan jumlah teks yang sangat pendek atau *similarity score* rendah.
2. Panggil *library* `wikipedia` (Python API).
3. Unduh halaman Wikipedia berdasarkan *keyword* topik.
4. Lakukan *chunking* otomatis di memori, dan langsung tambahkan ke PostgreSQL (`wiki_travelista`) agar tidak perlu diunduh ulang di masa depan.
5. Kembalikan gabungan konteks (Lokal + Wikipedia Baru) yang sudah diformat dengan URL aslinya ke Agen.

## 2. Pemasangan Multi-Model API (Groq, OpenRouter, Cohere)
Sistem variabel lingkungan (`.env`) telah diperbarui dengan kunci API.
**Rencana Kode Baru di Agen:**
1. Modifikasi `writer_agent.py` dan `reviewer_agent.py` agar tidak hanya terpaku pada `ChatGoogleGenerativeAI`.
2. Buat fungsi *LLM Factory/Router* di mana sistem bisa memilih *backend*:
   - `langchain-groq` untuk menggunakan `ChatGroq` (Llama-3-8b/70b).
   - `langchain-cohere` untuk menggunakan `ChatCohere` (Command-R).
   - `ChatOpenAI` dengan konfigurasi *Base URL* untuk OpenRouter (Model gratis/open-source).
3. Terapkan logika pemilihan model ini ke UI Streamlit agar pengguna/peneliti bisa melakukan A/B Testing dengan satu klik.

## 3. Instrumentasi Kode Pengukur Metrik (Logging)
Demi memenuhi kebutuhan metrik di `research_methodology_metrics.md`, struktur *AgentState* di `orchestrator.py` akan ditambah:
- `tokens_used`: Menyimpan array penggunaan token tiap iterasi.
- `start_time` & `end_time`: Untuk mengalkulasi TTFT dan Total Latency.
- File log terpisah (`metrics_log.csv`) yang akan di-append otomatis setelah grafik (Graph) selesai tereksekusi.
