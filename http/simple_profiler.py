import time
import json

class SimpleProfiler:
    class BlockContext:
        def __init__(self, name, prof):
            self.prof = prof
            self.name = name

        def __enter__(self):
            self.start = time.time_ns()

        def __exit__(self, exc_type, exc_value, traceback):
            self.prof.add_event(self.name, time.time_ns() - self.start)

    def __init__(self):
        self.timed_events = {}
        self.tags = []

    def add_tag(self, category):
        self.tags.append(category)

    def set_total(self, total):
        self.total = total

    def start(self):
        self.start_time = time.time_ns()

    def end(self):
        self.total = time.time_ns() - self.start_time

    def measure_function(self, name):
        def _decorator(f):
            def __decorator(*args, **kwargs):
                start = time.time_ns()
                result = f(*args, **kwargs)
                self.add_event(name, time.time_ns() - start)
                return result
            return __decorator
        return _decorator

    def add_event(self, name, t):
        if name not in self.timed_events:
            self.timed_events[name] = [t]
        else:
            self.timed_events[name].append(t)

    def measure_block(self, name):
        return self.BlockContext(name, self)

    def log_to_file(self, filename):
        with open(filename, "a") as f:
            f.write(json.dumps({'tags': self.tags, 'total': self.total, 'events': self.timed_events}))
            f.write("\n")
