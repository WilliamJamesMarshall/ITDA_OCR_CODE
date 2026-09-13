"""Verify CPU affinity and kernel-enforced outbound denial for this Python runtime."""
import argparse
import ctypes
import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path
from scripts.prepare_sequential_rounds import BASE, ROOT, read, write, digest

def executable_paths():
    """Include physical paths: uv's minor-version interpreter directory is a junction."""
    paths = {sys.executable, sys._base_executable}
    if os.name == 'nt':
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel.GetModuleFileNameW.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_uint32]
        buffer = ctypes.create_unicode_buffer(32768)
        length = kernel.GetModuleFileNameW(None, buffer, len(buffer))
        if not length or length >= len(buffer): raise ctypes.WinError(ctypes.get_last_error())
        paths.add(buffer.value)
    return sorted(paths | {str(Path(path).resolve(strict=True)) for path in paths})

def cpu_list(value):
    cpus = [int(i) for i in value.split(',')] if isinstance(value, str) else list(value)
    if len(cpus) != 4 or len(set(cpus)) != 4 or any(i < 0 or i >= 64 for i in cpus):
        raise ValueError('Exactly four distinct logical CPUs are required')
    return cpus

def limit_cpu(cpus=None):
    if os.name != 'nt': raise RuntimeError('This verifier is for the documented local Windows reproduction')
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.GetCurrentProcess.restype = ctypes.c_void_p
    process = kernel.GetCurrentProcess()
    affinity, system = ctypes.c_size_t(), ctypes.c_size_t()
    kernel.GetProcessAffinityMask.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_size_t), ctypes.POINTER(ctypes.c_size_t)]
    kernel.SetProcessAffinityMask.argtypes = [ctypes.c_void_p, ctypes.c_size_t]
    if not kernel.GetProcessAffinityMask(process, ctypes.byref(affinity), ctypes.byref(system)):
        raise ctypes.WinError(ctypes.get_last_error())
    requested = cpus if cpus is not None else os.environ.get('ITDA_CPU_SET')
    cpus = cpu_list(requested) if requested is not None else [i for i in range(64) if affinity.value & (1 << i)][:4]
    if len(cpus) != 4: raise RuntimeError('Four logical CPUs must be available')
    mask = sum(1 << i for i in cpus)
    if mask & system.value != mask:
        raise RuntimeError('Requested CPUs are not available on this machine')
    if not kernel.SetProcessAffinityMask(process, mask): raise ctypes.WinError(ctypes.get_last_error())
    if not kernel.GetProcessAffinityMask(process, ctypes.byref(affinity), ctypes.byref(system)) or affinity.value != mask:
        raise RuntimeError('CPU affinity verification failed')
    return cpus

def network_probe(require_denied=True):
    results = []
    for host in ('1.1.1.1', '8.8.8.8'):
        try:
            with socket.create_connection((host, 443), timeout=3): pass
            result = {'host': host, 'connected': True, 'winerror': None}
        except OSError as error:
            result = {'host': host, 'connected': False, 'winerror': getattr(error, 'winerror', None), 'error': str(error)}
        results.append(result)
    if require_denied and any(r['connected'] or r['winerror'] != 10013 for r in results):
        raise RuntimeError('Require explicit OS access-denied (WSAEACCES), not DNS errors or timeouts: ' + repr(results))
    return results

def enforce(cpus=None):
    return {'cpu_affinity': limit_cpu(cpus), 'network_probe': network_probe(),
            'python': sys.executable, 'base_python': sys._base_executable,
            'executable_paths': executable_paths()}

def qualify():
    from scripts.sequential_rounds import code_lock, model_lock
    proof = enforce()
    clean = BASE / 'clean-submission'
    # The separate preparation verifier must already have populated this clean copy.
    for name, sha in code_lock().items():
        if not (clean / name).exists() or digest(clean / name) != sha:
            raise RuntimeError('Refresh clean submission before qualification: ' + name)
    env = {**os.environ, 'JUPYTER_PATH': str(BASE / 'smoke-jupyter'),
           'ITDA_INPUT_DIR': str(BASE / 'smoke-input'), 'ITDA_OUTPUT_PATH': str(BASE / 'offline-submission.csv')}
    started = time.perf_counter()
    with (BASE / 'offline-notebook.log').open('w', encoding='utf-8') as log:
        subprocess.run([sys.executable, '-m', 'nbconvert', '--to', 'notebook', '--execute', 'predict.ipynb',
                        '--ExecutePreprocessor.timeout=2400', '--output', str(BASE / 'offline-executed.ipynb')],
                        cwd=clean, env=env, stdout=log, stderr=log, check=True, timeout=2400)
    proof['elapsed_seconds'] = time.perf_counter() - started
    proof['network_probe_after'] = network_probe()
    from scripts.prepare_sequential_rounds import csv_read
    if csv_read(BASE / 'offline-submission.csv') != csv_read(BASE / 'smoke-submission.csv'):
        raise RuntimeError('Offline notebook prediction changed')
    proof.update(status='passed', code=code_lock(), model=model_lock(ROOT / 'weights/paddle'),
                 official_document_sha256=digest(BASE / 'official_environment.md'),
                 sample='BMLC002247, previously exposed development image only',
                 scope='Windows reproduction: four logical CPUs and OS firewall denial; official CPU model, OS and RAM unspecified',
                 full_round_performance_verified=False)
    write(BASE / 'operating_environment_verified.json', proof)
    readiness = read(BASE / 'execution_readiness.json')
    readiness.update(formal_environment_verified=True, environment_blockers=[],
                     environment_evidence={'path': str(BASE / 'operating_environment_verified.json'),
                                           'sha256': digest(BASE / 'operating_environment_verified.json')})
    write(BASE / 'execution_readiness.json', readiness)
    print('Four-CPU offline Run All verified. Formal test still requires actual start instruction.')

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['qualify', 'probe', 'paths'])
    args = parser.parse_args()
    if args.action == 'qualify': qualify()
    elif args.action == 'probe': print(json.dumps({'cpu': limit_cpu(), 'network': network_probe(False)}))
    else: print(json.dumps(executable_paths()))

if __name__ == '__main__': main()
