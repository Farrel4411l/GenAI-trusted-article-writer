from dotenv import load_dotenv
import os
load_dotenv()

from src.agents.orchestrator import build_graph

def run():
    app_graph = build_graph()
    initial_state = {
        "topic": "Sejarah Suku Baduy",
        "context": "",
        "draft": "",
        "revision_notes": "",
        "revision_count": 1,
        "is_passed": False,
        "writer_model": "groq/qwen/qwen3.8-27b",
        "reviewer_model": "gemini/gemini-3.5-flash"
    }
    
    print("Mulai...")
    for event in app_graph.stream(initial_state):
        print(event.keys())

if __name__ == "__main__":
    run()
