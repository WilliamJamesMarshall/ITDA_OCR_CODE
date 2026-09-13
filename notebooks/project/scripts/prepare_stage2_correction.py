"""Preserve the previous development attempt and prepare independent correction copies."""
import shutil
from pathlib import Path

from scripts.grouped_plan import BASE, cpu_set
from scripts.grouped_rounds import source_lock, model_lock, evidence, now, exclusive
from scripts.prepare_sequential_rounds import read, write, digest


def main():
    previous = BASE / 'performance-development-20260913'
    destination = BASE / 'correction-development-20260914-v2'
    plan = BASE / 'retest-stage2-20260913/error-analysis-20260914/correction_plan.md'
    instruction = ('수정작업 시작하고, 상기 수정계획안대로 수정이 완료되면 2회차/3회차 테스트도 실행한 후에 '
                   '그 결과를 정리해서 가져와. 그리고 테스트 과정에서 발생하는 powershell의 승인 요청도 전부 네가 승인으로 처리해.')
    with exclusive(BASE / 'locks/execution.lock'):
        old = read(previous / 'development.json')
        protected = dict(old['protected_before'])
        for n in (2, 3):
            code = previous / f'round_{n:02d}/code'
            for name, sha in source_lock(code).items():
                protected[str(code / name)] = sha
        for path in (BASE / 'retest-stage2-20260913').rglob('*'):
            if path.is_file():
                protected[str(path)] = digest(path)
        destination.mkdir(parents=True, exist_ok=False)
        copies = {}
        for n in (2, 3):
            source = previous / f'round_{n:02d}/code'
            target = destination / f'round_{n:02d}/code'
            shutil.copytree(source, target, ignore=shutil.ignore_patterns('__pycache__', '.pytest_cache'))
            if source_lock(target) != source_lock(source) or model_lock(target / 'weights/paddle') != old['model']:
                raise ValueError('Correction copy differs from its preserved baseline')
            copies[str(n)] = dict(code_root=str(target), cpus=cpu_set(n))
        write(destination / 'development.json', dict(
            created_at=now(), instruction=instruction, source_reference='current user message, 2026-09-14 Asia/Seoul',
            scope='Implement approved correction plan and retest rounds 2/3; no training or shared weights promotion',
            plan=evidence(plan), previous=evidence(previous / 'development.json'),
            protected_before=protected, baseline_code=source_lock(previous / 'round_02/code'),
            model=old['model'], copies=copies, training_authorized=False))
    print(destination)


if __name__ == '__main__':
    main()
