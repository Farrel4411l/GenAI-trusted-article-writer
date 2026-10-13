# Rencana Implementasi: AI Editorial Multi-Agent RAG (Fokus: Travel, Kuliner, & Fakta Unik)

Tujuan: Membangun sistem AI otomatis yang mampu memproduksi artikel panjang (5-8 paragraf), berkualitas tinggi, akurat, dengan gaya bahasa *travel/lifestyle blog*, serta menyertakan **Sumber Asli (Citations)** di akhir artikel. Sistem ini dipastikan hanya menggunakan data yang legal untuk di-scrap (Creative Commons atau Public Domain).

---

## 1. Strategi Sumber Data (Legal & Etis)
Untuk menghindari pelanggaran hak cipta (*Copyright Infringement*), kita **tidak boleh** melakukan *scraping* sembarangan ke portal berita komersial tanpa izin. Sebagai gantinya, kita akan menggunakan sumber-sumber yang mengizinkan penggunaan ulang secara legal (Lisensi *Creative Commons / CC-BY-SA*):

*   **Wikivoyage Indonesia & Global:** Sumber utama untuk panduan perjalanan, tips *traveling*, daftar kuliner lokal, dan rute wisata. (Lisensi CC-BY-SA, 100% legal di-*scrap* dan digunakan ulang).
*   **Wikipedia (Kategori Spesifik):** Mengambil data spesifik tentang sejarah tempat (*Misteri*), geografi alam (*Fakta Unik*), dan makanan tradisional (*Food*). (Lisensi CC-BY-SA).
*   **Search Engine API (Tavily/SerpAPI):** (Opsional) Menggunakan API pencarian yang secara legal merangkum *snippet* dari internet dan memberikan URL sumber asli. Ini berguna untuk mendapatkan harga tiket, promo terbaru, atau berita wisata ter-update.

## 2. Pembaruan Arsitektur Database (Metadata Tracking)
Saat ini, database kita hanya menyimpan teks mentah (*chunks*). Agar AI bisa menuliskan sumber di akhir artikel, kita harus merekayasa ulang skrip **Ingestion (Pemasukan Data)**:
*   Setiap *chunk* teks yang masuk ke `pgvector` **wajib** disisipkan *metadata* yang berisi `Judul_Artikel` dan `URL_Sumber`.
*   Contoh Metadata: `{"title": "Candi Borobudur", "url": "https://id.wikipedia.org/wiki/Candi_Borobudur", "license": "CC-BY-SA"}`
*   Skrip `search.py` (Retriever) akan diubah agar tidak hanya mengembalikan teks, tetapi juga **Daftar URL** untuk dioper ke Agent Writer.

## 3. Strategi *Prompt Engineering* (Otak Jurnalistik)
*Prompt* lama akan dirombak total dan dibagi menjadi instruksi yang lebih mendetail agar menghasilkan 5-8 paragraf.

**Format Instruksi Agent Writer yang Baru:**
1.  **Peran:** Bertindak sebagai Jurnalis Travel dan Kuliner Senior (gaya bahasa *engaging*, inspiratif, informatif).
2.  **Struktur Wajib (5-8 Paragraf):**
    *   *Paragraf 1 (Hook):* Pembuka yang menarik perhatian pembaca (misal: "Pernahkah Anda membayangkan...").
    *   *Paragraf 2-6 (Body):* Fakta mendalam hasil sintesis dari dokumen sumber (Sejarah, keunikan, tips, kuliner khas).
    *   *Paragraf 7-8 (Conclusion/Tips):* Kesimpulan penutup atau tips praktis bagi pelancong.
3.  **Kewajiban Sitasi:** Setiap klaim unik (angka, fakta sejarah) harus berdasarkan dokumen konteks.
4.  **Format Sumber (Footer):** Di bagian paling bawah artikel, Agent WAJIB membuat bagian khusus:
    ```markdown
    ***
    **Sumber Referensi:**
    1. [Judul Artikel 1](URL Sumber 1)
    2. [Judul Artikel 2](URL Sumber 2)
    ```

## 4. Evolusi Alur LangGraph (Orkestrasi)
Untuk artikel panjang (5-8 paragraf), memaksa AI langsung menulis dari nol kadang membuat artikel terkesan "berputar-putar" atau mengulang kalimat. Kita akan sedikit memodifikasi *Graph* menjadi 3 tahap:
1.  **Agent Outline (Baru):** Menerima konteks dari database, lalu menyusun kerangka 5 paragraf (misal: P1 tentang sejarah, P2 tentang harga tiket, P3 tentang makanan khas).
2.  **Agent Writer:** Mengembangkan kerangka (*outline*) tersebut menjadi artikel panjang yang padu dan kaya narasi.
3.  **Agent Reviewer:** Bertugas sebagai *Fact-Checker* ketat. Ia mengecek: (a) Apakah artikel panjangnya 5-8 paragraf? (b) Apakah sumber dicantumkan di akhir? (c) Apakah ada klaim halusinasi?

## 5. Tahapan Eksekusi Berjalan (Execution Roadmap)
Jika Anda setuju dengan rencana ini, saya akan mengeksekusi dengan urutan berikut:

*   **Fase 1 (Data):** Menulis skrip ekstraksi data otomatis dari *Wikivoyage* (Kategori Wisata & Kuliner) menggunakan modul *Datasets* atau *Scraping* legal.
*   **Fase 2 (Database):** Memperbarui `ingestion.py` agar menangkap *URL Metadata* dan menanamkannya ke PostgreSQL.
*   **Fase 3 (Orkestrasi):** Merombak `writer_agent.py` dan `prompts.py` untuk mengaktifkan sistem Sitasi (Sumber) dan aturan 5-8 paragraf.
*   **Fase 4 (UI):** Meng-update Streamlit `app.py` agar menampilkan kotak khusus untuk daftar referensi dan membuat desain artikel terlihat seperti majalah digital travel (seperti Travelista).
