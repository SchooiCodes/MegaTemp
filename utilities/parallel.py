"""Process-isolated worker pool used by ``main --isolate``.

Each worker runs in its own Python process with its own asyncio loop and its
own Chromium, so a crashed browser, a blocked event loop or a CPU-heavy
hashcash solve cannot stall the other workers.

Workers claim work atomically from a shared counter, report whole output
blocks over a single queue (the parent prints them, so lines never interleave)
and are stopped through a shared event.

The pool is generic: the caller passes a module-level ``target`` function that
is picklable by reference. Its signature is::

        target(worker_id, payload, counter, lock, stop, out_queue, total)

where ``payload`` is a per-worker dict of plain data.
"""

import multiprocessing
import queue

from utilities.etc import Colours

_FATAL_COLOUR = Colours.FAIL


def _terminate(procs) -> None:
	for proc in procs:
		proc.join(timeout=5)
	for proc in procs:
		if proc.is_alive():
			proc.terminate()
			proc.join(timeout=2)


def run_pool(
	target,
	worker_count: int,
	total: int,
	payloads: list[dict],
	on_line=None,
	on_result=None,
) -> tuple[int, int]:
	"""Run *worker_count* processes until *total* registrations are claimed.

	Returns ``(successes, failures)``. ``on_line(worker_id, text, colour)`` is
	called for every captured output line and ``on_result(worker_id, ok)`` for
	every finished registration.
	"""
	ctx = multiprocessing.get_context("spawn")
	out_queue = ctx.Queue()
	counter = ctx.Value("i", 0)
	lock = ctx.Lock()
	stop = ctx.Event()

	procs = []
	for worker_id in range(worker_count):
		proc = ctx.Process(
			target=target,
			args=(
				worker_id,
				payloads[worker_id],
				counter,
				lock,
				stop,
				out_queue,
				total,
			),
			name=f"megatem-worker-{worker_id}",
			daemon=True,
		)
		proc.start()
		procs.append(proc)

	successes = failures = 0
	try:
		while True:
			alive = any(proc.is_alive() for proc in procs)
			try:
				message = out_queue.get(timeout=0.2)
			except queue.Empty:
				if not alive:
					break
				continue

			kind = message[0]
			if kind == "line":
				_, worker_id, text, colour = message
				if on_line is not None:
					on_line(worker_id, text, colour)
			elif kind == "result":
				_, worker_id, ok = message
				if ok:
					successes += 1
				else:
					failures += 1
				if on_result is not None:
					on_result(worker_id, ok)
			elif kind == "fatal":
				_, worker_id, detail = message
				failures += 1
				if on_line is not None:
					on_line(worker_id, f"worker crashed: {detail}", _FATAL_COLOUR)
	except KeyboardInterrupt:
		stop.set()
		_terminate(procs)
		raise
	finally:
		stop.set()
		_terminate(procs)
		out_queue.close()

	return successes, failures
