import socket

import pytest_asyncio
from aiohttp import web


@pytest_asyncio.fixture
async def http_server():
    """Start local HTTP servers and close every runner after the test."""
    runners = []

    async def start(app):
        runner = web.AppRunner(app)
        await runner.setup()
        sock = socket.socket()
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
        site = web.SockSite(runner, sock)
        await site.start()
        runners.append(runner)
        return f"http://127.0.0.1:{port}"

    try:
        yield start
    finally:
        for runner in reversed(runners):
            await runner.cleanup()
