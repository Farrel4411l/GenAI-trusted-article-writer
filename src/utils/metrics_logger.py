import csv
import os
from datetime import datetime

LOG_FILE = "experiment_metrics.csv"

def log_metrics(state, total_latency):
    file_exists = os.path.isfile(LOG_FILE)
    
    with open(LOG_FILE, mode='a', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow([
                "Timestamp", 
                "Topic", 
                "Writer Model", 
                "Reviewer Model", 
                "Revisions", 
                "Passed", 
                "Writer Tokens", 
                "Reviewer Tokens", 
                "Grader Tokens",
                "Total Latency (s)"
            ])
        
        writer.writerow([
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            state.get("topic", ""),
            state.get("writer_model", ""),
            state.get("reviewer_model", ""),
            max(1, state.get("revision_count", 1) - 1),  # actual revisions completed
            state.get("is_passed", False),
            state.get("writer_tokens", 0),
            state.get("reviewer_tokens", 0),
            state.get("grader_tokens", 0),
            round(total_latency, 2)
        ])
