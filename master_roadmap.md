# Rencana Induk Induk (Master Roadmap): Multi-Agent RAG Editorial

Dokumen ini berfungsi sebagai "kompas" (Garis Besar) bagi sistem dan pengembang agar seluruh pekerjaan teknis tetap berpusat pada satu tujuan utama: **Membangun dan Menguji Coba Sistem Redaksi AI (Travelista) yang Mandiri, serta Mengevaluasi Kinerja Model Berbeda Berdasarkan Parameter Akademis yang Ketat.**

---

## FASE 1: Otomatisasi Pencarian Dinamis (Dynamic Retrieval)
**Tujuan:** Membebaskan AI dari ketergantungan data manual.
*   **Tugas 1.1:** Memodifikasi `search.py` agar jika `pgvector` mengembalikan hasil kosong (atau skor rendah), sistem otomatis melakukan *scraping* legal ke **Wikipedia API**.
*   **Tugas 1.2:** Teks yang didapat dari Wikipedia langsung disimpan ke `pgvector` (*Caching*) dan dikirimkan ke Agent Writer secara *real-time*.

## FASE 2: Integrasi Ekosistem Multi-Model (Plug-and-Play)
**Tujuan:** Menerapkan API Key (Groq, OpenRouter, Cohere) agar peran Writer dan Reviewer bisa ditukar-tukar untuk eksperimen penelitian.
*   **Tugas 2.1:** Memperbarui fungsi LLM di `writer_agent.py` dan `reviewer_agent.py` agar bisa menggunakan *Groq (Llama 3)*, *Cohere (Command-R)*, atau *OpenRouter*.
*   **Tugas 2.2:** Membangun antarmuka di Streamlit `app.py` berupa *Dropdown Selector* agar pengguna bisa memilih: "Model Writer: [Pilih]" dan "Model Reviewer: [Pilih]".

## FASE 3: Instrumentasi Metrik & Evaluasi (Sistem Log)
**Tujuan:** Membangun kode pengukur di belakang layar untuk merekam seluruh aktivitas agen sesuai metodologi penelitian.
*   **Tugas 3.1:** Menyisipkan *tracker* waktu di `orchestrator.py` untuk mengukur *Time to First Token (TTFT)* dan *Total Latency*.
*   **Tugas 3.2:** Menyisipkan penghitung Token (Prompt Tokens & Completion Tokens) yang diakses dari masing-masing API.
*   **Tugas 3.3:** Membuat fungsi pencatatan *Delta Skor* (Kualitas Draf 1 vs Draf Final) untuk metrik *Correction Efficacy*.

## FASE 4: Pengujian & Ekstraksi Data Jurnal (Eksperimen)
**Tujuan:** Menjalankan sistem dengan berbagai *prompt* pengujian dan menyimpan metriknya dalam format CSV/Excel untuk bahan paper Scopus.
*   **Tugas 4.1:** Melakukan *batch testing* otomatis untuk skenario baseline (Gemini vs Gemini), skenario cepat (Groq vs Groq), dan skenario khusus (Groq vs Cohere).
*   **Tugas 4.2:** Mengkalkulasi *Convergence Rate* dan *Faithfulness* menggunakan *framework* RAGAS.

## FASE 5: Visualisasi Akhir
**Tujuan:** Menampilkan hasil riset dengan indah.
*   **Tugas 5.1:** Menambahkan halaman "Dashboard Analitik" di Streamlit untuk menampilkan grafik performa dari eksperimen FASE 4.
