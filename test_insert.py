import os
from dotenv import load_dotenv
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_community.vectorstores import PGVector
from langchain_core.documents import Document

load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")

embeddings = HuggingFaceEmbeddings(model_name="sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2")
doc = Document(page_content="Ini adalah dokumen tes Rinjani.", metadata={"title": "Rinjani", "url": "http://tes"})

db = PGVector.from_documents(
    documents=[doc],
    embedding=embeddings,
    collection_name="wiki_travelista",
    connection_string=DATABASE_URL,
    pre_delete_collection=False
)
print("Doc inserted!")
print("Search:", db.similarity_search("Rinjani"))
