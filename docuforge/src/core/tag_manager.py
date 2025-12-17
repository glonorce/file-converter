# Copyright (c) 2025 GÖKSEL ÖZKAN
# Persistent User Tag Management

from pathlib import Path
from typing import List
from ruamel.yaml import YAML

yaml = YAML()


class TagManager:
    """
    Manages user-defined blacklist patterns for text cleaning.
    Persists tags to ~/.docuforge/user_tags.yaml
    """
    
    def __init__(self):
        self.config_dir = Path.home() / ".docuforge"
        self.tags_file = self.config_dir / "user_tags.yaml"
    
    def _ensure_config_dir(self):
        """Create config directory if it doesn't exist."""
        self.config_dir.mkdir(parents=True, exist_ok=True)
    
    def load_user_tags(self) -> List[str]:
        """Load user tags from file. Returns empty list if file doesn't exist."""
        if not self.tags_file.exists():
            return []
        
        try:
            with open(self.tags_file, "r", encoding="utf-8") as f:
                data = yaml.load(f)
                return data.get("tags", []) if data else []
        except Exception:
            return []
    
    def save_user_tags(self, tags: List[str]):
        """Save user tags to file."""
        self._ensure_config_dir()
        
        with open(self.tags_file, "w", encoding="utf-8") as f:
            yaml.dump({"tags": tags}, f)
    
    def add_tag(self, pattern: str) -> bool:
        """
        Add a new tag pattern. Returns True if added, False if already exists.
        """
        tags = self.load_user_tags()
        if pattern in tags:
            return False
        
        tags.append(pattern)
        self.save_user_tags(tags)
        return True
    
    def remove_tag(self, pattern: str) -> bool:
        """
        Remove a tag pattern. Returns True if removed, False if not found.
        """
        tags = self.load_user_tags()
        if pattern not in tags:
            return False
        
        tags.remove(pattern)
        self.save_user_tags(tags)
        return True
    
    def list_tags(self) -> List[str]:
        """List all user tags."""
        return self.load_user_tags()
