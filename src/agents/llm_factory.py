import os
from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_groq import ChatGroq
from langchain_cohere import ChatCohere
from langchain_openai import ChatOpenAI

load_dotenv()

def get_llm(model_identifier: str):
    """
    Factory function untuk menginisiasi LLM sesuai nama/provider.
    Format model_identifier: "provider/model_name"
    Contoh: "groq/llama3-8b-8192", "cohere/command-r", "gemini/gemini-3.5-flash", "openrouter/meta-llama/llama-3-8b-instruct:free"
    """
    if "/" not in model_identifier:
        # Default fallback
        provider = "gemini"
        model_name = "gemini-3.5-flash"
    else:
        provider, model_name = model_identifier.split("/", 1)
        
    provider = provider.lower()
    
    if provider == "groq":
        # Khusus Qwen 27B di Groq free tier memiliki limit ketat 1000 Output Tokens Per Minute (OTPM).
        # Memasang max_tokens 800 mencegah request melampaui kuota 1000 OTPM.
        groq_max_tokens = 800 if "qwen" in model_name.lower() else 1000
        return ChatGroq(
            temperature=0.7,
            model_name=model_name,
            max_tokens=groq_max_tokens,
            api_key=os.getenv("GROQ_API_KEY")
        )
    elif provider == "cohere":
        return ChatCohere(
            temperature=0.7,
            model=model_name,
            cohere_api_key=os.getenv("COHERE_API_KEY")
        )
    elif provider == "openrouter":
        return ChatOpenAI(
            temperature=0.7,
            model=model_name,
            api_key=os.getenv("OPENROUTER_API_KEY"),
            base_url="https://openrouter.ai/api/v1"
        )
    else:
        # Default to Gemini
        return ChatGoogleGenerativeAI(
            model=model_name,
            temperature=0.7,
            api_key=os.getenv("GEMINI_API_KEY")
        )
