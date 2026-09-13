"""Fail closed if the documented local P/E topology no longer matches CPU IDs."""
import ctypes
import os
import struct

from scripts.grouped_plan import CPU_POLICY


def topology():
    if os.name != 'nt':
        raise RuntimeError('Grouped CPU qualification requires Windows CPU-set topology')
    api = ctypes.WinDLL('kernel32', use_last_error=True).GetSystemCpuSetInformation
    api.argtypes = [ctypes.c_void_p, ctypes.c_uint32, ctypes.POINTER(ctypes.c_uint32), ctypes.c_void_p, ctypes.c_uint32]
    api.restype = ctypes.c_int
    needed = ctypes.c_uint32()
    api(None, 0, ctypes.byref(needed), None, 0)
    if not needed.value:
        raise ctypes.WinError(ctypes.get_last_error())
    buffer = ctypes.create_string_buffer(needed.value)
    if not api(buffer, needed.value, ctypes.byref(needed), None, 0):
        raise ctypes.WinError(ctypes.get_last_error())
    rows, offset = [], 0
    while offset < needed.value:
        size, kind = struct.unpack_from('<II', buffer, offset)
        if size < 32 or offset + size > needed.value:
            raise ValueError('Invalid CPU-set record size')
        if kind == 0:
            _, group, logical, core, _, _, efficiency, _ = struct.unpack_from('<IH6B', buffer, offset + 8)
            rows.append(dict(group=group, logical_processor=logical, core_index=core, efficiency_class=efficiency))
        offset += size
    return rows


def validate_topology(rows):
    if len(rows) != 8 or any(r['group'] != 0 for r in rows):
        raise ValueError('Expected the qualified local eight-core topology')
    indexed = {r['logical_processor']: r for r in rows}
    if set(indexed) != set(range(8)) or len({r['core_index'] for r in rows}) != 8:
        raise ValueError('CPU IDs or physical core identities changed')
    p = {indexed[i]['efficiency_class'] for i in range(4)}
    e = {indexed[i]['efficiency_class'] for i in range(4, 8)}
    if len(p) != 1 or len(e) != 1 or min(p) <= max(e):
        raise ValueError('Expected P cores 0-3 and lower-efficiency-class E cores 4-7')
    return dict(policy=CPU_POLICY, p_cores=list(range(4)), e_cores=list(range(4, 8)), topology=rows)


def verify_topology():
    return validate_topology(topology())
