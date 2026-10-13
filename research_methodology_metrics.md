# Dokumentasi Metodologi & Metrik Penelitian: Evaluasi Multi-Agent RAG

Dokumen ini mendefinisikan pilar-pilar metrik pengukuran akademis yang akan digunakan dalam penelitian "Role Specialization (Writer vs Reviewer) dalam Arsitektur Multi-Agent RAG". Standar ini mengacu pada RAGAS framework dan metrik sistem terapan.

---

## PILAR 1: Retrieval Metrics (Evaluasi pgvector & Wikipedia Fallback)
Pilar ini mengukur apakah mesin pencari berhasil memberikan "bahan baku" yang berkualitas kepada Agent Writer, mencegah fenomena *Garbage In, Garbage Out*.

1. **Context Precision (Presisi Konteks):** 
   - **Definisi:** Mengukur rasio informasi yang relevan di dalam teks yang ditarik dari Wikipedia/pgvector dibandingkan dengan total teks yang ditarik. 
   - **Tujuan:** Mengetahui apakah sistem menarik terlalu banyak teks sampah (*noise*) yang dapat membingungkan agen.
2. **Context Recall (Perolehan Konteks):** 
   - **Definisi:** Mengukur apakah teks yang ditarik sudah mencakup *semua* informasi yang dibutuhkan Writer untuk menjawab instruksi pengguna.
   - **Tujuan:** Menghindari halusinasi paksa akibat informasi sumber yang "bolong".
3. **Hit Rate / Mean Reciprocal Rank (MRR):**
   - **Definisi:** Seberapa akurat sistem (pgvector) menempatkan dokumen yang paling relevan pada urutan (rank) pertama dari hasil pencarian.

---

## PILAR 2: Generation & Agentic Metrics (Evaluasi Kolaborasi)
Pilar ini mengevaluasi mekanika debat antara Agent Writer (Kreator) dan Agent Reviewer (Editor/Hakim), serta kualitas teks akhirnya (Menggantikan istilah "Halusinasi" yang terlalu umum).

1. **Faithfulness (Kesetiaan pada Konteks):**
   - **Definisi:** Memastikan tidak ada satu pun klaim, entitas, atau angka di dalam artikel akhir yang tidak dapat dibuktikan atau dilacak balik ke teks sumber (Wikipedia/Konteks).
2. **Answer Relevance (Relevansi Jawaban):**
   - **Definisi:** Mengukur apakah artikel akhir benar-benar menjawab *prompt* spesifik dari pengguna secara akurat (tidak sekadar memuntahkan fakta Wikipedia yang tidak relevan).
3. **Convergence Rate (Tingkat Konvergensi):**
   - **Definisi:** Persentase keberhasilan sistem mencapai kesepakatan (Reviewer memberi status "LULUS") sebelum menyentuh batas maksimal iterasi (misal: `max_retries = 3`).
   - **Contoh:** Jika dari 100 tugas ada 20 yang berakhir "gagal/stuck", tingkat konvergensinya 80%.
4. **Correction Efficacy (Efikasi Koreksi):**
   - **Definisi:** Selisih (Delta) skor kualitas *Faithfulness/Relevance* antara Draf 1 dan Draf Final. 
   - **Tujuan:** Mengukur apakah masukan/revisi dari Reviewer benar-benar menghasilkan tulisan yang lebih baik, atau malah memperburuk iterasi.

---

## PILAR 3: System & Efficiency Metrics (Performa & Biaya)
Pilar ini sangat penting untuk kelayakan *deployment* ke dunia nyata (Production-readiness).

1. **Total Token Consumption per Task:**
   - **Definisi:** Total token yang dihabiskan dalam seluruh putaran debat (Prompt Tokens + Completion Tokens) hingga artikel berstatus Lulus.
   - **Tujuan:** Mengukur pembengkakan biaya (eksponensial token) yang rentan terjadi pada arsitektur Multi-Agent.
2. **Time to First Token (TTFT):**
   - **Definisi:** Waktu (dalam detik/milidetik) yang dihitung sejak *prompt* pengguna ditekan hingga sistem selesai melakukan *hybrid search* (pgvector/Wikipedia) dan mulai merangkai kata pertama di layar.
3. **Total Latency:**
   - **Definisi:** Waktu total yang dihabiskan sistem sejak *prompt* ditekan hingga keseluruhan iterasi Reviewer selesai dan memberikan artikel final.
