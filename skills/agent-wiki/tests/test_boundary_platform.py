"""Platform-only entry points must fail closed on unsupported hosts."""

import errno
import sys

import pytest
from agent_wiki import boundary


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX platform guard regression")
@pytest.mark.parametrize(
    ("method", "args"),
    [
        ("_open_windows", ((), False, True)),
        ("_adopt_windows", (-1, "unused", False)),
        ("_verify_dir_windows", ((),)),
    ],
)
def test_windows_helpers_fail_closed_on_posix(tmp_path, method, args):
    with boundary.VaultFS(tmp_path) as fs:
        with pytest.raises(boundary.BoundaryError) as exc:
            getattr(fs, method)(*args)
        assert exc.value.errno == errno.ENOTSUP
