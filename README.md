# A Multi-Agent RAG Framework for Hallucination Mitigation and Source Verification in Indonesian Content Generation

**Tim Peneliti**: Muhammad Farrel Haidar & Tim

Proyek ini bertujuan membangun dan mengevaluasi arsitektur **Multi-Agent RAG** untuk mengurangi tingkat halusinasi dalam proses pembuatan artikel/konten berbahasa Indonesia menggunakan LLM. Fokus utama adalah pembuktian ilmiah untuk publikasi jurnal bereputasi (Scopus).

## 1. Arsitektur Sistem (RAG + Multi-Agent)
Sistem ini menggunakan orkestrasi 3 Agen AI:
1. **Agent 1 (Researcher)**: Mengambil data/konteks dari sumber kredibel (Vector Database PostgreSQL+pgvector, API Berita, Google Scholar).
2. **Agent 2 (Writer)**: Menulis draf berdasarkan konteks (Agent 1) dan Dynamic Policy.
3. **Agent 3 (Reviewer)**: Bertindak sebagai *Fact-Checker* untuk mengecek silang draf vs konteks asli. Mencegah halusinasi dan mengembalikan draf ke Writer jika ada klaim salah.

## 2. Metodologi Pengujian
### Ablation Study
Membandingkan sistem dalam beberapa skenario untuk mengukur signifikansi Agent Reviewer:
* **Sistem 0 (Baseline LLM)**: Zero-shot LLM tanpa RAG (Opsi tambahan untuk komparasi).
* **Sistem A (Baseline RAG)**: RAG + Agent Writer (Tanpa Reviewer).
* **Sistem B (Proposed)**: RAG + Agent Writer + Agent Reviewer.

### Evaluasi Kuantitatif (LLM-as-a-Judge)
1. **Evaluasi Konten (RAGAS - Faithfulness)**: Mengukur keselarasan klaim pada draf terhadap dokumen sumber. LLM Juri (misal GPT-4o) dipisah dari LLM Agen (misal Gemini 1.5 Pro).
2. **Evaluasi Agen Reviewer (Confusion Matrix)**: Uji injeksi halusinasi pada dataset. Mengukur Precision dan Recall dari Agent Reviewer dalam mendeteksi dan menolak draf salah.

## 3. Syarat Ketat Publikasi Scopus
* **Versi LLM Statis**: Menggunakan snapshot API (misal: `gemini-1.5-pro-002`, `gpt-4o-2024-05-13`) untuk reproduksibilitas.
* **Deterministic Generation**: Parameter `temperature=0.0` pada Juri dan Reviewer.
* **Transparansi Prompt**: Semua System Prompt dilampirkan.

## 4. Stack Teknologi
* **Orkestrasi**: Python, LangChain / LlamaIndex
* **Database**: PostgreSQL + pgvector
* **Evaluasi**: Ragas, Datasets, Pandas, Scikit-Learn
* **LLM**: Google Gemini / Anthropic Claude (Agents), OpenAI GPT-4o (Evaluator/Judge)
