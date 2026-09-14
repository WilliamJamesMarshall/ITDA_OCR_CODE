"""Opt-in predictor timings; generator consumer time is excluded."""
import json
import time
from contextlib import contextmanager
from pathlib import Path


class Profile:
    def __init__(self, path):
        self.path = Path(path) if path else None
        self.image_id = None
        if self.path:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.open('x', encoding='utf-8').close()

    def emit(self, **event):
        if self.path:
            with self.path.open('a', encoding='utf-8') as stream:
                stream.write(json.dumps(dict(image_id=self.image_id, **event)) + '\n')

    @contextmanager
    def measure(self, stage):
        wall, cpu = time.perf_counter(), time.process_time()
        error = None
        try:
            yield
        except BaseException as exc:
            error = repr(exc)
            raise
        finally:
            self.emit(stage=stage, wall_seconds=time.perf_counter()-wall,
                      cpu_seconds=time.process_time()-cpu, error=error)

    def wrap(self, model, stage):
        return TimedPredictor(model, self, stage) if self.path else model


class TimedPredictor:
    def __init__(self, model, profile, stage):
        object.__setattr__(self, '_model', model)
        object.__setattr__(self, '_profile', profile)
        object.__setattr__(self, '_stage', stage)

    def __getattr__(self, name):
        return getattr(self._model, name)

    def __setattr__(self, name, value):
        # Recovery temporarily swaps post_op for CTC evidence. Forward mutations.
        setattr(self._model, name, value)

    def __call__(self, *args, **kwargs):
        wall, cpu, count = 0., 0., 0
        error = None
        values = args[0] if args and isinstance(args[0], list) else list(args[:1])
        shapes = [list(v.shape) for v in values if hasattr(v, 'shape')]
        started, processor = time.perf_counter(), time.process_time()
        try:
            iterator = iter(self._model(*args, **kwargs))
        except BaseException as exc:
            self._profile.emit(stage=self._stage, wall_seconds=time.perf_counter()-started,
                               cpu_seconds=time.process_time()-processor, results=0, shapes=shapes, error=repr(exc))
            raise
        wall += time.perf_counter()-started
        cpu += time.process_time()-processor
        try:
            while True:
                started, processor = time.perf_counter(), time.process_time()
                try:
                    value = next(iterator)
                except StopIteration:
                    break
                finally:
                    wall += time.perf_counter()-started
                    cpu += time.process_time()-processor
                count += 1
                yield value
        except BaseException as exc:
            error = repr(exc)
            raise
        finally:
            close = getattr(iterator, 'close', None)
            if close:
                close()
            self._profile.emit(stage=self._stage, wall_seconds=wall, cpu_seconds=cpu,
                               results=count, shapes=shapes, error=error)
