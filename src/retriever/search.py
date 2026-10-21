import os
import re
from collections import OrderedDict
from dotenv import load_dotenv
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_community.vectorstores import PGVector
from langchain_core.messages import HumanMessage, SystemMessage
from src.agents.prompts import GRADER_SYSTEM_PROMPT
from src.agents.llm_factory import get_llm
from typing import List, Tuple, Dict
import wikipedia
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

load_dotenv()
wikipedia.set_user_agent("TravelistaBot/1.0 (travelista@example.com)")
wikipedia.set_lang("id")

DATABASE_URL = os.getenv("DATABASE_URL")
if DATABASE_URL and DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+psycopg2://", 1)

COLLECTION_NAME = "wiki_travelista"
MIN_UNIQUE_SOURCES = 3

_embeddings_instance = None

def get_embeddings():
    global _embeddings_instance
    if _embeddings_instance is None:
        try:
            import torch
            torch.set_num_threads(1)
        except Exception:
            pass
        _embeddings_instance = HuggingFaceEmbeddings(
            model_name="sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
            model_kwargs={"device": "cpu"}
        )
    return _embeddings_instance

def get_vectorstore() -> PGVector:
    if not DATABASE_URL:
        raise ValueError("DATABASE_URL tidak disetel di .env")
    return PGVector(
        collection_name=COLLECTION_NAME,
        connection_string=DATABASE_URL,
        embedding_function=get_embeddings(),
    )

def get_retriever(k: int = 15):
    store = get_vectorstore()
    return store.as_retriever(search_kwargs={"k": k})

def extract_subqueries(query: str) -> List[str]:
    """
    Memecah topik majemuk (misal: 'bali dan palembang') menjadi sub-topik individual
    agar pencarian mencakup seluruh entitas dan menghasilkan referensi yang bervariasi.
    """
    cleaned = query.strip()
    parts = re.split(r'\b(?:dan|serta|atau|vs|versus|dengan)\b|[,&/+]', cleaned, flags=re.IGNORECASE)
    subqueries = []
    for p in parts:
        p_clean = p.strip()
        if len(p_clean) >= 3 and p_clean.lower() not in [s.lower() for s in subqueries]:
            subqueries.append(p_clean)
    if not subqueries:
        subqueries = [cleaned]
    return subqueries

def group_docs_by_source(docs: List[Document]) -> OrderedDict[str, List[Document]]:
    """Mengelompokkan chunk berdasarkan judul artikel unik."""
    grouped: OrderedDict[str, List[Document]] = OrderedDict()
    for doc in docs:
        title = doc.metadata.get("title", "Tanpa Judul")
        if title not in grouped:
            grouped[title] = []
        # Hindari duplikasi chunk identik
        if all(existing.page_content != doc.page_content for existing in grouped[title]):
            grouped[title].append(doc)
    return grouped

def has_strong_match(grouped_sources: Dict[str, List[Document]], term: str) -> bool:
    """Mengecek apakah suatu sub-topik sudah memiliki artikel yang benar-benar membahasnya."""
    term_lower = term.lower()
    term_words = [w for w in term_lower.split() if len(w) >= 3]
    if not term_words:
        term_words = [term_lower]

    for title, chunks in grouped_sources.items():
        title_lower = title.lower()
        if any(w in title_lower for w in term_words):
            return True
        combined_text = " ".join(c.page_content.lower() for c in chunks[:3])
        # Harus muncul minimal 2 kali di isi jika tidak ada di judul (mencegah passing mention)
        if all(combined_text.count(w) >= 2 for w in term_words):
            return True
    return False

def fetch_wikipedia_multi(search_terms: List[str], existing_titles: set, max_new_pages: int = 3) -> List[Document]:
    """
    Mencari dan mengunduh beberapa artikel Wikipedia berbeda secara round-robin
    dari daftar search_terms untuk menjamin variasi sumber referensi.
    """
    candidate_titles = []
    search_Lists = []

    for term in search_terms:
        try:
            results = wikipedia.search(term, results=4)
            if results:
                search_Lists.append(results)
        except Exception as e:
            print(f"[Dynamic Fallback] Error saat mencari '{term}' di Wikipedia: {e}")

    # Interleave hasil pencarian dari tiap term
    max_len = max((len(lst) for lst in search_Lists), default=0)
    for i in range(max_len):
        for lst in search_Lists:
            if i < len(lst):
                t = lst[i]
                if t not in candidate_titles and t.lower() not in {et.lower() for et in existing_titles}:
                    candidate_titles.append(t)

    new_chunks: List[Document] = []
    fetched_pages = 0
    text_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=150)

    for page_title in candidate_titles:
        if fetched_pages >= max_new_pages:
            break
        try:
            page = wikipedia.page(page_title, auto_suggest=False)
        except wikipedia.exceptions.DisambiguationError as e:
            if e.options:
                try:
                    page = wikipedia.page(e.options[0], auto_suggest=False)
                except Exception:
                    continue
            else:
                continue
        except Exception:
            continue

        if page.title.lower() in {et.lower() for et in existing_titles}:
            continue

        new_doc = Document(
            page_content=page.content,
            metadata={"title": page.title, "url": page.url, "source": "wikipedia-fallback"}
        )
        chunks = text_splitter.split_documents([new_doc])
        if chunks:
            print(f"[Dynamic Fallback] Menyimpan {len(chunks)} chunks dari '{page.title}' ke pgvector...")
            try:
                store = get_vectorstore()
                store.add_documents(chunks)
            except Exception as e:
                print(f"[Dynamic Fallback] Gagal caching ke pgvector: {e}")

            new_chunks.extend(chunks)
            existing_titles.add(page.title)
            fetched_pages += 1

    return new_chunks

def grade_candidate_sources(
    query: str,
    grouped_sources: OrderedDict[str, List[Document]],
    model_id: str
) -> Tuple[OrderedDict[str, List[Document]], int]:
    """
    Menilai setiap sumber artikel unik menggunakan Agent Grader dalam 1 panggilan hemat token.
    Mengembalikan sumber yang dinyatakan RELEVAN beserta jumlah token yang terpakai.
    """
    if not grouped_sources:
        return OrderedDict(), 0

    source_items = list(grouped_sources.items())[:8]
    summary_lines = []
    query_words = [w.lower() for w in extract_subqueries(query) for w in w.split() if len(w) >= 3]

    for idx, (title, chunks) in enumerate(source_items, start=1):
        # Pilih chunk yang paling banyak mengandung kata kunci topik untuk diinspeksi Grader
        best_chunk = chunks[0]
        best_score = -1
        for ch in chunks:
            txt_low = ch.page_content.lower()
            score = sum(txt_low.count(w) for w in query_words)
            if score > best_score:
                best_score = score
                best_chunk = ch
        snippet = best_chunk.page_content.strip().replace("\n", " ")[:450]
        summary_lines.append(f"[{idx}] Judul: {title}\nCuplikan: {snippet}")

    candidates_text = "\n\n".join(summary_lines)
    print(f"\n[Agent Grader] Menilai relevansi {len(source_items)} sumber artikel unik untuk topik '{query}'...")

    grader_model = get_llm(model_id)
    if hasattr(grader_model, "temperature"):
        grader_model.temperature = 0.0
    if hasattr(grader_model, "max_tokens"):
        grader_model.max_tokens = 60

    messages = [
        SystemMessage(content=GRADER_SYSTEM_PROMPT),
        HumanMessage(content=f"TOPIK: {query}\n\nDAFTAR KANDIDAT DOKUMEN:\n{candidates_text}")
    ]

    grader_tokens = 0
    try:
        response = grader_model.invoke(messages)
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
        print(f"[Agent Grader] Keputusan Raw: {keputusan}")

        if "TIDAK RELEVAN" in keputusan and not re.search(r'\d+', keputusan):
            return OrderedDict(), grader_tokens

        selected_indices = [int(x) for x in re.findall(r'\d+', keputusan)]
        approved: OrderedDict[str, List[Document]] = OrderedDict()
        for i in selected_indices:
            if 1 <= i <= len(source_items):
                title, chs = source_items[i - 1]
                approved[title] = chs

        # Jika model hanya menjawab "RELEVAN" tanpa angka, ambil sumber yang cocok kata kuncinya
        if not approved and "RELEVAN" in keputusan:
            for title, chs in source_items:
                approved[title] = chs

        return approved, grader_tokens

    except Exception as e:
        print(f"[Agent Grader] Error saat menilai: {e}. Fallback ke filter kata kunci.")
        fallback_approved: OrderedDict[str, List[Document]] = OrderedDict()
        for title, chs in source_items:
            if any(has_strong_match({title: chs}, sq) for sq in extract_subqueries(query)):
                fallback_approved[title] = chs
        return fallback_approved, grader_tokens

def diversify_chunks(grouped_sources: OrderedDict[str, List[Document]], k: int = 15) -> List[Document]:
    """
    Mengambil chunk secara proporsional (Round-Robin) dari setiap sumber artikel unik
    agar tidak ada satu sumber yang memonopoli seluruh konteks.
    """
    if not grouped_sources:
        return []

    diversified: List[Document] = []
    source_lists = list(grouped_sources.values())
    max_depth = max(len(lst) for lst in source_lists)

    for depth in range(max_depth):
        for lst in source_lists:
            if depth < len(lst):
                diversified.append(lst[depth])
                if len(diversified) >= k:
                    return diversified

    return diversified

def search_context(query: str, model_id: str, k: int = 15) -> Tuple[str, int]:
    """Mengembalikan konteks multi-sumber yang bervariasi dan jumlah token yang dipakai grader."""
    subqueries = extract_subqueries(query)
    store = get_vectorstore()

    # 1. Tarik kandidat dari PGVector untuk query utama dan tiap sub-topik
    raw_docs: List[Document] = []
    search_queries = [query] + [sq for sq in subqueries if sq.lower() != query.lower()]
    per_query_k = max(8, k // len(search_queries) + 3)

    for sq in search_queries:
        try:
            raw_docs.extend(store.similarity_search(sq, k=per_query_k))
        except Exception as e:
            print(f"[Retriever] Error similarity_search untuk '{sq}': {e}")

    grouped = group_docs_by_source(raw_docs)

    # 2. Cek apakah tiap sub-topik sudah punya sumber kuat & apakah variasi sumber sudah >= MIN_UNIQUE_SOURCES
    missing_subqueries = [sq for sq in subqueries if not has_strong_match(grouped, sq)]
    matching_sources_count = sum(
        1 for title, chs in grouped.items()
        if any(has_strong_match({title: chs}, sq) for sq in subqueries)
    )

    existing_titles = set(grouped.keys())
    if missing_subqueries or matching_sources_count < MIN_UNIQUE_SOURCES:
        terms_to_fetch = missing_subqueries if missing_subqueries else search_queries
        # Pastikan query utama juga ikut dicari untuk menambah variasi artikel terkait
        for sq in search_queries:
            if sq not in terms_to_fetch:
                terms_to_fetch.append(sq)
        needed_pages = max(len(missing_subqueries) + 1, MIN_UNIQUE_SOURCES - matching_sources_count + 1, 3)
        print(f"[Dynamic Fallback] Memperkaya variasi referensi dari Wikipedia untuk: {terms_to_fetch}...")
        wiki_chunks = fetch_wikipedia_multi(terms_to_fetch, existing_titles, max_new_pages=min(needed_pages, 4))
        if wiki_chunks:
            # Tempatkan hasil Wikipedia baru di urutan teratas agar diprioritaskan
            grouped = group_docs_by_source(wiki_chunks + raw_docs)

    # 3. Evaluasi kandidat sumber dengan Agent Grader
    approved_sources, grader_tokens = grade_candidate_sources(query, grouped, model_id)

    # 4. Jika semua sumber PGVector ditolak Grader dan belum sempat ambil Wikipedia, coba Wikipedia sekali lagi
    if not approved_sources:
        print(f"[Dynamic Fallback] Semua sumber awal ditolak Grader. Mencari ulang di Wikipedia untuk '{query}'...")
        wiki_chunks = fetch_wikipedia_multi(search_queries, existing_titles, max_new_pages=3)
        if wiki_chunks:
            wiki_grouped = group_docs_by_source(wiki_chunks)
            approved_sources, extra_tokens = grade_candidate_sources(query, wiki_grouped, model_id)
            grader_tokens += extra_tokens

    # 5. Susun chunk secara bervariasi (Round-Robin antar sumber unik)
    final_docs = diversify_chunks(approved_sources, k=k)
    if not final_docs:
        return "", grader_tokens

    formatted_contexts = []
    unique_refs = OrderedDict()

    for i, doc in enumerate(final_docs):
        title = doc.metadata.get("title", "Tanpa Judul")
        url = doc.metadata.get("url", "#")
        content = doc.page_content.strip()
        formatted = f"[SUMBER {i+1} | {title} | {url}]\n{content}"
        formatted_contexts.append(formatted)
        if url not in unique_refs:
            unique_refs[url] = title

    # Tambahkan ringkasan daftar sumber unik di akhir konteks agar Writer tidak menduplikasi URL
    ref_lines = ["=== DAFTAR SUMBER REFERENSI UNIK (CANTUMKAN HANYA SATU KALI PER URL) ==="]
    for idx, (url, title) in enumerate(unique_refs.items(), start=1):
        ref_lines.append(f"{idx}. [{title}]({url})")

    full_context = "\n\n".join(formatted_contexts) + "\n\n" + "\n".join(ref_lines)
    return full_context, grader_tokens
