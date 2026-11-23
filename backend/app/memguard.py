"""Global memory guard (psutil is not installed; use the OS directly). Returns available physical RAM in MB, or None if unknown."""
from __future__ import annotations

import os
import sys


def available_mb() -> float | None:
    try:
        if sys.platform == "win32":
            import ctypes

            class MEMORYSTATUSEX(ctypes.Structure):
                _fields_ = [
                    ("dwLength", ctypes.c_ulong),
                    ("dwMemoryLoad", ctypes.c_ulong),
                    ("ullTotalPhys", ctypes.c_ulonglong),
                    ("ullAvailPhys", ctypes.c_ulonglong),
                    ("ullTotalPageFile", ctypes.c_ulonglong),
                    ("ullAvailPageFile", ctypes.c_ulonglong),
                    ("ullTotalVirtual", ctypes.c_ulonglong),
                    ("ullAvailVirtual", ctypes.c_ulonglong),
                    ("sullAvailExtendedVirtual", ctypes.c_ulonglong),
                ]

            st = MEMORYSTATUSEX()
            st.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(st)):  # type: ignore[attr-defined]
                return st.ullAvailPhys / 1048576
            return None
        if os.path.exists("/proc/meminfo"):
            with open("/proc/meminfo", encoding="ascii") as f:
                for line in f:
                    if line.startswith("MemAvailable:"):
                        return int(line.split()[1]) / 1024
    except Exception:  # noqa: BLE001 - the guard must never crash the API
        return None
    return None


def enough_memory(min_free_mb: int) -> bool:
    """True when at least `min_free_mb` is available (or when the platform cannot tell: fail open, jobs are single-flight anyway)."""
    a = available_mb()
    return True if a is None else a >= min_free_mb
