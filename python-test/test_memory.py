# SPDX-License-Identifier: (Apache-2.0 OR MIT)

import dataclasses
import datetime
import gc
import random
import sys
from typing import List

import pytest
import ssrjson

try:
    import pytz
except ImportError:
    pytz = None  # type: ignore

try:
    import psutil
except ImportError:
    psutil = None  # type: ignore

try:
    import numpy
except ImportError:
    numpy = None  # type: ignore

try:
    import pandas
except ImportError:
    pandas = None  # type: ignore

def is_libasan_loaded():
    if sys.platform == "win32":
        try:
            import ctypes
            from ctypes import wintypes
            # load needed DLL
            psapi = ctypes.WinDLL("Psapi.dll")
            kernel32 = ctypes.WinDLL("kernel32.dll")

            # get handle of current process
            GetCurrentProcess = kernel32.GetCurrentProcess
            GetCurrentProcess.restype = wintypes.HANDLE
            hProcess = GetCurrentProcess()

            # setup param and return type for EnumProcessModules
            EnumProcessModules = psapi.EnumProcessModules
            EnumProcessModules.restype = wintypes.BOOL
            EnumProcessModules.argtypes = [
                wintypes.HANDLE,                  # hProcess
                ctypes.POINTER(wintypes.HMODULE), # lphModule
                wintypes.DWORD,                   # cb
                ctypes.POINTER(wintypes.DWORD)    # lpcbNeeded
            ]

            # setup param and return type for GetModuleFileNameExA
            GetModuleFileNameExA = psapi.GetModuleFileNameExA
            GetModuleFileNameExA.restype = wintypes.DWORD
            GetModuleFileNameExA.argtypes = [
                wintypes.HANDLE,  # hProcess
                wintypes.HMODULE, # hModule
                wintypes.LPSTR,   # lpFilename
                wintypes.DWORD    # nSize
            ]

            # Allocate array for module handles
            MAX_MODULES = 1024
            module_array = (wintypes.HMODULE * MAX_MODULES)()
            cb = ctypes.sizeof(module_array)
            needed = wintypes.DWORD()

            if not EnumProcessModules(hProcess, module_array, cb, ctypes.byref(needed)):
                print("Fail to call EnumProcessModules.")
                return False

            module_count = needed.value // ctypes.sizeof(wintypes.HMODULE)

            # Iterate all loaded modules
            for i in range(module_count):
                hModule = module_array[i]
                buffer_len = 260
                module_filename = ctypes.create_string_buffer(buffer_len)
                if GetModuleFileNameExA(hProcess, hModule, module_filename, buffer_len):
                    # Convert to Python string (ignore encoding error)
                    path_str = module_filename.value.decode('utf-8', errors='ignore').lower()
                    if "asan" in path_str:
                        return True
        except Exception:  # pylint: disable=broad-except
            pass
        return False
    try:
        with open("/proc/self/maps", "r") as maps_file:
            for line in maps_file:
                if "libasan.so" in line:
                    return True
    except Exception:  # pylint: disable=broad-except
        pass
    return False


asan_loaded = is_libasan_loaded()

FIXTURE = '{"a":[81891289, 8919812.190129012], "b": false, "c": null, "d": "東京"}'


def default(obj):
    return str(obj)


@dataclasses.dataclass
class Member:
    id: int
    active: bool


@dataclasses.dataclass
class Object:
    id: int
    updated_at: datetime.datetime
    name: str
    members: List[Member]


DATACLASS_FIXTURE = [
    Object(
        i,
        datetime.datetime.now(datetime.timezone.utc)
        + datetime.timedelta(seconds=random.randint(0, 10000)),
        str(i) * 3,
        [Member(j, True) for j in range(0, 10)],
    )
    for i in range(100000, 101000)
]

# For the case `sde64 -ivb` checks, the memory allocation strategy is different, which uses more memory.
# For asan check, the memory will not be released and rss increases over time.
# For other cases, 4MiB is enough.
MAX_INCREASE = 1024 * 1024 * 6  # 6MiB.


class Unsupported:
    pass


class TestMemory:
    @pytest.mark.skipif(psutil is None, reason="psutil not installed")
    @pytest.mark.skipif(asan_loaded, reason="libasan loaded")
    def test_memory_loads(self):
        """
        loads() memory leak
        """
        proc = psutil.Process()
        gc.collect()
        val = ssrjson.loads(FIXTURE)
        assert val
        mem = proc.memory_info().rss
        for _ in range(10000):
            val = ssrjson.loads(FIXTURE)
            assert val
        gc.collect()
        leak = proc.memory_info().rss - mem
        assert leak <= MAX_INCREASE

    # @pytest.mark.skipif(psutil is None, reason="psutil not installed")
    # def test_memory_loads_memoryview(self):
    #     """
    #     loads() memory leak using memoryview
    #     """
    #     proc = psutil.Process()
    #     gc.collect()
    #     fixture = FIXTURE.encode("utf-8")
    #     val = ssrjson.loads(fixture)
    #     assert val
    #     mem = proc.memory_info().rss
    #     for _ in range(10000):
    #         val = ssrjson.loads(memoryview(fixture))
    #         assert val
    #     gc.collect()
    #     assert proc.memory_info().rss - mem <= + MAX_INCREASE

    @pytest.mark.skipif(psutil is None, reason="psutil not installed")
    @pytest.mark.skipif(asan_loaded, reason="libasan loaded")
    def test_memory_dumps(self):
        """
        dumps() memory leak
        """
        proc = psutil.Process()
        gc.collect()
        fixture = ssrjson.loads(FIXTURE)
        val = ssrjson.dumps(fixture)
        assert val
        mem = proc.memory_info().rss
        for _ in range(10000):
            val = ssrjson.dumps(fixture)
            assert val
        gc.collect()
        assert proc.memory_info().rss - mem <= MAX_INCREASE

    @pytest.mark.skipif(psutil is None, reason="psutil not installed")
    @pytest.mark.skipif(asan_loaded, reason="libasan loaded")
    def test_memory_dumps_to_bytes(self):
        """
        dumps_to_bytes() memory leak
        """
        proc = psutil.Process()
        gc.collect()
        fixture = ssrjson.loads(FIXTURE)
        val = ssrjson.dumps_to_bytes(fixture)
        assert val
        mem = proc.memory_info().rss
        for _ in range(10000):
            val = ssrjson.dumps_to_bytes(fixture)
            assert val
        gc.collect()
        assert proc.memory_info().rss - mem <= MAX_INCREASE

    @pytest.mark.skipif(psutil is None, reason="psutil not installed")
    @pytest.mark.skipif(asan_loaded, reason="libasan loaded")
    def test_memory_loads_exc(self):
        """
        loads() memory leak exception without a GC pause
        """
        proc = psutil.Process()
        gc.disable()
        mem = proc.memory_info().rss
        n = 10000
        i = 0
        for _ in range(n):
            try:
                ssrjson.loads("")
            except ssrjson.JSONDecodeError:
                i += 1
        assert n == i
        assert proc.memory_info().rss - mem <= MAX_INCREASE
        gc.enable()

    @pytest.mark.skipif(psutil is None, reason="psutil not installed")
    @pytest.mark.skipif(asan_loaded, reason="libasan loaded")
    def test_memory_dumps_exc(self):
        """
        dumps() memory leak exception without a GC pause
        """
        proc = psutil.Process()
        gc.disable()
        data = Unsupported()
        mem = proc.memory_info().rss
        n = 10000
        i = 0
        for _ in range(n):
            try:
                ssrjson.dumps(data)
            except ssrjson.JSONEncodeError:
                i += 1
        assert n == i
        assert proc.memory_info().rss - mem <= MAX_INCREASE
        gc.enable()

    @pytest.mark.skipif(psutil is None, reason="psutil not installed")
    @pytest.mark.skipif(asan_loaded, reason="libasan loaded")
    def test_memory_dumps_to_bytes_exc(self):
        """
        dumps_to_bytes() memory leak exception without a GC pause
        """
        proc = psutil.Process()
        gc.disable()
        data = Unsupported()
        mem = proc.memory_info().rss
        n = 10000
        i = 0
        for _ in range(n):
            try:
                ssrjson.dumps_to_bytes(data)
            except ssrjson.JSONEncodeError:
                i += 1
        assert n == i
        assert proc.memory_info().rss - mem <= MAX_INCREASE
        gc.enable()

    # @pytest.mark.skipif(psutil is None, reason="psutil not installed")
    # def test_memory_dumps_default(self):
    #     """
    #     dumps() default memory leak
    #     """
    #     proc = psutil.Process()
    #     gc.collect()
    #     fixture = ssrjson.loads(FIXTURE)

    #     class Custom:
    #         def __init__(self, name):
    #             self.name = name

    #         def __str__(self):
    #             return f"{self.__class__.__name__}({self.name})"

    #     fixture["custom"] = Custom("ssrjson")
    #     val = ssrjson.dumps(fixture, default=default)
    #     mem = proc.memory_info().rss
    #     for _ in range(10000):
    #         val = ssrjson.dumps(fixture, default=default)
    #         assert val
    #     gc.collect()
    #     assert proc.memory_info().rss - mem <= MAX_INCREASE

    @pytest.mark.skipif(psutil is None, reason="psutil not installed")
    @pytest.mark.skipif(asan_loaded, reason="libasan loaded")
    def test_memory_loads_keys(self):
        """
        loads() memory leak with number of keys causing cache eviction
        """
        proc = psutil.Process()
        gc.collect()
        fixture = {f"key_{idx}": "value" for idx in range(1024)}
        assert len(fixture) == 1024
        val = ssrjson.dumps(fixture)
        loaded = ssrjson.loads(val)
        assert loaded
        mem = proc.memory_info().rss
        for _ in range(100):
            loaded = ssrjson.loads(val)
            assert loaded
        gc.collect()
        assert proc.memory_info().rss - mem <= MAX_INCREASE
