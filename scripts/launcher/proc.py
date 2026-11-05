"""Process identity and termination helpers shared by the launcher and the supervisor.

A PID alone is never trusted: PIDs are reused. Every tracked process is stored as
(pid, identity), where identity is the process creation time reported by the operating system.
A process is only considered "ours" when both still match.

Standard library only (ctypes on Windows, ``ps`` on Linux and macOS).
"""

from __future__ import annotations

import os
import signal
import subprocess
import sys

IS_WINDOWS = os.name == "nt"

if IS_WINDOWS:
    import ctypes
    from ctypes import wintypes

    _kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    _STILL_ACTIVE = 259

    class _FILETIME(ctypes.Structure):
        _fields_ = [("low", wintypes.DWORD), ("high", wintypes.DWORD)]

    _kernel32.OpenProcess.restype = wintypes.HANDLE
    _kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    _kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    _kernel32.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
    _kernel32.GetProcessTimes.argtypes = [wintypes.HANDLE] + [ctypes.POINTER(_FILETIME)] * 4
    _kernel32.QueryFullProcessImageNameW.argtypes = [
        wintypes.HANDLE,
        wintypes.DWORD,
        wintypes.LPWSTR,
        ctypes.POINTER(wintypes.DWORD),
    ]


def _windows_query(pid: int) -> tuple[str, str] | None:
    """Return (creation time, image path) for a running process, or None."""
    handle = _kernel32.OpenProcess(_PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        return None
    try:
        code = wintypes.DWORD()
        if (
            not _kernel32.GetExitCodeProcess(handle, ctypes.byref(code))
            or code.value != _STILL_ACTIVE
        ):
            return None
        created, exited, kernel, user = (_FILETIME() for _ in range(4))
        if not _kernel32.GetProcessTimes(
            handle,
            ctypes.byref(created),
            ctypes.byref(exited),
            ctypes.byref(kernel),
            ctypes.byref(user),
        ):
            return None
        buffer = ctypes.create_unicode_buffer(1024)
        size = wintypes.DWORD(len(buffer))
        image = (
            buffer.value
            if _kernel32.QueryFullProcessImageNameW(handle, 0, buffer, ctypes.byref(size))
            else ""
        )
        return str((created.high << 32) | created.low), image
    finally:
        _kernel32.CloseHandle(handle)


def _ps(pid: int, field: str) -> str | None:
    try:
        result = subprocess.run(
            ["ps", "-o", f"{field}=", "-p", str(pid)],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    value = result.stdout.strip()
    return value if result.returncode == 0 and value else None


def identity(pid: int) -> str | None:
    """Creation-time token of a live process, or None if it is not running."""
    if pid <= 0:
        return None
    if IS_WINDOWS:
        info = _windows_query(pid)
        return info[0] if info else None
    state = _ps(pid, "stat")
    if state is None or state.startswith("Z"):
        return None
    return _ps(pid, "lstart")


def describe(pid: int) -> str:
    """Executable or command line, for messages and ownership checks."""
    if IS_WINDOWS:
        info = _windows_query(pid)
        return info[1] if info else ""
    return _ps(pid, "command") or ""


def is_ours(pid: int | None, expected_identity: str | None) -> bool:
    """True only if the PID is running AND is the same process we recorded."""
    if not pid or not expected_identity:
        return False
    return identity(pid) == expected_identity


def popen_flags(new_console: bool = False) -> dict:
    """Keyword arguments that put a child in its own process group / session."""
    if IS_WINDOWS:
        flags = subprocess.CREATE_NEW_PROCESS_GROUP
        if new_console:
            flags |= subprocess.CREATE_NO_WINDOW  # hidden console of its own
        return {"creationflags": flags}
    return {"start_new_session": True}


def request_graceful_stop(pid: int) -> None:
    """Ask a process group to shut down (Ctrl+Break on Windows, SIGINT on POSIX)."""
    try:
        if IS_WINDOWS:
            os.kill(pid, signal.CTRL_BREAK_EVENT)
        else:
            os.killpg(pid, signal.SIGINT)
    except (OSError, ProcessLookupError):
        pass


def kill_tree(pid: int) -> None:
    """Force-stop a process and its children. Callers must validate ownership first."""
    if IS_WINDOWS:
        subprocess.run(
            ["taskkill", "/PID", str(pid), "/T", "/F"],
            capture_output=True,
            check=False,
            timeout=30,
        )
        return
    try:
        if os.getpgid(pid) == pid:  # a session leader we created: kill the whole group
            os.killpg(pid, signal.SIGKILL)
        else:
            os.kill(pid, signal.SIGKILL)
    except (OSError, ProcessLookupError):
        pass


if __name__ == "__main__":  # tiny manual check: python proc.py <pid>
    target = int(sys.argv[1]) if len(sys.argv) > 1 else os.getpid()
    print(target, identity(target), describe(target))
