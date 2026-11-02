"""Code indexer: scan, hash, chunk, upload to ACE batch-upload API."""

import fnmatch
import gzip
import hashlib
import json
import logging
import math
import os
import time
import zlib
from calendar import timegm
from dataclasses import asdict, dataclass, field
from email.utils import parsedate_to_datetime
from pathlib import Path

import httpx

try:
    from .secure_fs import AuthorizedRoot, FileTooLargeError, SafeFile, UnsafePathError
    from .templates import (
        BINARY_EXTENSIONS,
        ENCODING_CHAIN,
        EXCLUDE_PATTERNS,
        INDEX_DIR,
        INDEX_FILE,
        MAX_BATCH_SIZE,
        MAX_BLOB_SIZE,
        MAX_LINES_PER_BLOB,
        TEXT_EXTENSIONS,
        UPLOAD_BATCH_COUNT,
        USER_AGENT,
    )
    from .utils import build_api_url, decode_bytes, get_session_id, sanitize_content
except ImportError:
    from secure_fs import AuthorizedRoot, FileTooLargeError, SafeFile, UnsafePathError
    from templates import (
        BINARY_EXTENSIONS,
        ENCODING_CHAIN,
        EXCLUDE_PATTERNS,
        INDEX_DIR,
        INDEX_FILE,
        MAX_BATCH_SIZE,
        MAX_BLOB_SIZE,
        MAX_LINES_PER_BLOB,
        TEXT_EXTENSIONS,
        UPLOAD_BATCH_COUNT,
        USER_AGENT,
    )
    from utils import build_api_url, decode_bytes, get_session_id, sanitize_content

log = logging.getLogger(__name__)
MAX_RETRY_WAIT = 30.0
# Hard cap on the decompressed cache file: a hostile .ace-tool/index.json.gz must
# not be able to exhaust memory while we only wanted to read our own cache.
MAX_INDEX_BYTES = 64 * 1024 * 1024


def _bounded_decompress(raw: bytes, limit: int) -> bytes:
    """Gzip-decompress with a hard output cap; raises ValueError past the limit."""
    decompressor = zlib.decompressobj(31)  # 31 = gzip container
    chunks: list[bytes] = []
    total = 0
    remaining = raw
    while True:
        chunk = decompressor.decompress(remaining, 1 << 20)
        remaining = decompressor.unconsumed_tail
        if not chunk:
            break
        total += len(chunk)
        if total > limit:
            raise ValueError(f"index cache exceeds {limit} decompressed bytes")
        chunks.append(chunk)
        if decompressor.eof and not remaining:
            break
    if not decompressor.eof:
        raise ValueError("index cache is not a complete gzip stream")
    return b"".join(chunks)


def _retry_after_seconds(value: str | None) -> float:
    try:
        try:
            delay = float(value or "5")
        except ValueError:
            date = parsedate_to_datetime(value)
            # A missing zone means GMT, which is what HTTP dates always are.
            delay = timegm(date.timetuple()) if date.tzinfo is None else date.timestamp()
            delay -= time.time()
        if not math.isfinite(delay):
            return 5.0
        return max(0.0, min(MAX_RETRY_WAIT, delay))
    except (TypeError, ValueError, OverflowError):
        return 5.0


class IndexRebuildError(ValueError):
    """Forced re-upload failed. Subclasses ValueError so tenacity-wrapped callers do not retry the full re-upload."""


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
        self.root = self._resolve_root(project_root)
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.index_path = self.root / INDEX_DIR / INDEX_FILE
        # Every read that feeds the index goes through this guard, so a link planted
        # below the requested root is refused instead of followed and its content
        # never reaches the upload payload.
        self._guard = AuthorizedRoot(self.root)
        self._index: ProjectIndex | None = None
        self._gitignore_patterns: list[str] = []
        try:
            self._load_ignore_patterns()
        except BaseException:
            self.close()
            raise

    def close(self) -> None:
        self._guard.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc_info) -> None:
        self.close()

    @staticmethod
    def _resolve_root(project_root: str) -> Path:
        """Keep indexing within the project root requested by the caller."""
        return Path(project_root).resolve()

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

    def force_rebuild(self) -> list[str]:
        """Discard local index state, re-upload every blob (server lost our data)."""
        self._index = ProjectIndex()
        self._scan_and_update()
        if not self._upload_pending():
            raise IndexRebuildError("Failed to re-upload blobs after index rebuild")
        self._save_index()
        return list(self._index.entries.keys())

    # --- Index persistence ---

    def _load_index(self):
        if self._index is not None:
            return
        try:
            raw = self._guard.read_verified((INDEX_DIR, INDEX_FILE))
            data = json.loads(_bounded_decompress(raw, MAX_INDEX_BYTES))
            entries = {k: BlobEntry(**v) for k, v in data.get("entries", {}).items()}
            self._index = ProjectIndex(entries=entries, last_indexed=data.get("last_indexed", 0.0))
            return
        except FileNotFoundError:
            pass  # no cache yet: normal
        except Exception as e:
            # Refused link, oversized/corrupt cache, or unreadable file: rebuild.
            log.warning("Failed to load index, rebuilding: %s", e)
        self._index = ProjectIndex()

    def _save_index(self) -> bool:
        self._index.last_indexed = time.time()
        # Per-process tmp: concurrent same-root writers each publish a fully
        # written file, so a torn index can never be renamed into place.
        data = {
            "entries": {k: asdict(v) for k, v in self._index.entries.items()},
            "last_indexed": self._index.last_indexed,
        }
        tmp_rel = (INDEX_DIR, f"{INDEX_FILE}.{os.getpid()}.tmp")
        try:
            self.index_path.parent.mkdir(parents=True, exist_ok=True)
            # The cache directory must be a real directory below the root, checked
            # before creating the temporary file and again before publishing it, so
            # a link planted at that name cannot redirect the write.
            self._guard.verify_directory((INDEX_DIR,))
            with self._guard.open_for_write(tmp_rel) as tmp:
                tmp.write_bytes(gzip.compress(json.dumps(data, ensure_ascii=False).encode("utf-8")))
            self._guard.verify_directory((INDEX_DIR,))
            for attempt in range(3):
                try:
                    self._guard.publish(tmp_rel, (INDEX_DIR, INDEX_FILE))
                    break
                except PermissionError:
                    # Windows refuses to replace a target a concurrent reader
                    # briefly holds open; genuine ACL errors still propagate.
                    if attempt == 2:
                        raise
                    time.sleep(0.05 * (2**attempt))
        except FileNotFoundError as e:
            # A concurrent operation removed the cache directory during save.
            log.warning("Index dir vanished during save: %s", e)
            return False
        except UnsafePathError as e:
            # The cache path is a link or otherwise outside the authorized root.
            log.warning("Refusing to write index cache: %s", e)
            return False
        return True

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

        for rel in current_files:
            try:
                # Open through the guard: the metadata used for the cache decision and
                # the bytes that get uploaded both come from this one verified object.
                with self._guard.open_verified(rel.split("/")) as safe:
                    mtime, size = safe.mtime, safe.size

                    cached_list = old_by_path.get(rel)
                    if cached_list and cached_list[0].mtime == mtime and cached_list[0].size == size:
                        for cached in cached_list:
                            new_entries[cached.blob_name] = cached
                        continue

                    blobs = self._process_file(safe, rel)
            except (UnsafePathError, FileTooLargeError) as e:
                log.debug("skipping %s: %s", rel, e)
                continue
            except OSError:
                continue
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

    def _load_ignore_patterns(self):
        seen = set()
        for filename in (".gitignore", ".aceignore"):
            try:
                text = self._guard.read_verified((filename,)).decode("utf-8", errors="ignore")
            except (UnsafePathError, OSError):
                continue  # absent, or a link we refuse to follow
            for line in text.splitlines():
                line = line.strip()
                if line and not line.startswith("#") and line not in seen:
                    seen.add(line)
                    self._gitignore_patterns.append(line)

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

    def _process_file(self, safe: SafeFile, rel: str) -> list[tuple[str, str, str]]:
        """Read, sanitize, chunk, hash. Returns [(blob_name, path_label, content), ...]"""
        try:
            raw = safe.read_bytes(MAX_BLOB_SIZE)
        except FileTooLargeError:
            return []
        content = decode_bytes(raw, ENCODING_CHAIN)
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
            if current_batch and (
                len(current_batch) >= UPLOAD_BATCH_COUNT or current_size + item_size > MAX_BATCH_SIZE
            ):
                batches.append(current_batch)
                current_batch = []
                current_size = 0
            current_batch.append(b)
            current_size += item_size
        if current_batch:
            batches.append(current_batch)
        return batches

    def _upload_batch_with_retry(self, headers: dict, payload: dict, max_retries: int = 3) -> bool:
        url = build_api_url(self.base_url, "/batch-upload")
        for attempt in range(max_retries):
            try:
                with httpx.Client(timeout=httpx.Timeout(60.0, connect=15.0)) as client:
                    resp = client.post(url, headers=headers, json=payload)
                    if resp.status_code in (401, 403):
                        log.error("Auth failed (%d) uploading blobs, aborting", resp.status_code)
                        return False
                    if resp.status_code == 429:
                        if attempt == max_retries - 1:
                            return False
                        retry_after = _retry_after_seconds(resp.headers.get("Retry-After"))
                        log.warning("Rate limited, waiting %gs", retry_after)
                        time.sleep(retry_after)
                        continue
                    if resp.status_code >= 500:
                        if attempt == max_retries - 1:
                            return False
                        wait = min(MAX_RETRY_WAIT, 2 ** min(attempt, 5))
                        log.warning("Server error %d, retrying in %gs", resp.status_code, wait)
                        time.sleep(wait)
                        continue
                    resp.raise_for_status()
                    return True
            except httpx.TransportError as e:
                if attempt < max_retries - 1:
                    time.sleep(min(MAX_RETRY_WAIT, 2 ** min(attempt, 5)))
                    log.warning("Transport error, retrying: %s", e)
                else:
                    log.error("Upload failed after retries: %s", e)
                    return False
        return False
