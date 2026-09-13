"""Create isolated development copies without changing an approved release or test."""
import argparse
import shutil
from pathlib import Path

from scripts.grouped_plan import BASE, CPU_POLICY, cpu_set
from scripts.grouped_rounds import execution_release, source_lock, model_lock, evidence, now, exclusive
from scripts.prepare_sequential_rounds import write, digest


def prepare(destination, instruction, source_reference, base=BASE):
    base, destination = Path(base), Path(destination)
    with exclusive(base / 'locks/execution.lock'):
        release = execution_release(base, 2)
        protected = [base / 'groups/group_02_03/release/release.json', base / 'manifest_lock.json']
        protected += [base / 'rounds' / f'round_{n:02d}' / name for n in (2,3)
                      for name in ('initial_report.json', 'report.md', 'state.json', 'runtime.json')]
        before = {str(p): digest(p) for p in protected}
        destination.mkdir(parents=True, exist_ok=False)
        source = Path(release['code_root'])
        copies = {}
        for n in (2,3):
            target = destination / f'round_{n:02d}/code'
            for name in release['code']:
                output = target / name
                output.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source / name, output)
            shutil.copytree(release['weights'], target / 'weights/paddle')
            if source_lock(target) != release['code'] or model_lock(target / 'weights/paddle') != release['model']:
                raise ValueError('Development copy differs from selected release')
            copies[str(n)] = dict(code_root=str(target), cpus=cpu_set(n))
        if {str(p): digest(p) for p in protected} != before:
            raise ValueError('Protected initial evidence changed during preparation')
        record = dict(created_at=now(), instruction=instruction, source_reference=source_reference,
                      scope='Development profiling and structural implementation only; not training approval',
                      baseline=evidence(base / 'groups/group_02_03/release/release.json'),
                      cpu_policy=CPU_POLICY, protected_before=before, baseline_code=release['code'],
                      model=release['model'], copies=copies, training_authorized=False)
        write(destination / 'development.json', record)
        return record


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--destination', type=Path, required=True)
    parser.add_argument('--instruction', required=True)
    parser.add_argument('--source-reference', required=True)
    args = parser.parse_args()
    prepare(args.destination, args.instruction, args.source_reference)
    print(args.destination / 'development.json')


if __name__ == '__main__':
    main()
