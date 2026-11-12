"""Picklable target for tests/test_parallel.py.

Kept in its own module because ``multiprocessing`` spawn pickles the function
by module name and re-imports it in the child process.
"""


def succeed(worker_id, payload, counter, lock, stop, out_queue, total):
	while True:
		with lock:
			if stop.is_set() or counter.value >= total:
				return
			counter.value += 1
		out_queue.put(("result", worker_id, True))
