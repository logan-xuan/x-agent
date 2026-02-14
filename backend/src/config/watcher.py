"""File watcher for configuration hot-reload."""

import time
from pathlib import Path
from typing import Callable

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer


class ConfigChangeHandler(FileSystemEventHandler):
    """Handler for configuration file changes."""
    
    def __init__(self, config_path: Path, callback: Callable[[], None]) -> None:
        self.config_path = config_path.resolve()
        self.callback = callback
        self.last_modified = 0.0
        self.debounce_seconds = 1.0
    
    def on_modified(self, event) -> None:
        """Called when a file is modified."""
        if event.is_directory:
            return
            
        event_path = Path(event.src_path).resolve()
        if event_path != self.config_path:
            return
        
        # Debounce to avoid multiple rapid reloads
        current_time = time.time()
        if current_time - self.last_modified < self.debounce_seconds:
            return
        
        self.last_modified = current_time
        print(f"Configuration file changed: {event_path}")
        self.callback()


class ConfigWatcher:
    """Watchdog-based file watcher for configuration hot-reload."""
    
    def __init__(self, config_path: Path, callback: Callable[[], None]) -> None:
        """Initialize the watcher.
        
        Args:
            config_path: Path to the configuration file to watch
            callback: Function to call when file changes
        """
        self.config_path = config_path
        self.callback = callback
        self.observer: Observer | None = None
        self.handler = ConfigChangeHandler(config_path, callback)
    
    def start(self) -> None:
        """Start watching for file changes."""
        if self.observer is not None:
            return
        
        self.observer = Observer()
        watch_dir = self.config_path.parent
        
        self.observer.schedule(self.handler, str(watch_dir), recursive=False)
        self.observer.start()
        print(f"Started watching {self.config_path} for changes")
    
    def stop(self) -> None:
        """Stop watching for file changes."""
        if self.observer:
            self.observer.stop()
            self.observer.join()
            self.observer = None
            print(f"Stopped watching {self.config_path}")
