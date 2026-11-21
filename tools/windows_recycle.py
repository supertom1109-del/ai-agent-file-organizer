"""Read-only Windows volume configuration and matching recycle evidence."""

import csv
import ctypes
from ctypes import wintypes
from datetime import datetime, timedelta, timezone
from pathlib import Path, PureWindowsPath
import re
import struct
import subprocess
import winreg


class RecycleInfo(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.DWORD), ("size", ctypes.c_int64), ("items", ctypes.c_int64)]


def usable_capacity(configured_mb, permanent_mode, used_bytes, needed_bytes):
    values = (configured_mb, permanent_mode, used_bytes, needed_bytes)
    if any(type(value) is not int for value in values):
        return False, None
    if configured_mb <= 0 or permanent_mode != 0 or min(used_bytes, needed_bytes) < 0:
        return False, None
    room = configured_mb * 1_000_000 - used_bytes
    return room > needed_bytes, room


def read_capacity(root, sample_bytes):
    output = subprocess.check_output(["mountvol.exe", root, "/L"], text=True, errors="replace")
    volume = re.search(r"\{[0-9A-Fa-f-]{36}\}", output)
    if volume is None:
        raise ValueError("无法核实源卷 GUID")
    branch = r"Software\Microsoft\Windows\CurrentVersion\Explorer\BitBucket\Volume"
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, branch + "\\" + volume.group()) as key:
        configured = winreg.QueryValueEx(key, "MaxCapacity")[0]
        permanent_mode = winreg.QueryValueEx(key, "NukeOnDelete")[0]

    query = ctypes.WinDLL("Shell32.dll").SHQueryRecycleBinW
    query.argtypes = [wintypes.LPCWSTR, ctypes.POINTER(RecycleInfo)]
    query.restype = ctypes.c_int32
    info = RecycleInfo(cbSize=ctypes.sizeof(RecycleInfo))
    if query(root, ctypes.byref(info)) != 0 or min(info.size, info.items) < 0:
        raise ValueError("无法查询源卷的回收站占用")
    ready, room = usable_capacity(configured, permanent_mode, info.size, sample_bytes)
    return {"capacity_check_passed": ready, "configured_quota_mb": configured, "quota_is_estimate": False,
            "nuke_on_delete": permanent_mode, "current_usage_bytes": info.size, "current_items": info.items,
            "conservative_headroom_bytes": room, "source_volume": Path(root).drive,
            "source": "mountvol 卷 GUID 与当前用户匹配配置；SHQueryRecycleBinW 实测占用"}


def parse_metadata(data):
    if len(data) < 28:
        raise ValueError("系统回收索引头部不完整")
    version, size, ticks, units = struct.unpack_from("<QQQI", data)
    if version != 2 or len(data) != 28 + units * 2:
        raise ValueError("系统回收索引格式不受支持或长度不匹配")
    path = data[28:].decode("utf-16-le")
    if not path.endswith("\0") or "\0" in path[:-1] or not PureWindowsPath(path[:-1]).is_absolute():
        raise ValueError("系统回收索引的原路径无效")
    removed = datetime(1601, 1, 1, tzinfo=timezone.utc) + timedelta(microseconds=ticks // 10)
    return path[:-1], size, removed


def current_user_bin(root):
    output = subprocess.check_output(["whoami.exe", "/user", "/fo", "csv", "/nh"],
                                     text=True, errors="replace")
    sid = next((entry for row in csv.reader(output.splitlines()) for entry in row
                if re.fullmatch(r"S-1-(?:\d+-)+\d+", entry)), None)
    if sid is None:
        raise ValueError("无法确认当前用户的系统回收目录")
    return Path(root) / "$Recycle.Bin" / sid
