"""Attach the grouped runner's shared execution lock to an already running trainer."""
import argparse
from pathlib import Path
import psutil
from scripts.audit_cumulative_1_5 import read, write_new
from scripts.grouped_rounds import exclusive, now


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', type=Path, required=True)
    args = parser.parse_args()
    run = args.run.resolve()
    state = read(run / 'training-run/runtime.json')
    assert state['status'] == 'training' and state['optimizer_steps'] > 0
    process = psutil.Process(state['pid'])
    expected = str(run / 'code/notebooks/project/scripts/train_cumulative_1_5.py').casefold()
    assert any(str(Path(arg)).casefold() == expected for arg in process.cmdline())
    lock = run.parent / 'locks/execution.lock'
    with exclusive(lock):
        write_new(run / 'shared-lock-attached.json', dict(attached_at=now(), trainer_pid=process.pid,
            trainer_create_time=process.create_time(), lock=str(lock),
            note='Attached after startup. The run-local supervisor lock already prevented duplicate cumulative launches.'))
        print('Shared execution lock attached; no training or test job is launched by this guard.', flush=True)
        process.wait()
    write_new(run / 'shared-lock-released.json', dict(released_at=now(), trainer_pid=process.pid,
                                                    note='Process exit is not itself proof of successful training.'))


if __name__ == '__main__':
    main()
