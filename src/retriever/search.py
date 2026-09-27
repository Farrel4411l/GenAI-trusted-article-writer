import os
from dotenv import load_dotenv
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_community.vectorstores import PGVector
from typing import List

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
COLLECTION_NAME = "wiki_id_massive"

def get_retriever(k: int = 3):
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

def search_context(query: str, k: int = 15) -> List[str]:
    retriever = get_retriever(k=k)
    docs = retriever.invoke(query)
    
    contexts = [doc.page_content for doc in docs]
    return contexts
