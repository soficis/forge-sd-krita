import os
import json
import time
import uuid
import base64
import shutil
import threading
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# Constants
MAX_ENTRIES = 100
MAX_AGE_DAYS = 30
MIGRATION_MARKER = ".migrated"


def _get_history_dir():
    """Determine the best history directory location.
    
    Priority:
    1. Krita's resource directory (if krita module available)
    2. Fallback: ~/.forge/history
    """
    try:
        import krita
        krita_app = krita.Krita.instance()
        if krita_app is not None:
            resource_dir = krita_app.resourceDir()
            if resource_dir and os.path.isdir(resource_dir):
                return os.path.join(str(resource_dir), "forge_history")
    except (ImportError, AttributeError, RuntimeError):
        pass

    return os.path.join(os.path.expanduser("~"), ".forge", "history")


def _get_old_history_dir():
    """Return the legacy ~/.forge/history path for migration."""
    return os.path.join(os.path.expanduser("~"), ".forge", "history")


class HistoryManager:
    def __init__(self):
        self.history_dir = _get_history_dir()
        self.thumbs_dir = os.path.join(self.history_dir, "thumbnails")
        self.history_file = os.path.join(self.history_dir, "history.json")
        self.old_history_dir = _get_old_history_dir()

        if not os.path.exists(self.thumbs_dir):
            os.makedirs(self.thumbs_dir, exist_ok=True)

        # Run migration on first initialization
        self._migrate_if_needed()

    # ------------------------------------------------------------------
    # Migration
    # ------------------------------------------------------------------

    def _migrate_if_needed(self):
        """Move data from the old ~/.forge/history location to the new one."""
        old_history_file = os.path.join(self.old_history_dir, "history.json")
        migration_done_marker = os.path.join(self.old_history_dir, MIGRATION_MARKER)

        # Skip if old location doesn't exist, or we're already at the old location,
        # or migration already happened
        if not os.path.exists(old_history_file):
            return
        if os.path.abspath(self.history_dir) == os.path.abspath(self.old_history_dir):
            return
        if os.path.exists(migration_done_marker):
            return

        logger.info(
            "Migrating forge history from %s -> %s", self.old_history_dir, self.history_dir
        )

        try:
            # Ensure destination directories exist
            os.makedirs(self.history_dir, exist_ok=True)
            os.makedirs(self.thumbs_dir, exist_ok=True)

            # Copy history JSON (merge if destination already has one)
            existing = self.get_history() if os.path.exists(self.history_file) else []
            with open(old_history_file, "r") as f:
                old_entries = json.load(f)
            merged = old_entries + existing
            # Deduplicate by timestamp (keep first occurrence) and cap at MAX_ENTRIES
            seen = set()
            deduped = []
            for entry in merged:
                ts = entry.get("timestamp")
                if ts not in seen:
                    seen.add(ts)
                    deduped.append(entry)
            deduped = deduped[:MAX_ENTRIES]

            with open(self.history_file, "w") as f:
                json.dump(deduped, f, indent=4)

            # Move thumbnail files
            old_thumbs_dir = os.path.join(self.old_history_dir, "thumbnails")
            if os.path.isdir(old_thumbs_dir):
                for thumb_name in os.listdir(old_thumbs_dir):
                    src = os.path.join(old_thumbs_dir, thumb_name)
                    dst = os.path.join(self.thumbs_dir, thumb_name)
                    if os.path.isfile(src) and not os.path.exists(dst):
                        shutil.copy2(src, dst)

            # Mark migration as done
            Path(migration_done_marker).touch()
            logger.info("Migration complete: %d entries moved", len(deduped))

        except Exception:
            logger.exception("Failed to migrate history from old location")

    # ------------------------------------------------------------------
    # TTL cleanup helpers
    # ------------------------------------------------------------------

    def _ttl_cutoff(self):
        """Return the earliest acceptable timestamp."""
        return time.time() - MAX_AGE_DAYS * 86400

    def _cleanup_expired(self, entries):
        """Remove entries older than MAX_AGE_DAYS and their orphaned thumbnails."""
        cutoff = self._ttl_cutoff()
        kept = []
        removed_thumbs = []
        for entry in entries:
            ts = entry.get("timestamp", 0)
            if ts >= cutoff:
                kept.append(entry)
            else:
                thumb = entry.get("thumbnail")
                if thumb and os.path.isfile(thumb):
                    removed_thumbs.append(thumb)

        for thumb_path in removed_thumbs:
            try:
                os.remove(thumb_path)
            except OSError:
                logger.debug("Could not remove expired thumbnail: %s", thumb_path)

        return kept

    def _cleanup_orphaned_thumbnails(self, kept_entries):
        """Remove thumbnail files not referenced by any kept entry."""
        referenced = set()
        for entry in kept_entries:
            thumb = entry.get("thumbnail")
            if thumb:
                referenced.add(os.path.normpath(thumb))

        if not os.path.isdir(self.thumbs_dir):
            return

        for fname in os.listdir(self.thumbs_dir):
            fpath = os.path.normpath(os.path.join(self.thumbs_dir, fname))
            if fpath not in referenced:
                try:
                    os.remove(fpath)
                except OSError:
                    logger.debug("Could not remove orphaned thumbnail: %s", fpath)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def save_generation(self, data: dict, thumbnail_path: str = None):
        """Save a generation entry synchronously (backward-compatible)."""
        history = self.get_history()

        entry = {
            "timestamp": time.time(),
            "thumbnail": thumbnail_path,
            **data,
        }

        history.insert(0, entry)
        history = history[:MAX_ENTRIES]

        with open(self.history_file, "w") as f:
            json.dump(history, f, indent=4)

    def save_generation_async(self, data: dict, image_data_b64: str):
        """Save a generation with an async thumbnail write (non-blocking).

        1. Decode base64 image data
        2. Write thumbnail to disk in a background thread
        3. Then save the generation entry (still on the caller thread for
           the history JSON, but the heavy I/O is off-loaded)

        The original synchronous ``save_generation()`` is kept for backward
        compatibility.
        """
        thumb_path = os.path.join(self.thumbs_dir, f"{uuid.uuid4().hex}.png")

        def _write_thumb():
            try:
                raw = base64.b64decode(image_data_b64)
                with open(thumb_path, "wb") as f:
                    f.write(raw)
            except Exception:
                logger.exception("Failed to write thumbnail asynchronously")

        thread = threading.Thread(target=_write_thumb, daemon=True)
        thread.start()

        # Save the history entry immediately (thumbnail will appear once
        # the thread finishes; this is fine for UI display).
        self.save_generation(data=data, thumbnail_path=thumb_path)

    def get_history(self):
        """Return history entries with expired ones removed."""
        if not os.path.exists(self.history_file):
            return []
        try:
            with open(self.history_file, "r") as f:
                entries = json.load(f)
        except (json.JSONDecodeError, OSError):
            return []

        # Apply TTL cleanup
        cleaned = self._cleanup_expired(entries)
        # Remove orphaned thumbnails
        self._cleanup_orphaned_thumbnails(cleaned)

        # Persist cleaned list if anything changed
        if len(cleaned) != len(entries):
            try:
                with open(self.history_file, "w") as f:
                    json.dump(cleaned, f, indent=4)
            except OSError:
                logger.debug("Could not persist cleaned history")

        return cleaned

    def clear_all(self):
        """Delete all history data and thumbnails."""
        if os.path.exists(self.history_file):
            os.remove(self.history_file)
        if os.path.exists(self.thumbs_dir):
            shutil.rmtree(self.thumbs_dir)
            os.makedirs(self.thumbs_dir, exist_ok=True)


__all__ = ["HistoryManager"]
