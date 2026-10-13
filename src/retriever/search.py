import os
from dotenv import load_dotenv
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_community.vectorstores import PGVector
from langchain_core.messages import HumanMessage, SystemMessage
from src.agents.prompts import GRADER_SYSTEM_PROMPT
from src.agents.llm_factory import get_llm
from typing import List, Tuple
import wikipedia
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

load_dotenv()
wikipedia.set_user_agent("TravelistaBot/1.0 (travelista@example.com)")
wikipedia.set_lang("id")

DATABASE_URL = os.getenv("DATABASE_URL")
COLLECTION_NAME = "wiki_travelista"

def get_retriever(k: int = 15):
    if not DATABASE_URL:
        raise ValueError("DATABASE_URL tidak disetel di .env")
        
    embeddings = HuggingFaceEmbeddings(
        model_name="sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
    )
    
    store = PGVector(
        collection_name=COLLECTION_NAME,
        connection_string=DATABASE_URL,
        embedding_function=embeddings,
    )
    
    return store.as_retriever(search_kwargs={"k": k})

def search_context(query: str, model_id: str, k: int = 15) -> Tuple[str, int]:
    """Mengembalikan konteks string dan jumlah token yang dipakai grader."""
    retriever = get_retriever(k=k)
    docs = retriever.invoke(query)
    
    grader_tokens = 0
    is_relevant = False
    
    if docs:
        print(f"\n[Agent Grader] Menilai relevansi {len(docs)} dokumen untuk topik '{query}'...")
        
        # Gabungkan teks untuk dinilai
        sample_context = "\n\n".join([doc.page_content for doc in docs[:3]])
        
        grader_model = get_llm(model_id)
        if hasattr(grader_model, "temperature"):
            grader_model.temperature = 0.0
            
        messages = [
            SystemMessage(content=GRADER_SYSTEM_PROMPT),
            HumanMessage(content=f"TOPIK: {query}\n\nKONTEKS:\n{sample_context}")
        ]
        
        try:
            response = grader_model.invoke(messages)
            
            # Hitung token grader
            if hasattr(response, "usage_metadata") and response.usage_metadata:
                grader_tokens = response.usage_metadata.get("total_tokens", 0)
            elif hasattr(response, "response_metadata") and "token_usage" in response.response_metadata:
                grader_tokens = response.response_metadata["token_usage"].get("total_tokens", 0)
            
            content = response.content
            if isinstance(content, list):
                draft_text = ""
                for item in content:
                    if isinstance(item, dict) and "text" in item:
                        draft_text += item["text"]
                    elif isinstance(item, str):
                        draft_text += item
                content = draft_text
            
            keputusan = content.strip().upper()
            if "TIDAK RELEVAN" in keputusan:
                is_relevant = False
                print(f"[Agent Grader] Keputusan: TIDAK RELEVAN (False Positive Ditemukan)")
            else:
                is_relevant = True
                print(f"[Agent Grader] Keputusan: RELEVAN")
                
        except Exception as e:
            print(f"[Agent Grader] Error saat menilai: {e}. Fallback ke asumsi relevan.")
            is_relevant = True
    else:
        is_relevant = False

    # Jika dinilai TIDAK RELEVAN atau kosong, panggil Wikipedia
    if not is_relevant:
        print(f"[Dynamic Fallback] Mencari langsung di Wikipedia untuk topik '{query}'...")
        docs = [] # Kosongkan docs awal
        try:
            search_results = wikipedia.search(query, results=1)
            if search_results:
                page_title = search_results[0]
                page = wikipedia.page(page_title, auto_suggest=False)
                
                new_doc = Document(
                    page_content=page.content,
                    metadata={"title": page.title, "url": page.url, "source": "wikipedia-fallback"}
                )
                
                text_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=150)
                chunks = text_splitter.split_documents([new_doc])
                
                print(f"[Dynamic Fallback] Menyimpan {len(chunks)} chunks dari '{page.title}' ke pgvector (Caching)...")
                store = PGVector(
                    collection_name=COLLECTION_NAME,
                    connection_string=DATABASE_URL,
                    embedding_function=HuggingFaceEmbeddings(model_name="sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2")
                )
                store.add_documents(chunks)
                
                docs = chunks[:k]
            else:
                print(f"[Dynamic Fallback] Tidak menemukan artikel Wikipedia untuk '{query}'.")
        except Exception as e:
            print(f"[Dynamic Fallback] Error Wikipedia API: {e}")

    # Format output
    formatted_contexts = []
    for i, doc in enumerate(docs):
        title = doc.metadata.get("title", "Tanpa Judul")
        url = doc.metadata.get("url", "#")
        content = doc.page_content.strip()
        formatted = f"[SUMBER {i+1} | {title} | {url}]\n{content}"
        formatted_contexts.append(formatted)
        
    return "\n\n".join(formatted_contexts), grader_tokens
