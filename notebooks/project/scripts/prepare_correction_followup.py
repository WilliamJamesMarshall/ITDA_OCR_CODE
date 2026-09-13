"""Fork a qualified diagnostic snapshot before changing its recovery routing."""
import shutil
import argparse
from scripts.grouped_plan import BASE, cpu_set
from scripts.grouped_rounds import source_lock, model_lock, evidence, exclusive, now
from scripts.prepare_sequential_rounds import read, write, digest


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--previous', required=True)
    parser.add_argument('--destination', required=True)
    args = parser.parse_args()
    previous = BASE/args.previous
    dest = BASE/args.destination
    if previous.parent != BASE or dest.parent != BASE:
        raise ValueError('Use a named immediate child of the grouped workspace')
    with exclusive(BASE/'locks/execution.lock'):
        record = read(previous/'development.json')
        protected = dict(record['protected_before'])
        for n in (2,3):
            source = previous/f'round_{n:02d}/code'
            protected.update({str(source/name):sha for name,sha in source_lock(source).items()})
        dest.mkdir(exist_ok=False)
        copies = {}
        for n in (2,3):
            source = previous/f'round_{n:02d}/code'
            target = dest/f'round_{n:02d}/code'
            shutil.copytree(source,target,ignore=shutil.ignore_patterns('__pycache__','.pytest_cache'))
            copies[str(n)] = dict(code_root=str(target),cpus=cpu_set(n))
        record.update(created_at=now(), previous=evidence(previous/'development.json'),
                      baseline_code=source_lock(previous/'round_02/code'), copies=copies,
                      protected_before=protected)
        write(dest/'development.json',record)
        for name in ('run_unit_tests.py','trace_replay.py'):
            shutil.copy2(previous/name,dest/name)
    print(dest)


if __name__ == '__main__': main()
