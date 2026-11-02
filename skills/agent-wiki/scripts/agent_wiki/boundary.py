"""Verified filesystem access for one vault.

Security property enforced here: every byte read or written by the tool comes from, or
goes to, an object that the operating system resolved - at open time - to a real file or
directory inside the vault. A directory link (POSIX symlink or Windows junction) planted
inside the vault can therefore never make the tool read, publish, write or delete
anything outside it, and swapping a path between a check and its use cannot either.

Why re-checking a path is not enough: ``Path.resolve()``, ``is_symlink()`` and
``Path.stat()`` describe a path at one instant. Somebody who can write inside the vault
can replace a component with a link after the check and before the later
``open()``/``read()``/``replace()`` (TOCTOU). Verification here is performed on the
opened object itself:

* POSIX: every component is opened relative to the previous component's directory
  descriptor with ``O_NOFOLLOW``, so a link at any component fails the open (``ELOOP``)
  and the request is refused instead of followed. Directory handles keep their
  descriptor, so writes, replacements and unlinks are descriptor-relative.
* Windows: the object is opened with ``FILE_FLAG_OPEN_REPARSE_POINT`` (never following a
  final link), the handle is checked for ``FILE_ATTRIBUTE_REPARSE_POINT`` (refuses link
  leaves such as junctions and symlinks), and ``GetFinalPathNameByHandleW`` is compared
  with the vault root. A link at an intermediate component shows up as the real target in
  that final path, so it is refused **when it leaves the vault**; Windows has no
  ``O_NOFOLLOW`` equivalent for intermediate components, so a link that stays inside the
  vault is still accepted there - POSIX refuses every link, Windows only refuses links
  that would escape the vault. Creation therefore never happens on a path that has not
  had its parent verified and held first (see ``_open_held_windows``). An output
  directory is additionally opened without ``FILE_SHARE_DELETE``, which makes Windows
  refuse to rename or remove that directory for anybody while the tool holds it - the
  practical substitute for descriptor-relative mutation that ``dir_fd`` cannot provide on
  Windows. Measured on Windows while such a handle is held: renaming the directory itself
  fails with WinError 32 and renaming any ancestor of it (verified up to the temporary
  directory the vault lives in) fails with WinError 5, while the same renames succeed
  without the handle. Holding the deepest output directory therefore pins its whole
  ancestor chain against the path swaps the descriptor approach would stop on POSIX.

Both platforms then read and write through the descriptor/handle that was verified, so
the content cannot be swapped for another object after the check.

Known limits (recorded rather than silently ignored):

* POSIX mount points are not distinguishable from directories with ``O_NOFOLLOW``;
  creating one needs privileges the same-user threat model does not assume.
* Hard links keep the final path inside the vault while pointing at an inode that is
  also reachable elsewhere on the same volume. They are exposed through
  ``Entry.link_count`` rather than rejected, because legitimate vaults use them.
* The vault root itself comes from the caller (``Path.resolve()`` follows links in the
  root the user explicitly named); only paths below it are constrained.
* Every path must be covered by a root registered with :func:`bind`. A path that no
  registered root covers is refused rather than re-anchored at its own parent: the
  caller's explicit vault is the capability, and inventing a new one from the argument
  would hand out access nobody authorized.
"""

from __future__ import annotations

import ctypes
import errno
import os
import secrets
import stat as stat_module
from collections.abc import Iterator
from pathlib import Path
from types import TracebackType
from typing import IO

_GENERIC_READ = 0x80000000
_GENERIC_WRITE = 0x40000000
_FILE_LIST_DIRECTORY = 0x00000001
_FILE_READ_ATTRIBUTES = 0x00000080
_FILE_SHARE_READ = 0x00000001
_FILE_SHARE_WRITE = 0x00000002
_FILE_SHARE_DELETE = 0x00000004
_FILE_SHARE_ALL = _FILE_SHARE_READ | _FILE_SHARE_WRITE | _FILE_SHARE_DELETE
_OPEN_EXISTING = 3
_CREATE_NEW = 1
_FILE_ATTRIBUTE_REPARSE_POINT = 0x00000400
_FILE_ATTRIBUTE_DIRECTORY = 0x00000010
_FILE_FLAG_BACKUP_SEMANTICS = 0x02000000
_FILE_FLAG_OPEN_REPARSE_POINT = 0x00200000
_ERROR_FILE_NOT_FOUND = 2
_ERROR_PATH_NOT_FOUND = 3
_ERROR_ALREADY_EXISTS = 183
_FILE_ATTRIBUTE_NORMAL = 0x00000080

# These flags exist only on POSIX; 0 keeps the same expressions portable to Windows,
# where the branch that uses them never runs.
_O_CLOEXEC = getattr(os, "O_CLOEXEC", 0)
_O_DIRECTORY = getattr(os, "O_DIRECTORY", 0)
_O_NOFOLLOW = getattr(os, "O_NOFOLLOW", 0)
_O_NONBLOCK = getattr(os, "O_NONBLOCK", 0)
_ERROR_PATH_NOT_FOUND = 3
# ctypes sign-extends the 32-bit INVALID_HANDLE_VALUE into a 64-bit pointer value.
_INVALID_HANDLE = 0xFFFFFFFFFFFFFFFF
# How many random temporary names to try before giving up: a collision is retried, never
# resolved by deleting whatever already occupies the name.
_TEMP_ATTEMPTS = 8


def _validate_name(name: str) -> str:
    """Refuse anything that is not a single safe path component.

    ``DirectoryHandle`` methods take a bare leaf name and open it relative to a
    descriptor, so the name must never carry a separator, a parent reference, a drive
    letter or an NTFS alternate-data-stream qualifier: any of those would step outside
    the directory the caller verified. ``VaultFS`` hands these methods one component of
    an already normalized path, so this is a boundary assertion rather than a filter
    over user input.
    """
    if not name or name in (".", ".."):
        raise BoundaryError(f"refusing invalid file name {name!r}")
    if "/" in name or "\\" in name or os.sep in name or (os.altsep and os.altsep in name):
        raise BoundaryError(f"refusing file name containing a path separator: {name!r}")
    if "\x00" in name:
        raise BoundaryError(f"refusing file name containing a null byte: {name!r}")
    if os.name == "nt" and ":" in name:
        # A colon introduces a drive qualifier or an alternate data stream, neither of
        # which is a name this boundary may create.
        raise BoundaryError(f"refusing file name containing a colon: {name!r}")
    return name


def _temp_name(name: str) -> str:
    """A random, unguessable temporary name beside ``name``."""
    return f".{name}.{os.getpid()}.{secrets.token_hex(8)}.tmp"


class BoundaryError(OSError):
    """The path did not resolve to a contained object below the authorized root.

    ``is_link`` marks the refusals that were caused by a directory link (symlink,
    junction, mount point) rather than by the path pointing outside the root, so
    callers can tell "there is nothing usable here" from "this is a link".
    """

    def __init__(self, *args: object, is_link: bool = False) -> None:
        super().__init__(*args)
        self.is_link = is_link


if os.name == "nt":  # pragma: no cover - loaded only on Windows
    import msvcrt
    from ctypes import wintypes

    _kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

    _kernel32.CreateFileW.argtypes = (
        wintypes.LPCWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.LPVOID,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.HANDLE,
    )
    _kernel32.CreateFileW.restype = wintypes.HANDLE
    _kernel32.GetFinalPathNameByHandleW.argtypes = (
        wintypes.HANDLE,
        wintypes.LPWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
    )
    _kernel32.GetFinalPathNameByHandleW.restype = wintypes.DWORD
    _kernel32.GetFileInformationByHandle.argtypes = (wintypes.HANDLE, ctypes.c_void_p)
    _kernel32.GetFileInformationByHandle.restype = wintypes.BOOL
    _kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
    _kernel32.CloseHandle.restype = wintypes.BOOL

    # FileRenameInfo: publish a temporary file under a verified name by handle, so the
    # destination is never re-resolved from a path after the check.
    _FILE_RENAME_INFO = 3

    class _FileRenameInfo(ctypes.Structure):  # noqa: N801 - mirrors the Windows struct name
        _fields_ = [
            ("ReplaceIfExists", wintypes.BOOL),
            ("RootDirectory", wintypes.HANDLE),
            ("FileNameLength", wintypes.DWORD),
            ("FileName", wintypes.WCHAR * 1),
        ]

    def _rename_by_handle(handle: int, destination: str, *, replace: bool = True) -> None:
        """Rename the object behind ``handle`` to ``destination`` (a full path)."""
        raw = destination.encode("utf-16-le")
        buf = ctypes.create_string_buffer(ctypes.sizeof(_FileRenameInfo) + len(raw))
        info = _FileRenameInfo.from_buffer(buf)
        info.ReplaceIfExists = replace
        info.FileNameLength = len(raw)
        ctypes.memmove(
            ctypes.byref(info, _FileRenameInfo.FileName.offset), raw, len(raw)
        )
        if not _kernel32.SetFileInformationByHandle(
            handle, _FILE_RENAME_INFO, buf, ctypes.sizeof(buf)
        ):
            err = ctypes.get_last_error()
            if not replace and err in (80, _ERROR_ALREADY_EXISTS):
                raise FileExistsError(errno.EEXIST, "destination exists", destination)
            raise BoundaryError(f"cannot publish {destination}: WinError {err}")

    _kernel32.SetFileInformationByHandle.argtypes = (
        wintypes.HANDLE,
        wintypes.DWORD,
        wintypes.LPVOID,
        wintypes.DWORD,
    )
    _kernel32.SetFileInformationByHandle.restype = wintypes.BOOL
    _GENERIC_DELETE = 0x00010000
    _SYNCHRONIZE = 0x00100000

    class _ByHandleFileInformation(ctypes.Structure):  # noqa: N801 - mirrors the Windows struct name
        _fields_ = [
            ("dwFileAttributes", wintypes.DWORD),
            ("ftCreationTime", wintypes.FILETIME),
            ("ftLastAccessTime", wintypes.FILETIME),
            ("ftLastWriteTime", wintypes.FILETIME),
            ("dwVolumeSerialNumber", wintypes.DWORD),
            ("nFileSizeHigh", wintypes.DWORD),
            ("nFileSizeLow", wintypes.DWORD),
            ("nNumberOfLinks", wintypes.DWORD),
            ("nFileIndexHigh", wintypes.DWORD),
            ("nFileIndexLow", wintypes.DWORD),
        ]

    def _final_path(handle: int) -> str:
        needed = _kernel32.GetFinalPathNameByHandleW(handle, None, 0, 0)
        if needed == 0:
            raise ctypes.WinError(ctypes.get_last_error())
        buf = ctypes.create_unicode_buffer(needed + 1)
        if _kernel32.GetFinalPathNameByHandleW(handle, buf, needed + 1, 0) == 0:
            raise ctypes.WinError(ctypes.get_last_error())
        return buf.value

    def _native_path(path: str) -> str:
        """Use a handle's final path for IO without changing its on-disk case."""
        if path.startswith("\\\\?\\UNC\\"):
            path = "\\\\" + path[len("\\\\?\\UNC\\") :]
        elif path.startswith("\\\\?\\"):
            path = path[len("\\\\?\\") :]
        return os.path.normpath(path)

    def _normalize(path: str) -> str:
        """Comparison key only; never use the case-folded result for IO."""
        return os.path.normcase(_native_path(path))

else:

    def _final_path(handle: int) -> str:  # pragma: no cover - unused on POSIX
        raise NotImplementedError

    def _native_path(path: str) -> str:  # pragma: no cover - unused on POSIX
        raise NotImplementedError

    def _normalize(path: str) -> str:  # pragma: no cover - unused on POSIX
        raise NotImplementedError


def _publish_tmp(dir_fd: int, tmp_name: str, destination: Path, fd: int) -> None:
    """Make the temporary file ``tmp_name`` become ``destination``.

    This is the single replace step. It is kept as one function because the two
    platforms issue the rename through different primitives, and callers/tests need
    one injection point: POSIX renames inside the held directory descriptor,
    Windows renames the very object it created (a handle-based rename needs DELETE
    access, which ``os.open`` does not request).
    """
    if os.name == "posix":
        os.replace(tmp_name, destination.name, src_dir_fd=dir_fd, dst_dir_fd=dir_fd)
        return
    _rename_by_handle(msvcrt.get_osfhandle(fd), str(destination))


def _move_noreplace_posix(src_fd: int, src: str, dst_fd: int, dst: str) -> None:
    """Move a directory entry atomically, never replacing an existing destination.

    Ordinary POSIX rename overwrites; link-then-unlink and check-then-rename both
    leave a source replacement race. Linux renameat2(RENAME_NOREPLACE) and Darwin
    renameatx_np(RENAME_EXCL) provide the required single operation. Unsupported
    systems/filesystems fail closed; never fall back to copying and unlinking.
    """
    libc = ctypes.CDLL(None, use_errno=True)
    rename = getattr(libc, "renameat2", None)
    flag = 1  # Linux RENAME_NOREPLACE
    if rename is None:
        rename = getattr(libc, "renameatx_np", None)
        flag = 4  # Darwin RENAME_EXCL
    if rename is None:
        raise BoundaryError(errno.ENOTSUP, "atomic no-replace move unavailable")
    rename.argtypes = (ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint)
    rename.restype = ctypes.c_int
    if rename(src_fd, os.fsencode(src), dst_fd, os.fsencode(dst), flag) != 0:
        err = ctypes.get_errno()
        raise OSError(err, os.strerror(err), dst)


def _is_reparse_entry(entry: os.DirEntry[str]) -> bool:
    """True for symlinks, junctions and other reparse points on either platform."""
    if entry.is_symlink():
        return True
    try:
        attrs = entry.stat(follow_symlinks=False).st_file_attributes
    except (OSError, AttributeError):
        return False
    return bool(attrs & _FILE_ATTRIBUTE_REPARSE_POINT)


class Entry:
    """A regular file below the vault root whose object was verified at open time."""

    def __init__(self, fs: VaultFS, path: Path, link_count: int | None = None, is_link: bool = False):
        self._fs = fs
        self.path = path
        self.name = path.name
        self.stem = path.stem
        self.link_count = link_count
        self.is_link = is_link

    def read_bytes(self) -> bytes:
        return self._fs.read_bytes(self.path)

    def read_text(self, encoding: str = "utf-8-sig", errors: str = "strict") -> str:
        return self._fs.read_text(self.path, encoding=encoding, errors=errors)

    def stat(self) -> os.stat_result | None:
        return self._fs.stat(self.path)

    def write_bytes(self, data: bytes) -> None:
        self._fs.write_text(self.path, data)

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<Entry {self.path}>"


class DirectoryHandle:
    """A verified directory used for the whole lifetime of one output operation.

    On POSIX every mutation is descriptor-relative, so the directory cannot be swapped
    for a link mid-operation. On Windows the handle is opened without
    ``FILE_SHARE_DELETE``, which makes the OS refuse to rename or remove the directory
    while it is held; leaf operations refuse reparse points and create their temporary
    file exclusively, so a swapped leaf cannot redirect a write or a delete.
    """

    def __init__(self, fs: VaultFS, path: Path, fd: int):
        self._fs = fs
        self.path = path
        self._fd = fd
        if os.name == "nt":
            # Pinning the resolved directory does not pin intermediate junction
            # aliases. Never reuse the caller's alias for a mutation after opening.
            try:
                final = _final_path(msvcrt.get_osfhandle(fd))
                if not fs._contains(final):
                    raise BoundaryError(f"{path} resolves outside the vault")
                self.path = Path(_native_path(final))
            except BaseException:
                self.close()
                raise

    def names(self, suffix: str | None = None) -> list[str]:
        """Names of real (non-link) entries directly inside the directory."""
        if os.name == "posix":
            found: list[str] = []
            with os.scandir(self._fd) as scan:
                for item in scan:
                    if _is_reparse_entry(item):
                        continue
                    if suffix is not None and not item.name.endswith(suffix):
                        continue
                    found.append(item.name)
            return sorted(found)
        found = []
        for item in os.scandir(self.path):
            if _is_reparse_entry(item):
                continue
            if suffix is not None and not item.name.endswith(suffix):
                continue
            found.append(item.name)
        return sorted(found)

    def entries(self, suffix: str | None = None) -> list[Entry]:
        out: list[Entry] = []
        for name in self.names(suffix):
            path = self.path / name
            try:
                st = self._fs.stat(path)
            except BoundaryError:
                continue
            if st is None or not stat_module.S_ISREG(st.st_mode):
                continue
            out.append(Entry(self._fs, path, link_count=getattr(st, "st_nlink", None)))
        return out

    def move_to(self, name: str, destination: DirectoryHandle, new_name: str) -> None:
        """Atomically move an entry between held directories without clobbering.

        A newer entry installed at the source name is moved intact, never deleted
        after copying stale bytes. POSIX moves the entry itself (not a symlink's
        target); Windows renames a verified source handle while denying writers
        and deletion. Cross-filesystem and unsupported moves fail without a copy
        fallback. Both endpoints must belong to the same authorized vault.
        """
        _validate_name(name)
        _validate_name(new_name)
        if self._fs.root != destination._fs.root:
            raise BoundaryError("refusing a move across vault boundaries")
        if os.name == "posix":
            st = os.stat(name, dir_fd=self._fd, follow_symlinks=False)
            if not stat_module.S_ISREG(st.st_mode):
                raise BoundaryError(f"refusing non-file {self.path / name}", is_link=True)
            _move_noreplace_posix(self._fd, name, destination._fd, new_name)
            return
        path = self.path / name
        handle = _kernel32.CreateFileW(
            str(path),
            _GENERIC_DELETE | _FILE_READ_ATTRIBUTES | _SYNCHRONIZE,
            _FILE_SHARE_READ,
            None,
            _OPEN_EXISTING,
            _FILE_FLAG_OPEN_REPARSE_POINT | _FILE_FLAG_BACKUP_SEMANTICS,
            None,
        )
        if not handle or handle == _INVALID_HANDLE:
            raise ctypes.WinError(ctypes.get_last_error())
        try:
            info = _ByHandleFileInformation()
            if not _kernel32.GetFileInformationByHandle(handle, ctypes.byref(info)):
                raise ctypes.WinError(ctypes.get_last_error())
            if info.dwFileAttributes & (_FILE_ATTRIBUTE_REPARSE_POINT | _FILE_ATTRIBUTE_DIRECTORY):
                raise BoundaryError(f"refusing non-file {path}", is_link=True)
            if not self._fs._contains(_final_path(handle)):
                raise BoundaryError(f"{path} resolves outside the vault")
            _rename_by_handle(handle, str(destination.path / new_name), replace=False)
        finally:
            _kernel32.CloseHandle(handle)

    def write_atomic(self, name: str, data: str | bytes) -> None:
        """Publish ``name`` inside this directory via an exclusive temporary file.

        The temporary name is random and created with ``O_EXCL``, so a name that is
        already taken is retried with a fresh one instead of touching whatever occupies
        it. POSIX creates, writes and replaces it relative to the held directory
        descriptor. Windows creates it inside the directory this handle pins (opened
        without ``FILE_SHARE_DELETE``) and publishes it with
        ``SetFileInformationByHandle``, so the destination is never re-resolved from a
        path after it was checked. Atomicity is about visibility, not durability: a
        crash between the write and the rename can leave the old file in place, and
        neither platform fsyncs here.
        """
        payload = data if isinstance(data, bytes) else data.encode("utf-8")
        _validate_name(name)
        if os.name == "posix":
            for _ in range(_TEMP_ATTEMPTS):
                tmp_name = _temp_name(name)
                try:
                    fd = os.open(
                        tmp_name,
                        os.O_WRONLY | os.O_CREAT | os.O_EXCL | _O_CLOEXEC,
                        0o600,
                        dir_fd=self._fd,
                    )
                except FileExistsError:
                    continue
                try:
                    with os.fdopen(fd, "wb") as handle:
                        handle.write(payload)
                    _publish_tmp(self._fd, tmp_name, self.path / name, -1)
                except BaseException:
                    with SuppressOSError():
                        os.unlink(tmp_name, dir_fd=self._fd)
                    raise
                return
            raise BoundaryError(f"cannot create a temporary file beside {name}")
        # Windows: the held handle pins the directory, so the temporary file is
        # created inside the directory that was verified, and publishing renames it by
        # handle. Renaming a handle requires DELETE access on it, so the temporary file
        # is opened directly rather than through ``os.open`` (which would ask for
        # GENERIC_WRITE only and fail with access denied at publish time).
        destination = self.path / name
        self._fs._refuse_reparse(destination)
        for _ in range(_TEMP_ATTEMPTS):
            tmp_path = self.path / _temp_name(name)
            handle = _kernel32.CreateFileW(
                str(tmp_path),
                _GENERIC_WRITE | _GENERIC_DELETE | _SYNCHRONIZE,
                _FILE_SHARE_ALL,
                None,
                _CREATE_NEW,
                _FILE_ATTRIBUTE_NORMAL,
                None,
            )
            if not handle or handle == _INVALID_HANDLE:
                err = ctypes.get_last_error()
                if err == _ERROR_ALREADY_EXISTS:
                    continue
                if err in (_ERROR_FILE_NOT_FOUND, _ERROR_PATH_NOT_FOUND):
                    raise BoundaryError(f"missing {tmp_path}", is_link=True) from None
                raise BoundaryError(f"cannot create {tmp_path}: WinError {err}")
            fd = -1
            try:
                fd = msvcrt.open_osfhandle(handle, os.O_WRONLY | os.O_BINARY)
                view = memoryview(payload)
                while view:
                    view = view[os.write(fd, view) :]
                # Rename the very object we created: no path is resolved again, so a
                # destination swapped in the meantime is replaced, not written through.
                _publish_tmp(-1, tmp_path.name, destination, fd)
            except BaseException:
                if fd >= 0:
                    with SuppressOSError():
                        os.close(fd)
                else:
                    _kernel32.CloseHandle(handle)
                with SuppressOSError():
                    os.unlink(tmp_path)
                raise
            if fd >= 0:
                os.close(fd)
            return
        raise BoundaryError(f"cannot create a temporary file beside {name}")

    def append_atomic(self, name: str, data: str | bytes) -> None:
        """Append to ``name`` inside this directory without ever following a link.

        There is no atomic append, so the file is opened (never following a link) and
        written through that descriptor. On POSIX the open is relative to the held
        directory descriptor with ``O_NOFOLLOW``; on Windows the leaf is opened with
        ``FILE_FLAG_OPEN_REPARSE_POINT`` and the resulting handle is checked for a
        reparse point and for containment, so a leaf swapped for a link between the
        check and the write is refused instead of appended to.
        """
        payload = data if isinstance(data, bytes) else data.encode("utf-8")
        _validate_name(name)
        if os.name == "posix":
            # O_NOFOLLOW makes the open itself refuse a link leaf: appending through
            # one would write the caller's data into a file outside the vault.
            flags = os.O_WRONLY | os.O_APPEND | os.O_CREAT | _O_NOFOLLOW | _O_CLOEXEC
            try:
                fd = os.open(name, flags, 0o600, dir_fd=self._fd)
            except OSError as exc:
                if exc.errno in (errno.ELOOP, errno.ENOTDIR):
                    raise BoundaryError(f"refusing link {self.path / name}", is_link=True) from exc
                raise
            try:
                view = memoryview(payload)
                while view:
                    view = view[os.write(fd, view) :]
            finally:
                os.close(fd)
            return
        # Windows: open the leaf without following it and verify the opened object,
        # rather than checking the path and then opening it (a raced swap would win).
        # ``create=False`` opens the existing file; a missing log file is created by
        # the caller through ``ensure_directory`` + ``write_text``.
        parts = self._fs.rel_parts(self.path / name)
        handle, _links = self._fs._open_windows(
            parts, write=True, want_directory=False, create=False
        )
        path = str(self.path / name)
        fd = self._fs._adopt_windows(handle, path, write=True, append=True)
        try:
            view = memoryview(payload)
            while view:
                view = view[os.write(fd, view) :]
        finally:
            os.close(fd)

    def unlink(self, name: str) -> None:
        _validate_name(name)
        if os.name == "posix":
            os.unlink(name, dir_fd=self._fd)
            return
        self._fs._refuse_reparse(self.path / name)
        os.unlink(self.path / name)

    def close(self) -> None:
        if self._fd >= 0:
            fd, self._fd = self._fd, -1
            with SuppressOSError():
                os.close(fd)

    def __enter__(self) -> DirectoryHandle:
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()


class SuppressOSError:
    """Minimal contextlib.suppress(OSError) without importing contextlib everywhere."""

    def __enter__(self) -> None:
        return None

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> bool:
        return exc_type is not None and issubclass(exc_type, OSError)


class VaultFS:
    """Guards file access below one authorized root directory."""

    def __init__(self, root: Path):
        # The caller names the root; resolving it once fixes the boundary object.
        self.root = Path(root).expanduser().resolve()
        self._dir_fd = -1
        self._win_prefix = ""
        if os.name == "posix":
            self._dir_fd = os.open(self.root, os.O_RDONLY | _O_DIRECTORY | _O_CLOEXEC)
        else:
            self._win_prefix = _normalize(str(self.root))

    # --- path handling ---

    def rel_parts(self, path: Path) -> tuple[str, ...]:
        """Relative components of ``path`` below the root, or refuse.

        Matching is lexical on purpose. Resolving here would follow a link planted
        inside the vault and hand back the components of *its* target, which is the very
        decision the open has to make on the object that is really there. Keeping the
        caller's names means every component is then opened without following it
        (``O_NOFOLLOW`` on POSIX, reparse and containment checks on Windows), so a link
        anywhere on the path is still refused - one component at a time.
        """
        candidate = Path(path)
        if not candidate.is_absolute():
            candidate = Path.cwd() / candidate
        candidate = Path(os.path.normpath(candidate.expanduser()))
        try:
            rel = candidate.relative_to(self.root)
        except ValueError as exc:
            # Tolerate a different case or separator spelling of the root itself; the
            # components below it keep the caller's spelling.
            if not _shares_prefix(candidate, self.root):
                raise BoundaryError(f"{path} is outside the vault {self.root}") from exc
            rel = (
                Path(*candidate.parts[len(self.root.parts) :])
                if len(candidate.parts) > len(self.root.parts)
                else Path(".")
            )
        parts = rel.parts
        if any(part in ("", ".", "..") for part in parts):
            raise BoundaryError(f"invalid relative path {path!r}")
        return tuple(str(part) for part in parts)

    def _is_root(self, candidate: Path) -> bool:
        """True when ``candidate`` names the authorized root itself (spelling-tolerant)."""
        return len(candidate.parts) == len(self.root.parts) and _shares_prefix(candidate, self.root)

    def _dup_root_fd(self) -> int:
        """Duplicate the authorized root descriptor (POSIX) or open the root afresh.

        POSIX callers get a duplicate of the descriptor captured at construction time,
        so later renames/link swaps of the root *name* cannot redirect them. On Windows
        there is no storable anchor descriptor, so callers get a fresh validated open.
        """
        if os.name == "nt":
            handle, _links = self._open_windows((), write=False, want_directory=True)
            return handle
        return os.dup(self._dir_fd)

    # --- POSIX implementation ---

    def _open_posix(self, parts: tuple[str, ...], write: bool, want_directory: bool | None) -> int:
        if not parts:
            # The root itself. It is always a directory, so only a directory open makes
            # sense. Duplicate the authorized descriptor instead of reopening by path:
            # if the root has been renamed and its old name replaced by a link, a path
            # reopen would follow the link outside the authorization decision made at
            # construction time.
            if want_directory is False:
                raise BoundaryError(f"{self.root} is a directory, not a file")
            return self._dup_root_fd()
        parents: list[int] = []
        try:
            parent = self._dir_fd
            for part in parts[:-1]:
                fd = os.open(
                    part,
                    os.O_RDONLY | _O_DIRECTORY | _O_NOFOLLOW | _O_CLOEXEC,
                    dir_fd=parent,
                )
                parents.append(fd)
                parent = fd
            flags = os.O_RDONLY
            if write:
                flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
            elif want_directory:
                flags = os.O_RDONLY | _O_DIRECTORY
            elif want_directory is None:
                # Metadata lookups: accept either kind and let the caller inspect fstat.
                flags = os.O_RDONLY | _O_NONBLOCK
            leaf = os.open(parts[-1], flags | _O_NOFOLLOW | _O_CLOEXEC, 0o600, dir_fd=parent)
        except OSError as exc:
            for fd in parents:
                os.close(fd)
            raise _as_not_found(exc, self.root.joinpath(*parts)) from exc
        for fd in parents:
            os.close(fd)
        return leaf

    def _verify_dir_posix(self, parts: tuple[str, ...]) -> int:
        """Open (never follow) every component and return the deepest descriptor.

        The returned descriptor *is* the verified directory, so the caller never has to
        re-resolve a path to use it: closing and reopening by name would reopen the race
        this module exists to close.
        """
        if not parts:
            return self._dup_root_fd()
        fds: list[int] = []
        try:
            parent = self._dir_fd
            for part in parts:
                fd = os.open(
                    part,
                    os.O_RDONLY | _O_DIRECTORY | _O_NOFOLLOW | _O_CLOEXEC,
                    dir_fd=parent,
                )
                fds.append(fd)
                parent = fd
        except OSError as exc:
            for fd in fds:
                with SuppressOSError():
                    os.close(fd)
            raise _as_not_found(exc, self.root.joinpath(*parts)) from exc
        for fd in fds[:-1]:
            os.close(fd)
        return fds[-1]

    # --- Windows implementation ---

    def _open_windows(
        self,
        parts: tuple[str, ...],
        write: bool,
        want_directory: bool | None,
        share_delete: bool = True,
        create: bool | None = None,
    ) -> tuple[int, int]:
        """Open and fully verify one object, returning its raw Windows handle."""
        if create is None:
            create = write
        path = str(self.root.joinpath(*parts))
        # Listing a directory needs FILE_LIST_DIRECTORY; a leaf needs read or write.
        access = (
            _GENERIC_READ | _FILE_LIST_DIRECTORY
            if want_directory
            else _GENERIC_WRITE if write else _GENERIC_READ
        )
        disposition = _CREATE_NEW if create else _OPEN_EXISTING
        # A held output directory is opened without FILE_SHARE_DELETE so Windows refuses
        # to rename or remove it while we work inside it.
        share = _FILE_SHARE_ALL if share_delete else (_FILE_SHARE_READ | _FILE_SHARE_WRITE)
        flags = _FILE_FLAG_BACKUP_SEMANTICS | _FILE_FLAG_OPEN_REPARSE_POINT
        handle = _kernel32.CreateFileW(path, access, share, None, disposition, flags, None)
        if not handle or handle == _INVALID_HANDLE:
            err = ctypes.get_last_error()
            if err in (_ERROR_FILE_NOT_FOUND, _ERROR_PATH_NOT_FOUND):
                raise FileNotFoundError(err, f"missing {path}")
            raise BoundaryError(f"refusing {path}: WinError {err}")
        try:
            info = _ByHandleFileInformation()
            if not _kernel32.GetFileInformationByHandle(handle, ctypes.byref(info)):
                raise BoundaryError(
                    f"cannot stat handle for {path}: WinError {ctypes.get_last_error()}"
                )
            if info.dwFileAttributes & _FILE_ATTRIBUTE_REPARSE_POINT:
                # The opened object is itself a link (junction, symlink, mount point).
                raise BoundaryError(f"refusing reparse point {path}", is_link=True)
            final = _final_path(handle)
            if not self._contains(final):
                # An intermediate component was a link: the handle names the real target.
                raise BoundaryError(f"{path} resolves outside the vault to {final}")
            if want_directory is True and not (info.dwFileAttributes & _FILE_ATTRIBUTE_DIRECTORY):
                raise BoundaryError(f"{path} is not a directory")
            if want_directory is False and (info.dwFileAttributes & _FILE_ATTRIBUTE_DIRECTORY):
                raise BoundaryError(f"{path} is a directory, not a file")
            return handle, info.nNumberOfLinks
        except BaseException:
            _kernel32.CloseHandle(handle)
            raise

    def _adopt_windows(self, handle: int, path: str, write: bool, append: bool = False) -> int:
        """Turn a verified handle into a file descriptor for reads and writes."""
        flags = (os.O_WRONLY if write else os.O_RDONLY) | os.O_BINARY
        if append:
            # CreateFileW was asked for write access only, so without this the first
            # write would land at offset 0 and overwrite the existing content.
            flags |= os.O_APPEND
        try:
            fd = msvcrt.open_osfhandle(handle, flags)
            if fd < 0:
                raise BoundaryError(f"cannot adopt handle for {path}")
            return fd
        except BaseException:
            _kernel32.CloseHandle(handle)
            raise

    def _contains(self, final_path: str) -> bool:
        normalized = _normalize(final_path)
        return normalized == self._win_prefix or normalized.startswith(self._win_prefix + os.sep)

    def _refuse_reparse(self, path: Path) -> None:
        """Refuse a destination that is itself a link (its target must not be touched).

        An inspection failure other than "missing" is fail-closed: refusing to publish
        is recoverable, silently publishing over an uninspectable link is not.
        """
        if os.name != "nt":
            return
        try:
            st = os.lstat(path)
        except (FileNotFoundError, NotADirectoryError):
            return
        except OSError as exc:
            raise BoundaryError(f"cannot inspect {path}: {exc}") from exc
        if st.st_file_attributes & _FILE_ATTRIBUTE_REPARSE_POINT:
            raise BoundaryError(f"refusing to write through reparse point {path}", is_link=True)

    # --- shared open path ---

    def _open(
        self, parts: tuple[str, ...], write: bool = False, want_directory: bool | None = False
    ) -> int:
        """Open the leaf below the root without following links.

        ``want_directory=None`` accepts either kind, which is what metadata lookups need;
        callers that read bytes still require a regular file and check afterwards.
        """
        if os.name == "posix":
            return self._open_posix(parts, write=write, want_directory=want_directory)
        handle, _links = self._open_windows(parts, write=write, want_directory=want_directory)
        path = str(self.root.joinpath(*parts))
        return self._adopt_windows(handle, path, write=write)

    # --- public API ---

    def open_read(self, path: Path) -> IO[bytes]:
        """Open a verified regular file for streaming reads."""
        parts = self.rel_parts(path)
        fd = self._open(parts)
        try:
            if not stat_module.S_ISREG(os.fstat(fd).st_mode):
                raise BoundaryError(f"{path} is not a regular file")
        except BaseException:
            os.close(fd)
            raise
        return os.fdopen(fd, "rb")

    def read_bytes(self, path: Path) -> bytes:
        parts = self.rel_parts(path)
        fd = self._open(parts)
        try:
            chunks: list[bytes] = []
            while True:
                chunk = os.read(fd, 1 << 20)
                if not chunk:
                    return b"".join(chunks)
                chunks.append(chunk)
        finally:
            os.close(fd)

    def read_text(self, path: Path, encoding: str = "utf-8-sig", errors: str = "strict") -> str:
        # Universal newlines, matching ``Path.read_text()``: the vault's text files may
        # be CRLF, and every consumer (frontmatter parsing, line splitting, the managed
        # block in HOME.md) was written against translated "\n" input.
        return self.read_bytes(path).decode(encoding, errors).replace("\r\n", "\n").replace("\r", "\n")

    def stat(self, path: Path) -> os.stat_result | None:
        """Metadata from a verified descriptor, for files *and* directories.

        ``None`` means "no file or directory object is reachable here", which includes
        a link: a link has no content of its own, and reporting it as present would let
        a caller treat the target as if it were inside the vault.
        """
        parts = self.rel_parts(path)
        try:
            fd = self._open(parts, want_directory=None)
        except FileNotFoundError:
            return None
        except BoundaryError as exc:
            if exc.is_link:
                return None
            raise
        try:
            return os.fstat(fd)
        finally:
            os.close(fd)

    def exists(self, path: Path) -> bool:
        return self.stat(path) is not None

    def open_directory(self, path: Path) -> DirectoryHandle:
        """Open (never follow) a directory and keep the handle for the whole operation."""
        candidate = Path(path)
        if not candidate.is_absolute():
            candidate = Path.cwd() / candidate
        candidate = Path(os.path.normpath(candidate.expanduser()))
        if self._is_root(candidate):
            # The authorized root itself: duplicate the authorized descriptor.
            if os.name == "posix":
                return DirectoryHandle(self, self.root, self._dup_root_fd())
            handle, _links = self._open_windows(
                (), write=False, want_directory=True, share_delete=False
            )
            return DirectoryHandle(
                self, self.root, self._adopt_windows(handle, str(self.root), write=False)
            )
        parts = self.rel_parts(path)
        if os.name == "posix":
            # The descriptor returned is the verified directory itself: nothing is
            # re-resolved from a path afterwards.
            return DirectoryHandle(self, self.root.joinpath(*parts), self._verify_dir_posix(parts))
        handle, _links = self._open_windows(
            parts, write=False, want_directory=True, share_delete=False
        )
        return DirectoryHandle(
            self,
            self.root.joinpath(*parts),
            self._adopt_windows(handle, str(self.root.joinpath(*parts)), write=False),
        )

    def ensure_directory(self, path: Path) -> None:
        """Create a directory (and parents) below the root, refusing links."""
        parts = self.rel_parts(path)
        if not parts:
            return  # the root itself already exists
        if os.name == "posix":
            parent = self._dir_fd
            for part in parts:
                fd = self._open_component_posix(parent, part)
                if parent != self._dir_fd:
                    os.close(parent)
                parent = fd
            if parent != self._dir_fd:
                os.close(parent)
            return
        # Windows has no dir_fd, so the parent is pinned instead: each component is
        # opened (never following a link) and held without FILE_SHARE_DELETE while the
        # next one is created. Nothing is created through a path whose parent has not
        # been verified and pinned, which is what makes creation safe here.
        held: list[int] = []
        try:
            handle, _links = self._open_windows(
                (), write=False, want_directory=True, share_delete=False
            )
            held.append(handle)
            for part in parts:
                # Use the pinned parent's canonical name, not an alias that could
                # be retargeted between its verification and mkdir.
                parent_path = Path(_native_path(_final_path(held[-1])))
                target = parent_path / part
                child_parts = self.rel_parts(target)
                try:
                    child, _links = self._open_windows(
                        child_parts, write=False, want_directory=True, share_delete=False
                    )
                except FileNotFoundError:
                    try:
                        os.mkdir(target, 0o755)
                    except OSError as exc:
                        raise BoundaryError(
                            f"refusing to create {target} below {self.root}: {exc.strerror}"
                        ) from exc
                    child, _links = self._open_windows(
                        child_parts, write=False, want_directory=True, share_delete=False
                    )
                _kernel32.CloseHandle(held.pop())
                held.append(child)
        finally:
            for handle in held:
                _kernel32.CloseHandle(handle)

    def _open_component_posix(self, parent: int, part: str) -> int:
        """Open (creating if needed) one directory component without following links.

        Every failure that is not "it does not exist yet" becomes a ``BoundaryError`` so
        callers never see a bare ``OSError``: a link where a directory is required is
        reported as a boundary violation, not as an errno from deep inside the walk.
        """
        flags = os.O_RDONLY | _O_DIRECTORY | _O_NOFOLLOW | _O_CLOEXEC
        try:
            return os.open(part, flags, dir_fd=parent)
        except FileNotFoundError:
            pass
        except OSError as exc:
            raise BoundaryError(
                f"refusing {part!r} below {self.root}: {exc.strerror or exc}"
            ) from exc
        try:
            os.mkdir(part, 0o755, dir_fd=parent)
        except OSError as exc:
            raise BoundaryError(
                f"refusing to create {part!r} below {self.root}: {exc.strerror or exc}"
            ) from exc
        try:
            return os.open(part, flags, dir_fd=parent)
        except OSError as exc:
            raise BoundaryError(
                f"refusing {part!r} below {self.root}: {exc.strerror or exc}"
            ) from exc

    def _verify_dir_windows(self, parts: tuple[str, ...]) -> None:
        handle, _links = self._open_windows(parts, write=False, want_directory=True)
        _kernel32.CloseHandle(handle)

    def write_text(self, path: Path, data: str | bytes) -> None:
        """Write through the verified parent directory: exclusive temp + replace."""
        parts = self.rel_parts(path)
        if not parts:
            raise BoundaryError(f"{path} is a directory, not a file")
        payload = data if isinstance(data, bytes) else data.encode("utf-8")
        if len(parts) == 1:
            with self.open_directory(self.root) as handle:
                handle.write_atomic(parts[0], payload)
            return
        with self.open_directory(self.root.joinpath(*parts[:-1])) as handle:
            handle.write_atomic(parts[-1], payload)

    def append_text(self, path: Path, data: str | bytes) -> None:
        """Append through the verified parent directory, never following a link."""
        parts = self.rel_parts(path)
        if not parts:
            raise BoundaryError(f"{path} is a directory, not a file")
        payload = data if isinstance(data, bytes) else data.encode("utf-8")
        if len(parts) == 1:
            with self.open_directory(self.root) as handle:
                handle.append_atomic(parts[0], payload)
            return
        with self.open_directory(self.root.joinpath(*parts[:-1])) as handle:
            handle.append_atomic(parts[-1], payload)

    def unlink(self, path: Path) -> None:
        parts = self.rel_parts(path)
        if not parts:
            raise BoundaryError(f"{path} is a directory, not a file")
        if len(parts) == 1:
            with self.open_directory(self.root) as handle:
                handle.unlink(parts[0])
            return
        with self.open_directory(self.root.joinpath(*parts[:-1])) as handle:
            handle.unlink(parts[-1])

    def entries(self, directory: Path, suffix: str | None = None) -> list[Entry]:
        """Regular files directly inside ``directory``, never following links.

        A directory that does not exist yields nothing; a link on the path to it
        raises, because the content that would have been listed is elsewhere.
        """
        try:
            with self.open_directory(directory) as handle:
                return handle.entries(suffix)
        except FileNotFoundError:
            return []

    def walk(self, directory: Path, *, include_links: bool = False) -> Iterator[Entry]:
        """Yield files below ``directory`` without descending into links.

        Enumeration only filters names; every read still verifies the object it opens,
        so a directory swapped into a link after enumeration is caught at read time.
        With ``include_links`` the links themselves are yielded (``Entry.is_link``) so
        callers can report them instead of silently dropping them.
        """
        root = Path(directory)
        # Verify the start directory itself before enumerating it: a link planted at
        # the start would otherwise list external names as if they were inside. The
        # open refuses links on the whole component chain.
        try:
            with self.open_directory(root):
                pass
        except FileNotFoundError:
            return
        for current, dir_names, file_names in os.walk(root, followlinks=False):
            # ``os.walk`` on Windows does descend into junctions (they are not
            # ``is_symlink``), so reparse points are filtered out by name here.
            kept: list[str] = []
            for name in dir_names:
                kind = _no_follow_kind(Path(current) / name)
                if kind is not None and kind[0]:
                    if include_links:
                        yield Entry(self, Path(current) / name, is_link=True)
                else:
                    kept.append(name)
            dir_names[:] = kept
            for name in sorted(file_names):
                kind = _no_follow_kind(Path(current) / name)
                if kind is None:
                    continue
                if kind[0]:
                    if include_links:
                        yield Entry(self, Path(current) / name, is_link=True)
                    continue
                yield Entry(self, Path(current) / name)

    def close(self) -> None:
        if self._dir_fd >= 0:
            fd, self._dir_fd = self._dir_fd, -1
            os.close(fd)

    def __enter__(self) -> VaultFS:
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()


def _no_follow_kind(path: Path) -> tuple[bool, bool] | None:
    """``(is_link, is_directory)`` for ``path`` without following it.

    Returns ``None`` when the entry cannot be inspected at all. On Windows a junction
    is a directory reparse point and is reported as a link, matching POSIX symlinks.
    """
    try:
        st = os.stat(path, follow_symlinks=False)
    except OSError:
        return None
    if stat_module.S_ISLNK(st.st_mode):
        return True, False
    attrs = getattr(st, "st_file_attributes", 0)
    if os.name == "nt" and attrs & 0x400 and attrs & 0x10:
        return True, True
    return False, stat_module.S_ISDIR(st.st_mode)


def _as_not_found(exc: OSError, path: Path) -> OSError:
    if isinstance(exc, FileNotFoundError):
        return exc
    if exc.errno in (2, 3) or (os.name == "nt" and exc.winerror in (2, 3)):
        return FileNotFoundError(exc.errno, f"missing {path}")
    # A link where a file or directory was required (ELOOP with O_NOFOLLOW, ENOTDIR when
    # the component is a link) is a boundary refusal, not a missing object.
    if exc.errno in (errno.ELOOP, errno.ENOTDIR):
        return BoundaryError(exc.errno, f"refusing {path}: {exc.strerror or exc}", is_link=True)
    return BoundaryError(f"refusing {path}: {exc}")


# --- module-level facade -------------------------------------------------------

_ANCHORS: list[Path] = []
_MAX_ANCHORS = 16

# One VaultFS per registered root, reused across facade calls. POSIX VaultFS instances
# hold an authorized root descriptor; recreating one per call would leak that descriptor
# because the facade has no close hook. Reuse also pins the authorization: the cached
# descriptor keeps pointing at the object that was authorized even if the root name is
# later renamed or replaced by a link.
_FS_CACHE: dict[Path, VaultFS] = {}


def bind(vault: str | Path) -> Path:
    """Register ``vault`` as an authorized root; the deepest one wins for a path."""
    root = Path(vault).expanduser().resolve()
    if root in _ANCHORS:
        _ANCHORS.remove(root)
    _ANCHORS.insert(0, root)
    del _ANCHORS[_MAX_ANCHORS:]
    # Drop any cached VaultFS whose root fell out of the anchor set: it would never be
    # selected again and its POSIX descriptor must be released.
    for stale in [cached for cached in _FS_CACHE if cached not in _ANCHORS]:
        fs = _FS_CACHE.pop(stale)
        fs.close()
    return root


def _anchor_for(path: Path) -> Path:
    """The registered root that covers ``path``, or refuse.

    Matching is lexical on purpose: ``resolve()`` would follow a link planted inside the
    vault and could then find a *different* root (or none), which would silently move the
    authorization to wherever the link points. Selecting the root lexically keeps the
    caller's vault as the capability; the link itself is refused later, when the object
    is opened without following it.
    """
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = Path.cwd() / candidate
    candidate = Path(os.path.normpath(candidate.expanduser()))
    # The deepest matching root wins. Taking the first match instead would let a
    # shallower root that happens to be registered widen the boundary for a path that
    # belongs to a nested vault.
    best: Path | None = None
    best_depth = -1
    for root in _ANCHORS:
        if len(root.parts) <= best_depth:
            continue
        try:
            candidate.relative_to(root)
        except ValueError:
            # The registered root is resolved, so a differently spelled root (case or
            # separator) is matched component-wise instead of being reported as
            # unauthorized. This only selects the capability; the link itself is still
            # refused when the object is opened without following it.
            if not _shares_prefix(candidate, root):
                continue
        best, best_depth = root, len(root.parts)
    if best is not None:
        return best
    raise BoundaryError(
        f"{path} is not below any authorized vault ({', '.join(str(r) for r in _ANCHORS) or 'none registered'})"
    )


def _shares_prefix(candidate: Path, root: Path) -> bool:
    """True when ``candidate`` is spelled below ``root`` ignoring case/separators."""
    root_parts = [os.path.normcase(part) for part in root.parts]
    candidate_parts = [os.path.normcase(part) for part in candidate.parts]
    return len(candidate_parts) >= len(root_parts) and candidate_parts[: len(root_parts)] == root_parts


def _fs_for(path: Path) -> VaultFS:
    root = _anchor_for(path)
    fs = _FS_CACHE.get(root)
    if fs is None:
        fs = VaultFS(root)
        _FS_CACHE[root] = fs
    return fs


def fs_for(path: str | Path) -> VaultFS:
    """The authorized filesystem view ``path`` belongs to."""
    return _fs_for(Path(path))


def open_read(path: str | Path) -> IO[bytes]:
    return _fs_for(Path(path)).open_read(Path(path))


def read_bytes(path: str | Path) -> bytes:
    return _fs_for(Path(path)).read_bytes(Path(path))


def read_text(path: str | Path, encoding: str = "utf-8-sig", errors: str = "strict") -> str:
    return _fs_for(Path(path)).read_text(Path(path), encoding=encoding, errors=errors)


def stat(path: str | Path) -> os.stat_result | None:
    return _fs_for(Path(path)).stat(Path(path))


def exists(path: str | Path) -> bool:
    return stat(path) is not None


def write_text(path: str | Path, data: str | bytes) -> None:
    _fs_for(Path(path)).write_text(Path(path), data)


def unlink(path: str | Path) -> None:
    _fs_for(Path(path)).unlink(Path(path))


def entries(directory: str | Path, suffix: str | None = None) -> list[Entry]:
    return _fs_for(Path(directory)).entries(Path(directory), suffix=suffix)


def walk(directory: str | Path, *, include_links: bool = False) -> Iterator[Entry]:
    return _fs_for(Path(directory)).walk(Path(directory), include_links=include_links)


def ensure_directory(path: str | Path) -> None:
    _fs_for(Path(path)).ensure_directory(Path(path))


def append_text(path: str | Path, data: str | bytes) -> None:
    _fs_for(Path(path)).append_text(Path(path), data)
