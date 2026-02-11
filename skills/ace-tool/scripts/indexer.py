"""Code indexer: scan, hash, chunk, upload to ACE batch-upload API."""

import fnmatch
import gzip
import hashlib
import json
import logging
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional

import httpx

try:
    from .templates import (
        TEXT_EXTENSIONS, EXCLUDE_PATTERNS, BINARY_EXTENSIONS,
        MAX_BLOB_SIZE, MAX_LINES_PER_BLOB, UPLOAD_BATCH_COUNT,
        MAX_BATCH_SIZE, INDEX_DIR, INDEX_FILE, ENCODING_CHAIN,
        USER_AGENT,
    )
    from .utils import get_session_id, detect_and_read, sanitize_content
except ImportError:
    from templates import (
        TEXT_EXTENSIONS, EXCLUDE_PATTERNS, BINARY_EXTENSIONS,
        MAX_BLOB_SIZE, MAX_LINES_PER_BLOB, UPLOAD_BATCH_COUNT,
        MAX_BATCH_SIZE, INDEX_DIR, INDEX_FILE, ENCODING_CHAIN,
        USER_AGENT,
    )
    from utils import get_session_id, detect_and_read, sanitize_content

log = logging.getLogger(__name__)


@dataclass
class BlobEntry:
    path: str
    blob_name: str
    mtime: float
    size: int


@dataclass
class ProjectIndex:
    entries: dict[str, BlobEntry] = field(default_factory=dict)
    last_indexed: float = 0.0


class Indexer:
    def __init__(self, project_root: str, base_url: str, token: str):
        self.root = Path(project_root).resolve()
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.index_path = self.root / INDEX_DIR / INDEX_FILE
        self._index: Optional[ProjectIndex] = None
        self._gitignore_patterns: list[str] = []
        self._load_gitignore()

    def get_blob_names(self) -> list[str]:
        """Main entry: load/build index, upload pending, return blob_names."""
        self._load_index()
        old_entries = dict(self._index.entries)
        changed = self._scan_and_update()
        if changed:
            if self._upload_pending():
                self._save_index()
            else:
                self._index.entries = old_entries
        return list(self._index.entries.keys())

    # --- Index persistence ---

    def _load_index(self):
        if self._index is not None:
            return
        if self.index_path.exists():
            try:
                with gzip.open(self.index_path, "rt", encoding="utf-8") as f:
                    data = json.load(f)
                entries = {k: BlobEntry(**v) for k, v in data.get("entries", {}).items()}
                self._index = ProjectIndex(entries=entries, last_indexed=data.get("last_indexed", 0.0))
                return
            except Exception as e:
                log.warning("Failed to load index, rebuilding: %s", e)
        self._index = ProjectIndex()

    def _save_index(self):
        self._index.last_indexed = time.time()
        self.index_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.index_path.with_suffix(".tmp")
        data = {
            "entries": {k: asdict(v) for k, v in self._index.entries.items()},
            "last_indexed": self._index.last_indexed,
        }
        with gzip.open(tmp, "wt", encoding="utf-8") as f:
            json.dump(data, f)
        tmp.replace(self.index_path)

    # --- Scanning ---

    def _scan_and_update(self) -> bool:
        current_files: dict[str, Path] = {}
        for fp in self._walk_files():
            rel = fp.relative_to(self.root).as_posix()
            current_files[rel] = fp

        old_entries = self._index.entries
        new_entries: dict[str, BlobEntry] = {}
        pending_blobs: list[dict] = []
        changed = False

        # Group old entries by base path (strip chunk suffix) for cache hit
        old_by_path: dict[str, list[BlobEntry]] = {}
        for entry in old_entries.values():
            base = entry.path.split("#chunk", 1)[0]
            old_by_path.setdefault(base, []).append(entry)

        for rel, fp in current_files.items():
            try:
                stat = fp.stat()
            except OSError:
                continue
            mtime, size = stat.st_mtime, stat.st_size

            cached_list = old_by_path.get(rel)
            if cached_list and cached_list[0].mtime == mtime and cached_list[0].size == size:
                for cached in cached_list:
                    new_entries[cached.blob_name] = cached
                continue

            blobs = self._process_file(fp, rel)
            if not blobs:
                continue
            changed = True
            for blob_name, path_label, content in blobs:
                new_entries[blob_name] = BlobEntry(path=path_label, blob_name=blob_name, mtime=mtime, size=size)
                if blob_name not in old_entries:
                    pending_blobs.append({"path": path_label, "content": content, "blob_name": blob_name})

        if set(new_entries.keys()) != set(old_entries.keys()):
            changed = True

        self._index.entries = new_entries
        self._pending = pending_blobs
        return changed

    def _walk_files(self):
        for fp in self.root.rglob("*"):
            try:
                if not fp.is_file():
                    continue
            except OSError:
                continue
            rel_parts = fp.relative_to(self.root).parts
            if any(p in EXCLUDE_PATTERNS for p in rel_parts):
                continue
            if any(part.startswith(".") and part != "." for part in rel_parts):
                continue
            if fp.suffix.lower() in BINARY_EXTENSIONS:
                continue
            if fp.suffix.lower() not in TEXT_EXTENSIONS:
                continue
            try:
                if fp.stat().st_size > MAX_BLOB_SIZE:
                    continue
            except OSError:
                continue
            if self._is_gitignored(fp):
                continue
            yield fp

    def _load_gitignore(self):
        gi = self.root / ".gitignore"
        if gi.exists():
            try:
                for line in gi.read_text(encoding="utf-8", errors="ignore").splitlines():
                    line = line.strip()
                    if line and not line.startswith("#"):
                        self._gitignore_patterns.append(line)
            except Exception:
                pass

    def _is_gitignored(self, fp: Path) -> bool:
        rel = fp.relative_to(self.root).as_posix()
        name = fp.name
        for pat in self._gitignore_patterns:
            if fnmatch.fnmatch(name, pat) or fnmatch.fnmatch(rel, pat):
                return True
            clean = pat.rstrip("/")
            if clean in rel.split("/") or rel.startswith(clean + "/"):
                return True
        return False

    # --- File processing ---

    def _process_file(self, fp: Path, rel: str) -> list[tuple[str, str, str]]:
        """Read, sanitize, chunk, hash. Returns [(blob_name, path_label, content), ...]"""
        content = detect_and_read(fp, ENCODING_CHAIN)
        if content is None:
            return []
        content = sanitize_content(content)
        if not content.strip():
            return []

        lines = content.split("\n")
        if len(lines) <= MAX_LINES_PER_BLOB:
            blob_name = self._hash_blob(rel, content)
            return [(blob_name, rel, content)]

        # Chunk large files
        chunks = []
        total_chunks = (len(lines) + MAX_LINES_PER_BLOB - 1) // MAX_LINES_PER_BLOB
        for i in range(total_chunks):
            start = i * MAX_LINES_PER_BLOB
            end = min(start + MAX_LINES_PER_BLOB, len(lines))
            chunk_content = "\n".join(lines[start:end])
            chunk_label = f"{rel}#chunk{i + 1}of{total_chunks}"
            blob_name = self._hash_blob(chunk_label, chunk_content)
            chunks.append((blob_name, chunk_label, chunk_content))
        return chunks

    @staticmethod
    def _hash_blob(path: str, content: str) -> str:
        h = hashlib.sha256()
        h.update(path.encode("utf-8"))
        h.update(content.encode("utf-8"))
        return h.hexdigest()

    # --- Upload ---

    def _upload_pending(self) -> bool:
        if not self._pending or not self.base_url:
            return True

        batches = self._make_batches(self._pending)
        headers = {
            "Content-Type": "application/json",
            "User-Agent": USER_AGENT,
            "Authorization": f"Bearer {self.token}",
            "x-request-session-id": get_session_id(),
        }

        all_ok = True
        for batch in batches:
            payload = {"blobs": [{"path": b["path"], "content": b["content"]} for b in batch]}
            if not self._upload_batch_with_retry(headers, payload):
                all_ok = False

        self._pending = []
        return all_ok

    def _make_batches(self, blobs: list[dict]) -> list[list[dict]]:
        batches = []
        current_batch = []
        current_size = 0
        for b in blobs:
            item_size = len(b["content"].encode("utf-8"))
            if current_batch and (len(current_batch) >= UPLOAD_BATCH_COUNT or current_size + item_size > MAX_BATCH_SIZE):
                batches.append(current_batch)
                current_batch = []
                current_size = 0
            current_batch.append(b)
            current_size += item_size
        if current_batch:
            batches.append(current_batch)
        return batches

    def _upload_batch_with_retry(self, headers: dict, payload: dict, max_retries: int = 3) -> bool:
        url = f"{self.base_url}/batch-upload"
        for attempt in range(max_retries):
            try:
                with httpx.Client(timeout=httpx.Timeout(60.0, connect=15.0)) as client:
                    resp = client.post(url, headers=headers, json=payload)
                    if resp.status_code in (401, 403):
                        log.error("Auth failed (%d) uploading blobs, aborting", resp.status_code)
                        return False
                    if resp.status_code == 429:
                        retry_after = int(resp.headers.get("Retry-After", "5"))
                        log.warning("Rate limited, waiting %ds", retry_after)
                        time.sleep(retry_after)
                        continue
                    if resp.status_code >= 500:
                        wait = 2 ** attempt
                        log.warning("Server error %d, retrying in %ds", resp.status_code, wait)
                        time.sleep(wait)
                        continue
                    resp.raise_for_status()
                    return True
            except httpx.TransportError as e:
                if attempt < max_retries - 1:
                    time.sleep(2 ** attempt)
                    log.warning("Transport error, retrying: %s", e)
                else:
                    log.error("Upload failed after retries: %s", e)
                    return False
        return False
