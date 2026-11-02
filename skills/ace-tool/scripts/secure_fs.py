"""Open files inside an authorized root and verify the object that was opened.

Security property enforced here: every byte returned by
:meth:`AuthorizedRoot.read_verified` and :meth:`SafeFile.read_bytes` comes from a file
object that the operating system resolved, at open time, to a regular file inside the
authorized root.

Why re-checking a path is not enough: ``Path.resolve()`` / ``is_symlink()`` describe a
path at one instant. An attacker who can write inside the project directory can swap a
component for a link between that check and the later ``open()``/``read()`` (TOCTOU).
Here the verification is performed on the opened object itself:

* POSIX: each component is opened relative to the previous component's directory
  descriptor with ``O_NOFOLLOW``, so a link at any component fails the open (``ELOOP``)
  and the request is refused instead of followed.
* Windows: the object is opened with ``FILE_FLAG_OPEN_REPARSE_POINT`` (never following a
  final link), the handle is checked for ``FILE_ATTRIBUTE_REPARSE_POINT`` (refuses link
  leaves such as junctions/symlinks), and ``GetFinalPathNameByHandleW`` is compared with
  the authorized root. Links at intermediate components are exposed this way: the final
  path names the real target, so a junction between root and file is detected as outside.

Both platforms then read through the same descriptor/handle that was verified, so the
content cannot be swapped for another object after the check.

Known limits (recorded rather than silently ignored):

* POSIX mount points are not distinguishable from directories with ``O_NOFOLLOW``;
  creating one needs privileges the same-user threat model does not assume.
* Hard links keep the final path inside the root while pointing at an inode that is also
  reachable elsewhere on the same volume. The count is exposed via ``SafeFile.link_count``
  so callers can decide; they are not rejected because legitimate repositories use them.
* The authorized root itself comes from the caller (``Path.resolve()`` follows links in
  the root the user explicitly named); only paths below it are constrained.
"""

from __future__ import annotations

import ctypes
import os
import stat as stat_module
from pathlib import Path

_GENERIC_READ = 0x80000000
_GENERIC_WRITE = 0x40000000
_FILE_SHARE_READ = 0x00000001
_FILE_SHARE_WRITE = 0x00000002
_FILE_SHARE_DELETE = 0x00000004
_FILE_SHARE_ALL = _FILE_SHARE_READ | _FILE_SHARE_WRITE | _FILE_SHARE_DELETE
_OPEN_EXISTING = 3
_CREATE_NEW = 1
_FILE_ATTRIBUTE_REPARSE_POINT = 0x00000400
_FILE_FLAG_BACKUP_SEMANTICS = 0x02000000
_FILE_FLAG_OPEN_REPARSE_POINT = 0x00200000
_FILE_LIST_DIRECTORY = 0x00000001
_GENERIC_DELETE = 0x00010000
_SYNCHRONIZE = 0x00100000
_ERROR_FILE_NOT_FOUND = 2
_ERROR_PATH_NOT_FOUND = 3
_ERROR_ALREADY_EXISTS = 183
# POSIX open flags absent on Windows are defined as 0 so the POSIX-only expressions
# stay syntactically valid (and never execute) on both platforms.
_O_DIRECTORY = getattr(os, "O_DIRECTORY", 0)
_O_CLOEXEC = getattr(os, "O_CLOEXEC", 0)
_O_NOFOLLOW = getattr(os, "O_NOFOLLOW", 0)
# ctypes sign-extends the 32-bit INVALID_HANDLE_VALUE to a 64-bit pointer value.
_INVALID_HANDLE = 0xFFFFFFFFFFFFFFFF


class UnsafePathError(OSError):
    """The path did not resolve to a contained regular file below the authorized root."""


class FileTooLargeError(UnsafePathError):
    """The file is larger than the caller's read limit."""


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
    # Without argtypes ctypes would truncate a 64-bit handle to a C int.
    _kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
    _kernel32.CloseHandle.restype = wintypes.BOOL

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

    class _FileRenameInfo(ctypes.Structure):  # noqa: N801 - mirrors the Windows struct name
        _fields_ = [
            ("ReplaceIfExists", wintypes.BOOL),
            ("RootDirectory", wintypes.HANDLE),
            ("FileNameLength", wintypes.DWORD),
            ("FileName", wintypes.WCHAR * 1),
        ]

    _FILE_RENAME_INFO = 3

    def _rename_to(handle: int, root_directory: int | None, name: str) -> None:
        """Rename the object behind ``handle`` to ``name``.

        ``root_directory`` anchors a *relative* ``name`` to a verified directory
        handle, so the destination is not re-resolved from a path after it was
        checked. Renaming requires DELETE access on the renamed handle.
        """
        raw = name.encode("utf-16-le")
        buf = ctypes.create_string_buffer(ctypes.sizeof(_FileRenameInfo) + len(raw))
        info = _FileRenameInfo.from_buffer(buf)
        info.ReplaceIfExists = True
        info.RootDirectory = root_directory or None
        info.FileNameLength = len(raw)
        ctypes.memmove(ctypes.byref(info, _FileRenameInfo.FileName.offset), raw, len(raw))
        if not _kernel32.SetFileInformationByHandle(handle, _FILE_RENAME_INFO, buf, ctypes.sizeof(buf)):
            raise OSError(ctypes.get_last_error(), f"cannot publish {name!r}")

    _kernel32.SetFileInformationByHandle.argtypes = (
        wintypes.HANDLE,
        wintypes.DWORD,
        wintypes.LPVOID,
        wintypes.DWORD,
    )
    _kernel32.SetFileInformationByHandle.restype = wintypes.BOOL

else:

    def _rename_to(handle: int, root_directory: int | None, name: str) -> None:  # pragma: no cover
        raise NotImplementedError

    def _final_path(handle: int) -> str:  # pragma: no cover - unused on POSIX
        raise NotImplementedError

    def _native_path(path: str) -> str:  # pragma: no cover - unused on POSIX
        raise NotImplementedError

    def _normalize(path: str) -> str:  # pragma: no cover - unused on POSIX
        raise NotImplementedError


class SafeFile:
    """A descriptor whose underlying object was verified to be inside the authorized root."""

    def __init__(self, fd: int, link_count: int | None = None):
        self._fd = fd
        self.link_count = link_count
        st = os.fstat(fd)
        self.size = st.st_size
        self.mtime = st.st_mtime

    def read_bytes(self, max_bytes: int | None = None) -> bytes:
        if max_bytes is not None and self.size > max_bytes:
            raise FileTooLargeError(f"file is {self.size} bytes, limit is {max_bytes}")
        remaining = self.size if max_bytes is None else min(self.size, max_bytes)
        chunks: list[bytes] = []
        while remaining > 0:
            chunk = os.read(self._fd, min(1 << 20, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        data = b"".join(chunks)
        if max_bytes is not None and len(data) < self.size:
            raise FileTooLargeError(f"file grew past {max_bytes} bytes while reading")
        return data

    def write_bytes(self, data: bytes) -> None:
        view = memoryview(data)
        while view:
            written = os.write(self._fd, view)
            if not written:
                raise OSError("short write")
            view = view[written:]

    def close(self) -> None:
        if self._fd >= 0:
            fd, self._fd = self._fd, -1
            os.close(fd)

    def __enter__(self) -> SafeFile:
        return self

    def __exit__(self, *exc_info) -> None:
        self.close()


class AuthorizedRoot:
    """Guards file access below one authorized root directory."""

    def __init__(self, root: Path):
        # The caller names the root; resolving it once fixes the boundary object.
        self.root = Path(root).resolve()
        self._dir_fd = -1
        self._win_prefix = ""
        if os.name == "posix":
            self._dir_fd = os.open(self.root, os.O_RDONLY | _O_DIRECTORY | _O_CLOEXEC)
        else:
            self._win_prefix = _normalize(str(self.root))

    # --- POSIX implementation ---

    def _open_posix(self, parts: tuple[str, ...], write: bool) -> int:
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
            flags = (os.O_WRONLY | os.O_CREAT | os.O_EXCL) if write else os.O_RDONLY
            leaf = os.open(parts[-1], flags | _O_NOFOLLOW | _O_CLOEXEC, 0o600, dir_fd=parent)
        except OSError as e:
            for fd in parents:
                os.close(fd)
            raise UnsafePathError(f"refusing {self.root.joinpath(*parts)}: {e}") from e
        for fd in parents:
            os.close(fd)
        return leaf

    def _verify_dir_posix(self, parts: tuple[str, ...]) -> None:
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
        except OSError as e:
            for fd in fds:
                os.close(fd)
            raise UnsafePathError(f"refusing directory {self.root.joinpath(*parts)}: {e}") from e
        for fd in fds:
            os.close(fd)

    # --- Windows implementation ---

    def _open_windows(self, parts: tuple[str, ...], write: bool, want_directory: bool) -> tuple[int, int]:
        path = str(self.root.joinpath(*parts))
        access = _GENERIC_WRITE if write else _GENERIC_READ
        disposition = _CREATE_NEW if write else _OPEN_EXISTING
        # A newly created private file needs no share flags; reads share everything so
        # concurrent tools keep working.
        share = _FILE_SHARE_READ if write else _FILE_SHARE_ALL
        flags = _FILE_FLAG_BACKUP_SEMANTICS | _FILE_FLAG_OPEN_REPARSE_POINT
        parent_handle = -1
        if write:
            # Create only once every parent directory is verified and pinned. Creating
            # through a link would put the file outside the root, and checking the
            # finished handle would merely discover that after the fact.
            parent_handle = self._open_dir_handle(parts[:-1])
        try:
            if write:
                # A held real directory does not pin an intermediate junction
                # alias. Create only through its verified canonical name.
                path = str(Path(_native_path(_final_path(parent_handle))) / parts[-1])
            handle = _kernel32.CreateFileW(path, access, share, None, disposition, flags, None)
            if not handle or handle == _INVALID_HANDLE:
                err = ctypes.get_last_error()
                if err in (_ERROR_FILE_NOT_FOUND, _ERROR_PATH_NOT_FOUND):
                    raise FileNotFoundError(err, f"missing {path}")
                raise UnsafePathError(f"refusing {path}: WinError {err}")
            info = _ByHandleFileInformation()
            if not _kernel32.GetFileInformationByHandle(handle, ctypes.byref(info)):
                err = ctypes.get_last_error()
                _kernel32.CloseHandle(handle)
                raise UnsafePathError(f"cannot stat handle for {path}: WinError {err}")
            if info.dwFileAttributes & _FILE_ATTRIBUTE_REPARSE_POINT:
                # The opened object is itself a link (junction, symlink, mount point).
                _kernel32.CloseHandle(handle)
                raise UnsafePathError(f"refusing reparse point {path}")
            final = _final_path(handle)
            if not self._contains(final):
                # An intermediate component was a link: the handle names the real target.
                _kernel32.CloseHandle(handle)
                raise UnsafePathError(f"{path} resolves outside the root to {final}")
            if want_directory and not (info.dwFileAttributes & 0x10):
                _kernel32.CloseHandle(handle)
                raise UnsafePathError(f"{path} is not a directory")
            # Adopt the verified handle as a descriptor: reads and fstat then
            # operate on exactly the object that passed the checks above.
            # O_BINARY keeps CRLF translation from rewriting indexed content.
            fd = msvcrt.open_osfhandle(handle, os.O_BINARY | (os.O_WRONLY if write else os.O_RDONLY))
            if fd < 0:
                _kernel32.CloseHandle(handle)
                raise UnsafePathError(f"cannot adopt handle for {path}")
            # fd now owns the handle; it must not be closed separately.
            return fd, info.nNumberOfLinks
        finally:
            if parent_handle >= 0:
                _kernel32.CloseHandle(parent_handle)

    def _contains(self, final_path: str) -> bool:
        normalized = _normalize(final_path)
        return normalized == self._win_prefix or normalized.startswith(self._win_prefix + os.sep)

    def _open_dir_handle(self, parts: tuple[str, ...]) -> int:
        """Open a verified directory and keep it: without FILE_SHARE_DELETE the OS then
        refuses to rename or remove it, which is what pins the destination's parent
        while a publication is in flight (Windows has no directory-relative rename).
        """
        path = str(self.root.joinpath(*parts))
        handle = _kernel32.CreateFileW(
            path,
            _FILE_LIST_DIRECTORY,
            _FILE_SHARE_READ | _FILE_SHARE_WRITE,
            None,
            _OPEN_EXISTING,
            _FILE_FLAG_BACKUP_SEMANTICS | _FILE_FLAG_OPEN_REPARSE_POINT,
            None,
        )
        if not handle or handle == _INVALID_HANDLE:
            err = ctypes.get_last_error()
            if err in (_ERROR_FILE_NOT_FOUND, _ERROR_PATH_NOT_FOUND):
                raise FileNotFoundError(err, f"missing {path}")
            raise UnsafePathError(f"refusing {path}: WinError {err}")
        info = _ByHandleFileInformation()
        if not _kernel32.GetFileInformationByHandle(handle, ctypes.byref(info)):
            err = ctypes.get_last_error()
            _kernel32.CloseHandle(handle)
            raise UnsafePathError(f"cannot stat {path}: WinError {err}")
        if info.dwFileAttributes & _FILE_ATTRIBUTE_REPARSE_POINT:
            _kernel32.CloseHandle(handle)
            raise UnsafePathError(f"refusing reparse point {path}")
        if not info.dwFileAttributes & 0x10:
            _kernel32.CloseHandle(handle)
            raise UnsafePathError(f"{path} is not a directory")
        if not self._contains(_final_path(handle)):
            _kernel32.CloseHandle(handle)
            raise UnsafePathError(f"{path} resolves outside the root")
        return handle

    def publish(self, tmp_rel_parts, rel_parts) -> None:
        """Make a temporary file created by :meth:`open_for_write` become ``rel_parts``.

        The rename is issued against the verified objects rather than by re-resolving
        the destination path: POSIX replaces inside the verified parent directory
        descriptor, Windows renames the temporary file by handle and anchors the
        relative destination to a held directory handle. A destination swapped for a
        link in the meantime is therefore *replaced*, not written through.
        """
        tmp_parts = self._validate(tmp_rel_parts)
        parts = self._validate(rel_parts)
        if tmp_parts[:-1] != parts[:-1]:
            raise UnsafePathError(f"{tmp_parts!r} is not beside {parts!r}")
        if os.name == "posix":
            fds: list[int] = []
            try:
                parent = self._dir_fd
                for part in parts[:-1]:
                    fd = os.open(
                        part,
                        os.O_RDONLY | _O_DIRECTORY | _O_NOFOLLOW | _O_CLOEXEC,
                        dir_fd=parent,
                    )
                    fds.append(fd)
                    parent = fd
                os.replace(tmp_parts[-1], parts[-1], src_dir_fd=parent, dst_dir_fd=parent)
            except OSError as e:
                raise UnsafePathError(f"cannot publish {self.root.joinpath(*parts)}: {e}") from e
            finally:
                for fd in fds:
                    os.close(fd)
            return
        parent_handle = -1
        tmp_handle = -1
        try:
            # Holding the destination's directory (no FILE_SHARE_DELETE) keeps it from
            # being renamed or removed while the publication is in flight, so the
            # destination path cannot be redirected by swapping the parent.
            parent_handle = self._open_dir_handle(parts[:-1])
            # Discard mutable intermediate aliases after opening the parent.
            parent_path = Path(_native_path(_final_path(parent_handle)))
            destination = parent_path / parts[-1]
            temporary = parent_path / tmp_parts[-1]
            self._refuse_reparse(destination)
            # OPEN_REPARSE_POINT is required here: without it this reopen would
            # follow a link planted at the temporary name, and renaming that handle
            # would move the outside target instead of publishing our own file.
            tmp_handle = _kernel32.CreateFileW(
                str(temporary),
                _GENERIC_READ | _GENERIC_WRITE | _GENERIC_DELETE | _SYNCHRONIZE,
                _FILE_SHARE_ALL,
                None,
                _OPEN_EXISTING,
                _FILE_FLAG_OPEN_REPARSE_POINT | _FILE_FLAG_BACKUP_SEMANTICS,
                None,
            )
            if not tmp_handle or tmp_handle == _INVALID_HANDLE:
                raise UnsafePathError(
                    f"cannot reopen temporary {self.root.joinpath(*tmp_parts)}: WinError {ctypes.get_last_error()}"
                )
            info = _ByHandleFileInformation()
            if not _kernel32.GetFileInformationByHandle(tmp_handle, ctypes.byref(info)):
                raise UnsafePathError(f"cannot stat temporary handle: WinError {ctypes.get_last_error()}")
            if info.dwFileAttributes & _FILE_ATTRIBUTE_REPARSE_POINT:
                raise UnsafePathError(f"temporary {tmp_parts!r} became a link")
            # Renaming replaces the destination's directory entry, so a leaf that was
            # swapped for a link is replaced rather than written through.
            _rename_to(tmp_handle, None, str(destination))
        finally:
            if tmp_handle >= 0:
                _kernel32.CloseHandle(tmp_handle)
            if parent_handle >= 0:
                _kernel32.CloseHandle(parent_handle)

    @staticmethod
    def _refuse_reparse(path: Path) -> None:
        """Refuse a destination that is a link, so publication replaces the entry
        instead of following it."""
        try:
            info = os.stat(path, follow_symlinks=False)
        except (FileNotFoundError, NotADirectoryError):
            return
        except OSError as exc:
            raise UnsafePathError(f"cannot inspect {path}: {exc}") from exc
        if stat_module.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
            raise UnsafePathError(f"refusing to publish over link {path}")

    # --- public API ---

    @staticmethod
    def _validate(rel_parts) -> tuple[str, ...]:
        parts = tuple(rel_parts)
        if not parts or any(
            not p
            or p in (".", "..")
            or "/" in p
            or "\\" in p
            # A colon in a component is either a drive-relative path (``C:escape``
            # resolves against the C: current directory of that drive) or an NTFS
            # alternate data stream (``file:stream``); both can escape or alias the
            # intended location, so both are refused outright.
            or ":" in p
            or "\x00" in p
            for p in parts
        ):
            raise UnsafePathError(f"invalid relative path {parts!r}")
        return parts

    def open_verified(self, rel_parts) -> SafeFile:
        """Open a regular file below the root, refusing links and outside targets."""
        parts = self._validate(rel_parts)
        if os.name == "posix":
            fd = self._open_posix(parts, write=False)
            try:
                if not stat_module.S_ISREG(os.fstat(fd).st_mode):
                    raise UnsafePathError(f"{self.root.joinpath(*parts)} is not a regular file")
                return SafeFile(fd, link_count=os.fstat(fd).st_nlink)
            except BaseException:
                os.close(fd)
                raise
        fd, links = self._open_windows(parts, write=False, want_directory=False)
        return SafeFile(fd, link_count=links)

    def open_for_write(self, rel_parts) -> SafeFile:
        """Exclusively create a file below the root after verifying its container."""
        parts = self._validate(rel_parts)
        if os.name == "posix":
            return SafeFile(self._open_posix(parts, write=True))
        fd, _links = self._open_windows(parts, write=True, want_directory=False)
        return SafeFile(fd)

    def verify_directory(self, rel_parts) -> None:
        """Refuse unless every component below the root is a real (non-link) directory."""
        parts = self._validate(rel_parts)
        if os.name == "posix":
            self._verify_dir_posix(parts)
        else:
            fd, _links = self._open_windows(parts, write=False, want_directory=True)
            os.close(fd)

    def read_verified(self, rel_parts, max_bytes: int | None = None) -> bytes:
        with self.open_verified(rel_parts) as safe:
            return safe.read_bytes(max_bytes)

    def close(self) -> None:
        if self._dir_fd >= 0:
            fd, self._dir_fd = self._dir_fd, -1
            os.close(fd)
