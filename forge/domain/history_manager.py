import os
import json
import time

class HistoryManager:
    def __init__(self):
        self.history_dir = os.path.join(os.path.expanduser("~"), ".forge", "history")
        self.thumbs_dir = os.path.join(self.history_dir, "thumbnails")
        self.history_file = os.path.join(self.history_dir, "history.json")
        
        if not os.path.exists(self.thumbs_dir):
            os.makedirs(self.thumbs_dir, exist_ok=True)

    def save_generation(self, data: dict, thumbnail_path: str = None):
        history = self.get_history()
        
        entry = {
            'timestamp': time.time(),
            'thumbnail': thumbnail_path,
            **data
        }
        
        history.insert(0, entry) # Most recent first
        history = history[:100] # Keep last 100
        
        with open(self.history_file, 'w') as f:
            json.dump(history, f, indent=4)

    def get_history(self):
        if not os.path.exists(self.history_file):
            return []
        try:
            with open(self.history_file, 'r') as f:
                return json.load(f)
        except:
            return []

    def clear_all(self):
        if os.path.exists(self.history_file):
            os.remove(self.history_file)
        if os.path.exists(self.thumbs_dir):
            import shutil
            shutil.rmtree(self.thumbs_dir)
            os.makedirs(self.thumbs_dir, exist_ok=True)

__all__ = ["HistoryManager"]
