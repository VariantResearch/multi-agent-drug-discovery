"""Tests for the registry transport upgrade: persistent pooled
connections, the cross-run SQLite response cache with singleflight
deduplication, and the console's cache enablement.

Network-free: the pooled fetcher is exercised against a local
stdlib HTTP server on loopback, and the cache against a counting
fake base fetcher.
"""
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from madd import resolve
from madd.resolve import CachingFetcher, PooledFetcher


class _Handler(BaseHTTPRequestHandler):
    """Serve fixed routes; the server counts accepted connections."""

    protocol_version = "HTTP/1.1"  # keep-alive, like the real registries
    disable_nagle_algorithm = True  # production servers do not stall on Nagle

    def do_GET(self):
        """Route the test paths."""
        if self.path == "/ok":
            body = b'{"fine": true}'
            self.send_response(200)
        elif self.path == "/missing":
            body = b"nope"
            self.send_response(404)
        elif self.path == "/hop":
            body = b""
            self.send_response(302)
            self.send_header("Location", "/ok")
        else:
            body = b"?"
            self.send_response(500)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        """Silence the default stderr logging."""
        pass


class _CountingServer(ThreadingHTTPServer):
    """Threading server that counts how many connections it accepts."""

    daemon_threads = True

    def __init__(self, *args, **kwargs):
        """Init with a zeroed connection counter."""
        super().__init__(*args, **kwargs)
        self.connections = 0

    def get_request(self):
        """Count each accepted connection."""
        self.connections += 1
        return super().get_request()


@pytest.fixture()
def server():
    """Provide a running local server and its base URL."""
    srv = _CountingServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=srv.serve_forever, daemon=True)
    thread.start()
    yield srv, "http://127.0.0.1:" + str(srv.server_address[1])
    srv.shutdown()


def test_pooled_fetcher_reuses_connections(server):
    """Three sequential GETs ride one connection, not three."""
    srv, base = server
    fetch = PooledFetcher()
    for _ in range(3):
        status, body = fetch(base + "/ok")
        assert status == 200 and "fine" in body
    assert srv.connections == 1


def test_pooled_fetcher_statuses_and_redirect(server):
    """Error statuses return instead of raising; redirects resolve."""
    srv, base = server
    fetch = PooledFetcher()
    status, body = fetch(base + "/missing")
    assert status == 404 and body == "nope"
    status, body = fetch(base + "/hop")
    assert status == 200 and "fine" in body


def test_cache_hit_skips_the_network(tmp_path):
    """A second fetch of a 200 URL comes from the cache."""
    calls = []

    def base(url):
        """Count calls and return a fixed JSON body."""
        calls.append(url)
        return 200, '{"n": ' + str(len(calls)) + "}"

    fetch = CachingFetcher(base, tmp_path / "cache.sqlite3")
    first = fetch("https://example.test/a")
    second = fetch("https://example.test/a")
    assert first == second == (200, '{"n": 1}')
    assert len(calls) == 1
    assert fetch.stats() == {"hits": 1, "misses": 1, "shared": 0}


def test_cache_never_stores_errors_and_expires(tmp_path):
    """Non-200s are not cached, and a zero TTL forces refetching."""
    calls = []

    def base(url):
        """Alternate 404 then 200 responses."""
        calls.append(url)
        return (404, "no") if len(calls) == 1 else (200, "yes")

    fetch = CachingFetcher(base, tmp_path / "c.sqlite3", ttl_seconds=0)
    assert fetch("https://example.test/b")[0] == 404
    assert fetch("https://example.test/b") == (200, "yes")
    assert fetch("https://example.test/b") == (200, "yes")
    assert len(calls) == 3  # 404 uncached, TTL 0: the 200 also refetched


def test_cache_singleflight_shares_one_fetch(tmp_path):
    """Concurrent same-URL calls collapse into one base fetch."""
    calls = []

    def slow_base(url):
        """Sleep briefly, then answer, counting invocations."""
        time.sleep(0.25)
        calls.append(url)
        return 200, "shared-body"

    fetch = CachingFetcher(slow_base, tmp_path / "s.sqlite3")
    results = []

    def worker():
        """Fetch the shared URL and record the result."""
        results.append(fetch("https://example.test/c"))

    threads = [threading.Thread(target=worker) for _ in range(6)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert results == [(200, "shared-body")] * 6
    assert len(calls) == 1
    stats = fetch.stats()
    assert stats["misses"] == 1 and stats["shared"] >= 1


def test_registry_fetcher_factory(tmp_path):
    """The factory returns the caching wrapper only with a path."""
    plain = resolve.registry_fetcher()
    assert isinstance(plain, PooledFetcher)
    cached = resolve.registry_fetcher(cache_path=tmp_path / "x.sqlite3")
    assert isinstance(cached, CachingFetcher)


def test_console_enables_the_registry_cache(tmp_path, monkeypatch):
    """Constructing the console manager points the cache env var
    into the runs directory when the operator has not set it."""
    import os

    from madd.gui import RunManager
    monkeypatch.delenv("MADD_REGISTRY_CACHE", raising=False)
    try:
        RunManager(str(tmp_path), None)
        assert os.environ["MADD_REGISTRY_CACHE"].endswith(
            "registry-cache.sqlite3")
    finally:
        # The manager set the variable outside monkeypatch's
        # bookkeeping; remove it so later tests see a clean env.
        os.environ.pop("MADD_REGISTRY_CACHE", None)
