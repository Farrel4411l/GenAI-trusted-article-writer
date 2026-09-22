import os
import pandas as pd
from datasets import load_dataset
from dotenv import load_dotenv
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from langchain_community.vectorstores import PGVector
from langchain_core.documents import Document

load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
DATABASE_URL = os.getenv("DATABASE_URL")
COLLECTION_NAME = "tydiqa_id_knowledge"

def main():
    print("1. Mengunduh dataset Pengetahuan Umum (Wikipedia Indonesia)...")
    # Menggunakan Wikipedia versi bahasa Indonesia agar kompatibel dengan versi datasets terbaru
    # Mode streaming=True agar tidak perlu mengunduh data puluhan GB, cukup ambil bagian awalnya saja.
    try:
        dataset = load_dataset("wikimedia/wikipedia", "20231101.id", split="train", streaming=True)
    except Exception as e:
        print(f"Gagal mengunduh dataset: {e}")
        return
        
    print("Mengambil 5 artikel pertama dari Wikipedia untuk pengetahuan dasar...")
    
    documents = []
    # Mengambil hanya 5 artikel pertama (Prototype agar terhindar dari batas gratis 100 request/menit Gemini)
    for i, row in enumerate(dataset):
        if i >= 5:
            break
            
        text = row['text']
        title = row['title']
        if pd.isna(text) or len(text.strip()) == 0:
            continue
        
        doc = Document(
            page_content=text,
            metadata={"source": "wikipedia-id", "title": title, "language": "id"}
        )
        documents.append(doc)
        
    print(f"Berhasil memuat {len(documents)} dokumen Wikipedia berbahasa Indonesia.")
        
    print("2. Memecah dokumen (Chunking)...")
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=1000,
        chunk_overlap=150, # Sedikit irisan agar konteks kalimat tidak terputus
        separators=["\n\n", "\n", ".", " ", ""]
    )
    chunks = text_splitter.split_documents(documents)
    print(f"Total chunk yang dihasilkan: {len(chunks)} chunks.")
    
    print("3. Proses Embedding dan Penyimpanan ke PostgreSQL (pgvector)...")
    if not DATABASE_URL:
        print("ERROR: DATABASE_URL tidak ditemukan di .env")
        return
        
    embeddings = GoogleGenerativeAIEmbeddings(
        model="models/gemini-embedding-2",
        google_api_key=os.getenv("GEMINI_API_KEY")
    )
    
    try:
        # Hapus data lama jika ada, agar tidak duplikat saat dijalankan ulang
        db = PGVector.from_documents(
            embedding=embeddings,
            documents=chunks,
            collection_name=COLLECTION_NAME,
            connection_string=DATABASE_URL,
            pre_delete_collection=True 
        )
        print("Selesai! Database pengetahuan umum telah siap digunakan.")
    except Exception as e:
        print(f"Gagal menyimpan ke database (Pastikan Docker PostgreSQL sudah berjalan): {e}")

if __name__ == "__main__":
    main()
