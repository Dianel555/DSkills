"""Durable upload intent and cooperative, same-platform project locking."""

from __future__ import annotations

import hashlib
import json
import os
import stat
import time
import uuid
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import unquote, urlsplit

try:
    from .secure_fs import AuthorizedRoot, UnsafePathError
    from .templates import INDEX_DIR
except ImportError:
    from secure_fs import AuthorizedRoot, UnsafePathError
    from templates import INDEX_DIR

LOCK_FILE = ".ace-tool.lock"
JOURNAL_FILE = "upload-journal.json"
JOURNAL_VERSION = 1
MAX_JOURNAL_BYTES = 64 * 1024 * 1024
LOCK_WAIT_SECONDS = 300.0
LOCK_MARKER_INIT_SECONDS = 5.0
MAX_UPLOAD_ATTEMPTS = 3


class RecoveryStateError(ValueError):
    """Recovery state or its cooperative lock cannot be trusted."""


class RecoveryBudgetExhaustedError(RecoveryStateError):
    """A possibly sent upload exhausted its persistent retry budget."""


def _missing(exc: BaseException) -> bool:
    return isinstance(exc, FileNotFoundError) or isinstance(exc.__cause__, FileNotFoundError)


def _hash_name(value: object) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(c in "0123456789abcdef" for c in value)


def _service_id(base_url: str, token: str = "") -> str:
    """Identify a service origin and its non-secret API prefix."""
    try:
        parsed = urlsplit(base_url)
        if (
            parsed.scheme.lower() not in {"http", "https"}
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError
        path = parsed.path.rstrip("/")
        decoded = path
        for _ in range(5):
            if token and token in decoded:
                raise ValueError
            decoded_next = unquote(decoded)
            if decoded_next == decoded:
                break
            decoded = decoded_next
        else:
            raise ValueError
        port = parsed.port or (443 if parsed.scheme.lower() == "https" else 80)
        identity = json.dumps([parsed.scheme.lower(), parsed.hostname.lower(), port, path], separators=(",", ":"))
    except ValueError:
        # Do not leak malformed URL fragments through exception chaining.
        raise RecoveryStateError("Upload server URL must not contain credentials, a query, or a fragment") from None
    return hashlib.sha256(identity.encode("utf-8")).hexdigest()


def _platform_marker() -> bytes:
    return b"windows\n" if os.name == "nt" else b"posix\n"


def _lock_fd(fd: int) -> None:
    if os.name == "nt":  # pragma: no cover - exercised on Windows
        import msvcrt

        # Do not lock the marker bytes: another process must read the platform
        # before it can safely contend for the native byte-range lock.
        os.lseek(fd, 32, os.SEEK_SET)
        msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
    else:
        import fcntl

        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)


def _unlock_fd(fd: int) -> None:
    if os.name == "nt":  # pragma: no cover - exercised on Windows
        import msvcrt

        os.lseek(fd, 32, os.SEEK_SET)
        msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
    else:
        import fcntl

        fcntl.flock(fd, fcntl.LOCK_UN)


class UploadRecovery:
    """Project-local state, guarded through scan, upload, and index publication."""

    def __init__(self, root: Path, guard: AuthorizedRoot, base_url: str, token: str = ""):
        self.root = root
        self.guard = guard
        self.project = hashlib.sha256(os.fsencode(os.path.normcase(str(root)))).hexdigest()
        self.service = _service_id(base_url, token) if base_url else None
        self.services: dict[str, dict[str, dict[str, object]]] = {}
        self._anchor = None

    def _open_anchor(self):
        try:
            anchor = self.guard.open_lock_verified((LOCK_FILE,))
        except (FileNotFoundError, UnsafePathError) as exc:
            if not _missing(exc):
                raise RecoveryStateError("Cannot safely open the project upload lock") from exc
            try:
                with self.guard.open_for_write((LOCK_FILE,)) as created:
                    created.write_bytes(_platform_marker())
                    created.flush_to_disk()
            except (FileExistsError, UnsafePathError):
                # A competing process may have created the anchor after our open.
                pass
            try:
                anchor = self.guard.open_lock_verified((LOCK_FILE,))
            except (OSError, UnsafePathError) as open_exc:
                raise RecoveryStateError("Cannot safely create the project upload lock") from open_exc
        deadline = time.monotonic() + LOCK_MARKER_INIT_SECONDS
        while True:
            try:
                info = os.fstat(anchor.fileno())
                if not stat.S_ISREG(info.st_mode) or anchor.link_count != 1:
                    raise RecoveryStateError("Project upload lock is not a private regular file")
                marker = anchor.read_bytes(max_bytes=32)
                if marker == _platform_marker():
                    return anchor
                partial = any(
                    value.startswith(marker) and len(marker) < len(value) for value in (b"windows\n", b"posix\n")
                )
                if not partial or time.monotonic() >= deadline:
                    raise RecoveryStateError("Project upload lock belongs to another platform or is incomplete")
            except BaseException:
                anchor.close()
                raise
            anchor.close()
            time.sleep(min(0.05, max(0.0, deadline - time.monotonic())))
            try:
                anchor = self.guard.open_lock_verified((LOCK_FILE,))
            except (OSError, UnsafePathError) as exc:
                raise RecoveryStateError("Project upload lock is unavailable") from exc

    def verify_anchor(self) -> None:
        """Detect replacement by cooperative peers; arbitrary same-user tampering is unsupported."""
        try:
            with self.guard.open_lock_verified((LOCK_FILE,)) as current:
                held = os.fstat(self._anchor.fileno())
                found = os.fstat(current.fileno())
                if current.link_count != 1 or (held.st_dev, held.st_ino) != (found.st_dev, found.st_ino):
                    raise RecoveryStateError("Project upload lock was replaced")
        except (OSError, UnsafePathError) as exc:
            raise RecoveryStateError("Project upload lock is unavailable") from exc

    @contextmanager
    def locked(self):
        anchor = self._open_anchor()
        acquired = False
        try:
            deadline = time.monotonic() + LOCK_WAIT_SECONDS
            while True:
                try:
                    _lock_fd(anchor.fileno())
                    acquired = True
                    break
                except OSError as exc:
                    if time.monotonic() >= deadline:
                        raise RecoveryStateError("Timed out waiting for the project upload lock") from exc
                    time.sleep(min(0.1, max(0.0, deadline - time.monotonic())))
            self._anchor = anchor
            self.verify_anchor()
            yield self
        finally:
            self._anchor = None
            try:
                if acquired:
                    _unlock_fd(anchor.fileno())
            finally:
                anchor.close()

    def load(self) -> None:
        self.verify_anchor()
        try:
            (self.root / INDEX_DIR).mkdir(exist_ok=True)
            self.guard.verify_directory((INDEX_DIR,))
            try:
                with self.guard.open_verified((INDEX_DIR, JOURNAL_FILE)) as source:
                    if source.link_count != 1:
                        raise RecoveryStateError("Upload recovery journal is hard-linked")
                    raw = source.read_bytes(max_bytes=MAX_JOURNAL_BYTES)
            except (FileNotFoundError, UnsafePathError) as exc:
                if _missing(exc):
                    self.services = {}
                    return
                raise RecoveryStateError("Cannot safely read the upload recovery journal") from exc
            data = json.loads(raw)
            if (
                not isinstance(data, dict)
                or set(data) != {"version", "project", "services"}
                or type(data["version"]) is not int
                or data["version"] != JOURNAL_VERSION
                or data["project"] != self.project
                or not isinstance(data["services"], dict)
            ):
                raise RecoveryStateError("Invalid or incompatible upload recovery journal")
            for service, records in data["services"].items():
                if not _hash_name(service) or not isinstance(records, dict):
                    raise RecoveryStateError("Invalid upload recovery journal")
                for name, record in records.items():
                    if (
                        not _hash_name(name)
                        or not isinstance(record, dict)
                        or set(record) != {"state", "attempts"}
                        or record["state"] not in {"may", "ack"}
                        or type(record["attempts"]) is not int
                        or not 0 <= record["attempts"] <= MAX_UPLOAD_ATTEMPTS
                        or (record["state"] == "may" and record["attempts"] == 0)
                        or (record["state"] == "ack" and record["attempts"] != 0)
                    ):
                        raise RecoveryStateError("Invalid upload recovery journal")
            self.services = data["services"]
        except RecoveryStateError:
            raise
        except (OSError, ValueError, TypeError) as exc:
            raise RecoveryStateError("Cannot load upload recovery state") from exc

    def save(self) -> None:
        self.verify_anchor()
        # An acknowledged blob can be rediscovered with a status query. Only
        # possibly sent uploads need durable attempt history across scans.
        retained = {
            service: pending
            for service, records in self.services.items()
            if (pending := {name: record for name, record in records.items() if record["state"] == "may"})
        }
        data = {"version": JOURNAL_VERSION, "project": self.project, "services": retained}
        raw = json.dumps(data, sort_keys=True, separators=(",", ":")).encode("utf-8")
        if len(raw) > MAX_JOURNAL_BYTES:
            raise RecoveryStateError("Upload recovery journal exceeds its size limit")
        temporary = (INDEX_DIR, f".upload-journal-{uuid.uuid4().hex}.tmp")
        try:
            self.guard.verify_directory((INDEX_DIR,))
            with self.guard.open_for_write(temporary) as out:
                out.write_bytes(raw)
                out.flush_to_disk()
            self.verify_anchor()
            self.guard.publish(temporary, (INDEX_DIR, JOURNAL_FILE))
            self.guard.sync_directory((INDEX_DIR,))
            self.services = retained
        except (OSError, UnsafePathError) as exc:
            raise RecoveryStateError("Cannot persist upload recovery state") from exc

    def records(self) -> dict[str, dict[str, object]]:
        if self.service is None:
            raise RecoveryStateError("Upload recovery requires a server")
        return self.services.setdefault(self.service, {})

    def before_send(self, names: list[str]) -> dict[str, dict[str, object] | None]:
        if not names or not all(_hash_name(name) for name in names):
            raise RecoveryStateError("Invalid upload recovery record")
        records = self.records()
        previous = {}
        updates = {}
        for name in names:
            record = records.get(name)
            attempts = record["attempts"] if record and record["state"] == "may" else 0
            if attempts >= MAX_UPLOAD_ATTEMPTS:
                raise RecoveryBudgetExhaustedError("Upload retry budget exhausted; server outcome remains unknown")
            previous[name] = record.copy() if record else None
            updates[name] = {"state": "may", "attempts": attempts + 1}
        records.update(updates)
        self.save()
        return previous

    def restore_rejected(self, previous: dict[str, dict[str, object] | None]) -> None:
        """Undo only a definitively rejected or unsent attempt, preserving prior uncertainty."""
        records = self.records()
        for name, record in previous.items():
            if record is None:
                records.pop(name, None)
            else:
                records[name] = record
        self.save()

    def acknowledge(self, names: list[str]) -> None:
        if not all(_hash_name(name) for name in names):
            raise RecoveryStateError("Invalid upload recovery record")
        records = self.records()
        if any(name in records for name in names):
            for name in names:
                records.pop(name, None)
            self.save()
