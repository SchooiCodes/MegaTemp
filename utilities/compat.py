import asyncio

if not hasattr(asyncio, "coroutine"):
	asyncio.coroutine = lambda f: f
