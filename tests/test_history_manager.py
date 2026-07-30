"""Unit tests for forge.domain.history_manager — file-system backed
generation history with TTL cleanup, thumbnails, and migration logic.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from unittest.mock import patch

import pytest

from forge.domain.history_manager import (
    MAX_ENTRIES,
    MAX_AGE_DAYS,
    HistoryManager,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def history_dir(tmp_path):
    """Provide a temporary directory and patch _get_history_dir to use it."""
    hdir = tmp_path / "history"
    hdir.mkdir(parents=True, exist_ok=True)
    with patch("forge.domain.history_manager._get_history_dir", return_value=str(hdir)):
        yield hdir


@pytest.fixture
def manager(history_dir):
    """Return a HistoryManager rooted at the temp directory."""
    return HistoryManager()


# ---------------------------------------------------------------------------
# Basic save / get / clear
# ---------------------------------------------------------------------------


class TestSaveAndGet:
    """save_generation and get_history round-trip correctly."""

    def test_save_and_retrieve_single_entry(self, manager):
        manager.save_generation({"prompt": "a cat"})
        history = manager.get_history()
        assert len(history) == 1
        assert history[0]["prompt"] == "a cat"
        assert "timestamp" in history[0]

    def test_newest_entry_is_first(self, manager):
        manager.save_generation({"prompt": "first"})
        time.sleep(0.01)
        manager.save_generation({"prompt": "second"})
        history = manager.get_history()
        assert history[0]["prompt"] == "second"
        assert history[1]["prompt"] == "first"

    def test_save_with_thumbnail_path(self, manager, history_dir):
        thumb = history_dir / "test_thumb.png"
        thumb.write_bytes(b"\x89PNG fake")
        manager.save_generation({"prompt": "test"}, thumbnail_path=str(thumb))
        history = manager.get_history()
        assert history[0]["thumbnail"] == str(thumb)

    def test_max_entries_cap(self, manager):
        for i in range(MAX_ENTRIES + 10):
            manager.save_generation({"index": i})
        history = manager.get_history()
        assert len(history) <= MAX_ENTRIES

    def test_get_history_empty_when_no_file(self, history_dir):
        mgr = HistoryManager()
        assert mgr.get_history() == []


class TestClearAll:
    """clear_all removes history file and thumbnails."""

    def test_clear_removes_history_file(self, manager, history_dir):
        manager.save_generation({"prompt": "test"})
        assert os.path.isfile(manager.history_file)

        manager.clear_all()
        assert not os.path.exists(manager.history_file)

    def test_clear_removes_thumbnails(self, manager, history_dir):
        thumb_dir = Path(manager.thumbs_dir)
        thumb = thumb_dir / "img.png"
        thumb.write_bytes(b"fake")
        manager.save_generation({"prompt": "x"}, thumbnail_path=str(thumb))

        manager.clear_all()
        assert not thumb.exists()
        # thumbnails directory should still exist (recreated)
        assert os.path.isdir(manager.thumbs_dir)


# ---------------------------------------------------------------------------
# TTL cleanup
# ---------------------------------------------------------------------------


class TestTTLCleanup:
    """Expired entries are pruned on get_history()."""

    def test_expired_entry_is_removed(self, manager):
        old_ts = time.time() - (MAX_AGE_DAYS + 1) * 86400
        entry = {"prompt": "old", "timestamp": old_ts}

        # Manually write an old entry
        with open(manager.history_file, "w") as f:
            json.dump([entry], f)

        history = manager.get_history()
        assert len(history) == 0

    def test_recent_entry_is_kept(self, manager):
        manager.save_generation({"prompt": "recent"})
        history = manager.get_history()
        assert len(history) == 1

    def test_expired_entry_with_thumbnail_removes_thumb(self, manager, history_dir):
        thumb_dir = Path(manager.thumbs_dir)
        thumb = thumb_dir / "old_thumb.png"
        thumb.write_bytes(b"fake")
        old_ts = time.time() - (MAX_AGE_DAYS + 1) * 86400
        entry = {"prompt": "old", "timestamp": old_ts, "thumbnail": str(thumb)}

        with open(manager.history_file, "w") as f:
            json.dump([entry], f)

        manager.get_history()
        assert not thumb.exists()

    def test_mixed_old_and_new_entries(self, manager):
        now = time.time()
        old_ts = now - (MAX_AGE_DAYS + 1) * 86400
        entries = [
            {"prompt": "old", "timestamp": old_ts},
            {"prompt": "new", "timestamp": now},
        ]
        with open(manager.history_file, "w") as f:
            json.dump(entries, f)

        history = manager.get_history()
        assert len(history) == 1
        assert history[0]["prompt"] == "new"


# ---------------------------------------------------------------------------
# Orphaned thumbnail cleanup
# ---------------------------------------------------------------------------


class TestOrphanedThumbnails:
    """Thumbnail files not referenced by any entry are removed."""

    def test_orphaned_thumbnail_is_removed(self, manager, history_dir):
        thumb_dir = Path(manager.thumbs_dir)
        thumb = thumb_dir / "orphan.png"
        thumb.write_bytes(b"fake")
        manager.save_generation({"prompt": "no thumb ref"})

        manager.get_history()
        assert not thumb.exists()

    def test_referenced_thumbnail_is_kept(self, manager, history_dir):
        thumb_dir = Path(manager.thumbs_dir)
        thumb = thumb_dir / "kept.png"
        thumb.write_bytes(b"fake")
        manager.save_generation({"prompt": "with thumb"}, thumbnail_path=str(thumb))

        manager.get_history()
        assert thumb.exists()


# ---------------------------------------------------------------------------
# JSON error handling
# ---------------------------------------------------------------------------


class TestCorruptHistory:
    """Corrupted history.json is handled gracefully."""

    def test_invalid_json_returns_empty(self, manager, history_dir):
        Path(manager.history_file).write_text("not valid json {{{")

        history = manager.get_history()
        assert history == []

    def test_empty_file_returns_empty(self, manager, history_dir):
        Path(manager.history_file).write_text("")

        history = manager.get_history()
        assert history == []


# ---------------------------------------------------------------------------
# Async thumbnail save
# ---------------------------------------------------------------------------


class TestSaveGenerationAsync:
    """save_generation_async writes thumbnail in background thread."""

    def test_async_save_creates_history_entry(self, manager):
        # Small base64 PNG (1x1 red pixel)
        tiny_b64 = (
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR4"
            "nGP4z8BQDwAEgAF/pooBPQAAAABJRU5ErkJggg=="
        )
        manager.save_generation_async({"prompt": "async"}, image_data_b64=tiny_b64)

        history = manager.get_history()
        assert len(history) == 1
        assert history[0]["prompt"] == "async"
        # thumbnail path should be set
        assert history[0]["thumbnail"] is not None

    def test_async_save_writes_thumbnail_file(self, manager):
        tiny_b64 = (
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR4"
            "nGP4z8BQDwAEgAF/pooBPQAAAABJRU5ErkJggg=="
        )
        manager.save_generation_async({"prompt": "async"}, image_data_b64=tiny_b64)

        history = manager.get_history()
        thumb_path = history[0]["thumbnail"]
        # Allow thread to finish
        time.sleep(0.1)
        assert os.path.isfile(thumb_path)


# ---------------------------------------------------------------------------
# History directory creation
# ---------------------------------------------------------------------------


class TestDirectoryCreation:
    """Manager creates required directories on init."""

    def test_creates_thumbs_dir(self, history_dir):
        # Remove thumbs dir if it exists
        thumbs = history_dir / "thumbnails"
        if thumbs.exists():
            thumbs.rmdir()
        mgr = HistoryManager()
        assert os.path.isdir(mgr.thumbs_dir)
