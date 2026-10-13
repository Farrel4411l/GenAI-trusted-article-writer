import os
import wikipedia
import time
from dotenv import load_dotenv
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_community.vectorstores import PGVector
from langchain_core.documents import Document

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
COLLECTION_NAME = "wiki_travelista" # Menggunakan nama koleksi baru khusus Travel/Food

# Atur bahasa Wikipedia ke Indonesia
wikipedia.set_lang("id")

# Daftar topik pilihan (Travel, Kuliner, Unik, Misteri, Tips)
TOPICS = [
    "Candi Borobudur", "Danau Toba", "Raja Ampat", "Pulau Komodo", "Gunung Bromo",
    "Taman Nasional Ujung Kulon", "Kawah Ijen", "Bali", "Nusa Penida", "Tana Toraja",
    "Rendang", "Sate Padang", "Nasi Goreng", "Gudeg", "Pempek", "Soto Ayam", "Rawon",
    "Misteri Gunung Merapi", "Alas Purwo", "Lawang Sewu", "Benteng Vredeburg",
    "Pulau Bali", "Suku Baduy", "Tari Kecak", "Angklung", "Batik", "Wayang Kulit",
    "Candi Prambanan", "Pantai Kuta", "Kepulauan Seribu", "Taman Mini Indonesia Indah",
    "Masakan Padang", "Kopi Luwak", "Gado-gado", "Bakso", "Sate Lilit",
    "Tangkuban Parahu", "Gunung Rinjani", "Taman Nasional Tanjung Puting", "Wae Rebo"
]

def main():
    print("1. Mengunduh data spesifik Jurnalistik Travel, Kuliner, & Misteri (Wikipedia)...")
    documents = []
    
    for topic in TOPICS:
        try:
            print(f"Mencari data: {topic}...")
            # Ambil halaman wikipedia
            page = wikipedia.page(topic, auto_suggest=False)
            
            # Buat metadata dengan URL agar bisa dijadikan referensi/sitasi
            doc = Document(
                page_content=page.content,
                metadata={
                    "source": "wikipedia-id",
                    "title": page.title,
                    "url": page.url
                }
            )
            documents.append(doc)
            # Tidur sebentar agar tidak diblokir Wikipedia API
            time.sleep(0.5)
        except wikipedia.exceptions.DisambiguationError as e:
            print(f"  [!] Halaman ganda untuk {topic}, dilewati.")
        except wikipedia.exceptions.PageError:
            print(f"  [!] Halaman {topic} tidak ditemukan.")
        except Exception as e:
            print(f"  [!] Error pada {topic}: {e}")
            
    print(f"\nBerhasil memuat {len(documents)} artikel kurasi Travelista.")
        
    print("2. Memecah dokumen (Chunking)...")
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=1000,
        chunk_overlap=150
    )
    chunks = text_splitter.split_documents(documents)
    print(f"Total chunk yang dihasilkan: {len(chunks)} chunks.")
    
    print("3. Memuat Model Embedding Lokal...")
    embeddings = HuggingFaceEmbeddings(
        model_name="sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
    )
    
    print("4. Proses Penyimpanan ke PostgreSQL (pgvector)...")
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
        
        # VERIFIKASI
        count = len(db.similarity_search("tes", k=10))
        print(f"VERIFIKASI DATABASE: {count} dokumen berhasil ditarik sebagai tes.")
        
        print("Selesai! Database Travelista telah siap digunakan.")
    except Exception as e:
        print(f"Gagal menyimpan ke database: {e}")

if __name__ == "__main__":
    main()
