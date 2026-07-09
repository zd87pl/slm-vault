"""
Training Queue Service

Manages batch document training with background processing and folder watching.
Enables Enclave to be a personal knowledge vault with unified understanding.
"""

import os
import logging
import threading
import hashlib
import json
import time
from pathlib import Path
from typing import Optional, List, Dict, Any, Callable
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
from queue import Queue, Empty
import shutil

logger = logging.getLogger(__name__)


class QueueItemStatus(Enum):
    """Status of a queue item."""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class QueueItem:
    """A single item in the training queue."""
    id: str
    file_path: str
    filename: str
    status: QueueItemStatus = QueueItemStatus.PENDING
    priority: int = 0  # Higher = more priority
    progress: float = 0.0
    progress_message: str = ""
    error: Optional[str] = None
    added_at: datetime = field(default_factory=datetime.now)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    adapter_id: Optional[str] = None
    encryption_key: Optional[str] = None
    file_hash: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "id": self.id,
            "file_path": self.file_path,
            "filename": self.filename,
            "status": self.status.value,
            "priority": self.priority,
            "progress": self.progress,
            "progress_message": self.progress_message,
            "error": self.error,
            "added_at": self.added_at.isoformat() if self.added_at else None,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "adapter_id": self.adapter_id,
            "encryption_key": self.encryption_key,
            "file_hash": self.file_hash,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "QueueItem":
        """Create from dictionary."""
        return cls(
            id=data["id"],
            file_path=data["file_path"],
            filename=data["filename"],
            status=QueueItemStatus(data.get("status", "pending")),
            priority=data.get("priority", 0),
            progress=data.get("progress", 0.0),
            progress_message=data.get("progress_message", ""),
            error=data.get("error"),
            added_at=datetime.fromisoformat(data["added_at"]) if data.get("added_at") else datetime.now(),
            started_at=datetime.fromisoformat(data["started_at"]) if data.get("started_at") else None,
            completed_at=datetime.fromisoformat(data["completed_at"]) if data.get("completed_at") else None,
            adapter_id=data.get("adapter_id"),
            encryption_key=data.get("encryption_key"),
            file_hash=data.get("file_hash"),
        )


@dataclass
class WatchedFolder:
    """A folder being watched for new documents."""
    path: str
    enabled: bool = True
    auto_train: bool = True  # Automatically add new files to queue
    recursive: bool = True  # Watch subdirectories
    file_extensions: List[str] = field(default_factory=lambda: [".pdf"])
    last_scan: Optional[datetime] = None
    known_files: Dict[str, str] = field(default_factory=dict)  # path -> hash
    known_file_stats: Dict[str, str] = field(default_factory=dict)  # path -> "mtime_ns:size"
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "path": self.path,
            "enabled": self.enabled,
            "auto_train": self.auto_train,
            "recursive": self.recursive,
            "file_extensions": self.file_extensions,
            "last_scan": self.last_scan.isoformat() if self.last_scan else None,
            "known_files": self.known_files,
            "known_file_stats": self.known_file_stats,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "WatchedFolder":
        """Create from dictionary."""
        return cls(
            path=data["path"],
            enabled=data.get("enabled", True),
            auto_train=data.get("auto_train", True),
            recursive=data.get("recursive", True),
            file_extensions=data.get("file_extensions", [".pdf"]),
            last_scan=datetime.fromisoformat(data["last_scan"]) if data.get("last_scan") else None,
            known_files=data.get("known_files", {}),
            known_file_stats=data.get("known_file_stats", {}),
        )


class TrainingQueue:
    """
    Manages a queue of documents for training.
    
    Features:
    - Background processing with pause/resume
    - Priority queue (higher priority items processed first)
    - Folder watching for automatic file detection
    - Duplicate detection via file hashing
    - Persistent state across restarts
    """
    
    def __init__(
        self,
        vault_path: str,
        on_item_updated: Optional[Callable[[QueueItem], None]] = None,
        on_item_completed: Optional[Callable[[QueueItem], None]] = None,
        on_item_failed: Optional[Callable[[QueueItem, str], None]] = None,
    ):
        """
        Initialize the training queue.
        
        Args:
            vault_path: Path to vault directory for persistence
            on_item_updated: Callback when item status/progress changes
            on_item_completed: Callback when item completes successfully
            on_item_failed: Callback when item fails
        """
        self.vault_path = Path(vault_path).expanduser()
        self.queue_dir = self.vault_path / "training_queue"
        self.queue_dir.mkdir(parents=True, exist_ok=True)
        
        # Callbacks
        self.on_item_updated = on_item_updated
        self.on_item_completed = on_item_completed
        self.on_item_failed = on_item_failed
        
        # Queue state
        self.items: Dict[str, QueueItem] = {}
        self.watched_folders: Dict[str, WatchedFolder] = {}
        self.processed_hashes: set = set()  # Hashes of already-trained files
        
        # Processing control
        self._processing = False
        self._paused = False
        self._worker_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._pause_event = threading.Event()
        self._pause_event.set()  # Not paused initially
        
        # Folder watcher
        self._watcher_thread: Optional[threading.Thread] = None
        self._watcher_stop = threading.Event()
        
        # Training function (to be set by VaultApp)
        self._train_document: Optional[Callable] = None
        
        # Load persisted state
        self._load_state()
        
        logger.info(f"TrainingQueue initialized with {len(self.items)} queued items")
    
    def _generate_id(self) -> str:
        """Generate a unique queue item ID."""
        import uuid
        return str(uuid.uuid4())[:8]
    
    def _calculate_file_hash(self, file_path: str) -> str:
        """Calculate SHA-256 hash of a file."""
        sha256 = hashlib.sha256()
        try:
            with open(file_path, 'rb') as f:
                for chunk in iter(lambda: f.read(1024 * 1024), b''):
                    sha256.update(chunk)
            return sha256.hexdigest()
        except Exception as e:
            logger.warning(f"Could not hash file {file_path}: {e}")
            return ""
    
    def _load_state(self):
        """Load queue state from disk."""
        state_file = self.queue_dir / "queue_state.json"
        if state_file.exists():
            try:
                with open(state_file, 'r') as f:
                    data = json.load(f)
                
                # Load queue items
                for item_data in data.get("items", []):
                    item = QueueItem.from_dict(item_data)
                    # Reset processing items to pending on restart
                    if item.status == QueueItemStatus.PROCESSING:
                        item.status = QueueItemStatus.PENDING
                        item.progress = 0.0
                        item.progress_message = ""
                    self.items[item.id] = item
                
                # Load watched folders
                for folder_data in data.get("watched_folders", []):
                    folder = WatchedFolder.from_dict(folder_data)
                    self.watched_folders[folder.path] = folder
                
                # Load processed hashes
                self.processed_hashes = set(data.get("processed_hashes", []))
                
                logger.info(f"Loaded queue state: {len(self.items)} items, {len(self.watched_folders)} folders")
            except Exception as e:
                logger.error(f"Failed to load queue state: {e}")
    
    def _save_state(self):
        """Save queue state to disk."""
        state_file = self.queue_dir / "queue_state.json"
        try:
            data = {
                "items": [item.to_dict() for item in self.items.values()],
                "watched_folders": [folder.to_dict() for folder in self.watched_folders.values()],
                "processed_hashes": list(self.processed_hashes),
            }
            with open(state_file, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save queue state: {e}")
    
    def set_train_function(self, train_fn: Callable):
        """
        Set the function to call for training each document.
        
        The function should accept (file_path, filename, progress_callback) and return
        (adapter_id, encryption_key) on success or raise an exception on failure.
        """
        self._train_document = train_fn
    
    # ==================== Queue Management ====================
    
    def add_file(self, file_path: str, priority: int = 0) -> Optional[QueueItem]:
        """
        Add a file to the training queue.
        
        Args:
            file_path: Path to the PDF file
            priority: Higher = more priority (default 0)
            
        Returns:
            QueueItem if added, None if duplicate
        """
        path = Path(file_path)
        if not path.exists():
            logger.warning(f"File does not exist: {file_path}")
            return None
        
        # Check for duplicates via hash
        file_hash = self._calculate_file_hash(file_path)
        if file_hash in self.processed_hashes:
            logger.info(f"File already processed (hash match): {path.name}")
            return None
        
        # Check if already in queue
        for item in self.items.values():
            if item.file_hash == file_hash and item.status not in [QueueItemStatus.FAILED, QueueItemStatus.CANCELLED]:
                logger.info(f"File already in queue: {path.name}")
                return None
        
        # Copy to queue storage directory
        queue_files_dir = self.queue_dir / "files"
        queue_files_dir.mkdir(exist_ok=True)
        
        item_id = self._generate_id()
        dest_path = queue_files_dir / f"{item_id}_{path.name}"
        shutil.copy2(file_path, dest_path)
        
        # Create queue item
        item = QueueItem(
            id=item_id,
            file_path=str(dest_path),
            filename=path.name,
            priority=priority,
            file_hash=file_hash,
        )
        
        self.items[item.id] = item
        self._save_state()
        
        logger.info(f"Added to queue: {item.filename} (ID: {item.id})")
        
        if self.on_item_updated:
            self.on_item_updated(item)
        
        return item
    
    def add_files(self, file_paths: List[str], priority: int = 0) -> List[QueueItem]:
        """Add multiple files to the queue."""
        added = []
        for path in file_paths:
            item = self.add_file(path, priority)
            if item:
                added.append(item)
        return added
    
    def remove_item(self, item_id: str) -> bool:
        """Remove an item from the queue (only if pending or failed)."""
        if item_id not in self.items:
            return False
        
        item = self.items[item_id]
        if item.status in [QueueItemStatus.PENDING, QueueItemStatus.FAILED, QueueItemStatus.CANCELLED]:
            # Remove the file copy
            try:
                Path(item.file_path).unlink(missing_ok=True)
            except Exception:
                pass
            
            del self.items[item_id]
            self._save_state()
            logger.info(f"Removed from queue: {item.filename}")
            return True
        
        return False
    
    def clear_completed(self):
        """Remove all completed items from the queue."""
        to_remove = [
            item_id for item_id, item in self.items.items()
            if item.status in [QueueItemStatus.COMPLETED, QueueItemStatus.CANCELLED]
        ]
        for item_id in to_remove:
            try:
                Path(self.items[item_id].file_path).unlink(missing_ok=True)
            except Exception:
                pass
            del self.items[item_id]
        
        self._save_state()
        logger.info(f"Cleared {len(to_remove)} completed items")
    
    def get_pending_items(self) -> List[QueueItem]:
        """Get all pending items sorted by priority (highest first)."""
        pending = [
            item for item in self.items.values()
            if item.status == QueueItemStatus.PENDING
        ]
        return sorted(pending, key=lambda x: (-x.priority, x.added_at))
    
    def get_all_items(self) -> List[QueueItem]:
        """Get all items sorted by status and priority."""
        # Order: processing, pending (by priority), completed, failed
        def sort_key(item):
            status_order = {
                QueueItemStatus.PROCESSING: 0,
                QueueItemStatus.PENDING: 1,
                QueueItemStatus.COMPLETED: 2,
                QueueItemStatus.FAILED: 3,
                QueueItemStatus.CANCELLED: 4,
            }
            return (status_order.get(item.status, 5), -item.priority, item.added_at)
        
        return sorted(self.items.values(), key=sort_key)
    
    def retry_failed(self, item_id: str) -> bool:
        """Retry a failed item."""
        if item_id not in self.items:
            return False
        
        item = self.items[item_id]
        if item.status == QueueItemStatus.FAILED:
            item.status = QueueItemStatus.PENDING
            item.progress = 0.0
            item.progress_message = ""
            item.error = None
            self._save_state()
            
            if self.on_item_updated:
                self.on_item_updated(item)
            
            return True
        return False
    
    def retry_all_failed(self):
        """Retry all failed items."""
        for item in self.items.values():
            if item.status == QueueItemStatus.FAILED:
                item.status = QueueItemStatus.PENDING
                item.progress = 0.0
                item.progress_message = ""
                item.error = None
        self._save_state()
    
    # ==================== Processing Control ====================
    
    def start_processing(self):
        """Start processing the queue in background."""
        if self._processing:
            logger.info("Queue processing already running")
            return
        
        if not self._train_document:
            logger.error("Train function not set - cannot start processing")
            return
        
        self._stop_event.clear()
        self._pause_event.set()
        self._processing = True
        
        self._worker_thread = threading.Thread(target=self._process_queue, daemon=True)
        self._worker_thread.start()
        
        logger.info("Started queue processing")
    
    def stop_processing(self):
        """Stop queue processing."""
        if not self._processing:
            return
        
        self._stop_event.set()
        self._pause_event.set()  # Unblock if paused
        
        if self._worker_thread:
            self._worker_thread.join(timeout=5.0)
        
        self._processing = False
        logger.info("Stopped queue processing")
    
    def pause_processing(self):
        """Pause queue processing."""
        self._paused = True
        self._pause_event.clear()
        logger.info("Paused queue processing")
    
    def resume_processing(self):
        """Resume queue processing."""
        self._paused = False
        self._pause_event.set()
        logger.info("Resumed queue processing")
    
    @property
    def is_processing(self) -> bool:
        """Check if queue is processing."""
        return self._processing and not self._paused
    
    @property
    def is_paused(self) -> bool:
        """Check if queue is paused."""
        return self._paused
    
    def _process_queue(self):
        """Background worker that processes queue items."""
        logger.info("Queue worker started")
        
        while not self._stop_event.is_set():
            # Wait if paused
            self._pause_event.wait()
            
            if self._stop_event.is_set():
                break
            
            # Get next pending item
            pending = self.get_pending_items()
            if not pending:
                # No items to process, wait a bit
                time.sleep(1.0)
                continue
            
            item = pending[0]
            self._process_item(item)
        
        logger.info("Queue worker stopped")
    
    def _process_item(self, item: QueueItem):
        """Process a single queue item."""
        logger.info(f"Processing: {item.filename}")
        
        item.status = QueueItemStatus.PROCESSING
        item.started_at = datetime.now()
        item.progress = 0.0
        item.progress_message = "Starting..."
        self._save_state()
        
        if self.on_item_updated:
            self.on_item_updated(item)
        
        def progress_callback(progress: float, message: str = ""):
            """Update item progress."""
            item.progress = progress
            item.progress_message = message
            if self.on_item_updated:
                self.on_item_updated(item)
        
        try:
            # Call the training function
            adapter_id, encryption_key = self._train_document(
                item.file_path,
                item.filename,
                progress_callback
            )
            
            # Success!
            item.status = QueueItemStatus.COMPLETED
            item.completed_at = datetime.now()
            item.adapter_id = adapter_id
            item.encryption_key = encryption_key
            item.progress = 100.0
            item.progress_message = "Complete!"
            
            # Mark hash as processed
            if item.file_hash:
                self.processed_hashes.add(item.file_hash)
            
            self._save_state()
            
            logger.info(f"Completed: {item.filename} -> adapter {adapter_id}")
            
            if self.on_item_completed:
                self.on_item_completed(item)
            
        except Exception as e:
            logger.error(f"Failed to process {item.filename}: {e}")
            
            item.status = QueueItemStatus.FAILED
            item.error = str(e)
            item.progress_message = f"Failed: {str(e)[:50]}"
            self._save_state()
            
            if self.on_item_failed:
                self.on_item_failed(item, str(e))
        
        if self.on_item_updated:
            self.on_item_updated(item)
    
    # ==================== Folder Watching ====================
    
    def add_watched_folder(self, folder_path: str, auto_train: bool = True, recursive: bool = True) -> WatchedFolder:
        """Add a folder to watch for new documents."""
        path = Path(folder_path).expanduser().resolve()
        
        if not path.is_dir():
            raise ValueError(f"Not a directory: {folder_path}")
        
        folder = WatchedFolder(
            path=str(path),
            auto_train=auto_train,
            recursive=recursive,
        )
        
        # Initial scan to populate known files
        self._scan_folder(folder, initial=True)
        
        self.watched_folders[str(path)] = folder
        self._save_state()
        
        logger.info(f"Added watched folder: {path} ({len(folder.known_files)} existing files)")
        
        return folder
    
    def remove_watched_folder(self, folder_path: str) -> bool:
        """Remove a watched folder."""
        path = str(Path(folder_path).expanduser().resolve())
        if path in self.watched_folders:
            del self.watched_folders[path]
            self._save_state()
            logger.info(f"Removed watched folder: {path}")
            return True
        return False
    
    def toggle_folder(self, folder_path: str, enabled: bool):
        """Enable or disable a watched folder."""
        path = str(Path(folder_path).expanduser().resolve())
        if path in self.watched_folders:
            self.watched_folders[path].enabled = enabled
            self._save_state()
    
    def get_watched_folders(self) -> List[WatchedFolder]:
        """Get all watched folders."""
        return list(self.watched_folders.values())
    
    def start_folder_watcher(self):
        """Start the folder watcher thread."""
        if self._watcher_thread and self._watcher_thread.is_alive():
            return
        
        self._watcher_stop.clear()
        self._watcher_thread = threading.Thread(target=self._watch_folders, daemon=True)
        self._watcher_thread.start()
        logger.info("Started folder watcher")
    
    def stop_folder_watcher(self):
        """Stop the folder watcher thread."""
        self._watcher_stop.set()
        if self._watcher_thread:
            self._watcher_thread.join(timeout=5.0)
        logger.info("Stopped folder watcher")
    
    def _watch_folders(self):
        """Background thread that watches folders for new files."""
        while not self._watcher_stop.is_set():
            for folder in self.watched_folders.values():
                if folder.enabled:
                    new_files = self._scan_folder(folder)
                    
                    if new_files and folder.auto_train:
                        for file_path in new_files:
                            self.add_file(file_path)
            
            # Check every 5 seconds
            self._watcher_stop.wait(5.0)
    
    def _scan_folder(self, folder: WatchedFolder, initial: bool = False) -> List[str]:
        """Scan a folder for new files."""
        new_files = []
        path = Path(folder.path)
        
        if not path.exists():
            return new_files
        
        # Get all matching files
        if folder.recursive:
            files = []
            for ext in folder.file_extensions:
                files.extend(path.rglob(f"*{ext}"))
        else:
            files = []
            for ext in folder.file_extensions:
                files.extend(path.glob(f"*{ext}"))
        
        current_paths = set()
        for file_path in files:
            str_path = str(file_path)
            current_paths.add(str_path)

            try:
                stat = file_path.stat()
                current_stat = f"{stat.st_mtime_ns}:{stat.st_size}"
            except Exception as e:
                logger.debug(f"Could not stat file {str_path}: {e}")
                continue

            # Skip expensive hashing when file metadata is unchanged.
            if folder.known_file_stats.get(str_path) == current_stat:
                continue

            file_hash = self._calculate_file_hash(str_path)
            folder.known_file_stats[str_path] = current_stat
            
            if str_path not in folder.known_files:
                # New file!
                folder.known_files[str_path] = file_hash
                
                if not initial:
                    logger.info(f"New file detected: {file_path.name}")
                    new_files.append(str_path)
            elif folder.known_files[str_path] != file_hash:
                # File modified!
                folder.known_files[str_path] = file_hash
                
                if not initial:
                    logger.info(f"File modified: {file_path.name}")
                    new_files.append(str_path)

        # Remove deleted files from folder cache maps
        deleted_paths = set(folder.known_files.keys()) - current_paths
        for deleted in deleted_paths:
            folder.known_files.pop(deleted, None)
            folder.known_file_stats.pop(deleted, None)
        
        folder.last_scan = datetime.now()
        return new_files
    
    def scan_folder_now(self, folder_path: str) -> List[str]:
        """Manually trigger a folder scan and return new files."""
        path = str(Path(folder_path).expanduser().resolve())
        if path not in self.watched_folders:
            return []
        
        folder = self.watched_folders[path]
        new_files = self._scan_folder(folder)
        self._save_state()
        
        return new_files
    
    # ==================== Statistics ====================
    
    def get_stats(self) -> Dict[str, Any]:
        """Get queue statistics."""
        items = list(self.items.values())
        
        return {
            "total": len(items),
            "pending": sum(1 for i in items if i.status == QueueItemStatus.PENDING),
            "processing": sum(1 for i in items if i.status == QueueItemStatus.PROCESSING),
            "completed": sum(1 for i in items if i.status == QueueItemStatus.COMPLETED),
            "failed": sum(1 for i in items if i.status == QueueItemStatus.FAILED),
            "watched_folders": len(self.watched_folders),
            "processed_total": len(self.processed_hashes),
            "is_processing": self.is_processing,
            "is_paused": self.is_paused,
        }
    
    # ==================== Cleanup ====================
    
    def shutdown(self):
        """Clean shutdown of the queue."""
        self.stop_processing()
        self.stop_folder_watcher()
        self._save_state()
        logger.info("TrainingQueue shutdown complete")
