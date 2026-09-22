import os
from dotenv import load_dotenv
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from langchain_community.vectorstores import PGVector

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
COLLECTION_NAME = "tydiqa_id_knowledge"

def get_retriever(k: int = 3):
    """
    Menginisiasi koneksi ke pgvector dan mengembalikan objek retriever.
    
    Args:
        k (int): Jumlah dokumen konteks (chunks) yang ingin diambil.
    """
    if not DATABASE_URL:
        raise ValueError("DATABASE_URL tidak disetel di .env")
        
    embeddings = GoogleGenerativeAIEmbeddings(
        model="models/gemini-embedding-2",
        google_api_key=os.getenv("GEMINI_API_KEY")
    )
    
    store = PGVector(
        collection_name=COLLECTION_NAME,
        connection_string=DATABASE_URL,
        embedding_function=embeddings,
    )
    
    # Mengambil `k` dokumen paling relevan menggunakan vector similarity
    return store.as_retriever(search_kwargs={"k": k})

def search_context(query: str, k: int = 3):
    """
    Mencari dokumen berdasarkan query string.
    
    Returns:
        list of str: Kumpulan teks konteks yang relevan.
    """
    retriever = get_retriever(k=k)
    docs = retriever.invoke(query)
    
    contexts = [doc.page_content for doc in docs]
    return contexts

if __name__ == "__main__":
    # Script untuk tes cepat (Hanya akan berhasil jika database sudah terisi via ingestion.py)
    test_query = "Kapan berdirinya Bank Indonesia?"
    print(f"Mencari konteks untuk query: '{test_query}'\n")
    
    try:
        results = search_context(test_query)
        for i, res in enumerate(results, 1):
            print(f"--- Konteks {i} ---")
            print(res)
            print()
    except Exception as e:
        print(f"Gagal mencari konteks: {e}")
        print("Pastikan Docker berjalan dan Anda sudah menjalankan ingestion.py sebelumnya.")
