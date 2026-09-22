import os
import pandas as pd
from datasets import Dataset
from ragas.metrics import faithfulness
from ragas import evaluate
from langchain_openai import ChatOpenAI
from dotenv import load_dotenv

# Load environment variables (OPENAI_API_KEY, etc.)
load_dotenv()

def evaluate_faithfulness(data_dict: dict) -> pd.DataFrame:
    """
    Mengevaluasi metrik Faithfulness menggunakan RAGAS.
    Gunakan LLM Juri yang berbeda dari LLM Agen untuk objektivitas.
    
    Args:
        data_dict (dict): Dictionary yang berisi 'question', 'answer', dan 'contexts'
        
    Returns:
        pd.DataFrame: Hasil evaluasi per baris dataset
    """
    print("Mempersiapkan dataset untuk evaluasi RAGAS...")
    dataset = Dataset.from_dict(data_dict)
    
    # Menggunakan GPT-4o-mini atau GPT-4o sebagai Juri Independen (LLM-as-a-judge)
    # Pastikan temperature diset ke 0.0 agar deterministik (syarat Scopus)
    judge_llm = ChatOpenAI(model="gpt-4o", temperature=0.0)
    
    print("Menjalankan evaluasi Faithfulness...")
    result = evaluate(
        dataset,
        metrics=[faithfulness],
        llm=judge_llm,
        # Untuk Scopus, kita bisa mengontrol seed/param lain jika library mendukung
    )
    
    df_result = result.to_pandas()
    print(f"\nRata-rata Skor Faithfulness: {df_result['faithfulness'].mean():.4f}")
    
    return df_result

if __name__ == "__main__":
    # ---------------------------------------------------------
    # Contoh Data Mock untuk Pengujian Awal
    # ---------------------------------------------------------
    mock_data = {
        "question": [
            "Apa dampak kebijakan baru terhadap UMKM di Indonesia?",
            "Siapa yang memenangkan medali emas di Olimpiade 2024 untuk bulu tangkis?"
        ],
        "answer": [
            "Kebijakan baru menurunkan pajak UMKM sebesar 5%.", # Jawaban halusinasi (sumber menyebut 15%->10%, bukan 'sebesar 5%')
            "Atlet bulu tangkis Indonesia memenangkan medali emas di sektor ganda putra." 
        ],
        "contexts": [
            ["Pemerintah mengumumkan pemotongan pajak UMKM dari 15% menjadi 10% untuk tahun depan."],
            ["Pada Olimpiade 2024, Indonesia berhasil meraih medali emas di cabang olahraga angkat besi dan panjat tebing. Tidak ada emas untuk bulu tangkis."]
        ]
    }
    
    # Eksekusi Evaluasi
    try:
        evaluation_results = evaluate_faithfulness(mock_data)
        print("\nDetail Hasil per Data:")
        print(evaluation_results[['question', 'answer', 'faithfulness']])
    except Exception as e:
        print(f"Error saat menjalankan evaluasi: {e}")
        print("Pastikan Anda sudah memiliki OPENAI_API_KEY di file .env")
