import os
import pandas as pd
from datasets import load_dataset
from dotenv import load_dotenv
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_community.vectorstores import PGVector
from langchain_core.documents import Document

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
COLLECTION_NAME = "wiki_id_massive"

def main():
    print("1. Mengunduh dataset Pengetahuan Umum (Wikipedia Indonesia)...")
    try:
        dataset = load_dataset("wikimedia/wikipedia", "20231101.id", split="train", streaming=True)
    except Exception as e:
        print(f"Gagal mengunduh dataset: {e}")
        return
        
    print("Mengambil 3000 artikel Wikipedia untuk memperluas cakupan topik AI secara masif...")
    
    documents = []
    # Mengambil 3000 artikel (karena kita pakai model lokal, bebas rate limit!)
    for i, row in enumerate(dataset):
        if i >= 3000:
            break
            
        text = row['text']
        title = row['title']
        if pd.isna(text) or len(text.strip()) == 0:
            continue
        
        doc = Document(
            page_content=text,
            metadata={"source": "wikipedia-id", "title": title}
        )
        documents.append(doc)
        
    print(f"Berhasil memuat {len(documents)} dokumen Wikipedia berbahasa Indonesia.")
        
    print("2. Memecah dokumen (Chunking)...")
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=1000,
        chunk_overlap=150
    )
    chunks = text_splitter.split_documents(documents)
    print(f"Total chunk yang dihasilkan: {len(chunks)} chunks.")
    
    print("3. Memuat Model Embedding Lokal (Bebas Kuota/Limit)...")
    embeddings = HuggingFaceEmbeddings(
        model_name="sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
    )
    
    print("4. Proses Penyimpanan ke PostgreSQL (pgvector)... Ini mungkin memakan waktu beberapa menit.")
    if not DATABASE_URL:
        print("ERROR: DATABASE_URL tidak ditemukan di .env")
        return
    
    try:
        db = PGVector.from_documents(
            embedding=embeddings,
            documents=chunks,
            collection_name=COLLECTION_NAME,
            connection_string=DATABASE_URL,
            pre_delete_collection=True 
        )
        print("Selesai! Database raksasa telah siap digunakan.")
    except Exception as e:
        print(f"Gagal menyimpan ke database: {e}")

if __name__ == "__main__":
    main()
