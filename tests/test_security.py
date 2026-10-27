"""Security hardening tests: host, origin, body caps, headers, fences."""

import http.client
import json
import os
import threading

import pytest

from madd import config
from madd.gui import MAX_POST_BODY, create_server
from madd.prompting import SYSTEM_PROMPT, build_user_prompt


@pytest.fixture()
def server(tmp_path):
    """A console server on an ephemeral port, state restored after."""
    saved_cache = os.environ.pop("MADD_REGISTRY_CACHE", None)
    srv = create_server("127.0.0.1", 0, runs_dir=str(tmp_path))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield srv, srv.server_address[1]
    srv.shutdown()
    config._REGISTRY_FETCHER = None
    if saved_cache is None:
        os.environ.pop("MADD_REGISTRY_CACHE", None)
    else:
        os.environ["MADD_REGISTRY_CACHE"] = saved_cache


def _request(port, method, path, host=None, headers=None, body=None):
    """One raw HTTP request with full header control."""
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=30)
    all_headers = dict(headers or {})
    if host is not None:
        all_headers["Host"] = host
    conn.request(method, path, body=body, headers=all_headers)
    response = conn.getresponse()
    data = response.read()
    result = (response.status, dict(response.getheaders()), data)
    conn.close()
    return result


def test_unknown_host_is_refused(server):
    """A rebinding-style Host gets 403 on reads and writes alike."""
    _, port = server
    status, _, _ = _request(port, "GET", "/api/runs",
                             host="evil.example.com")
    assert status == 403
    status, _, _ = _request(port, "POST", "/api/stop",
                            host="evil.example.com", body=b"{}")
    assert status == 403


def test_loopback_and_tunnel_hosts_are_served(server):
    """The two legitimate Host shapes both answer."""
    _, port = server
    status, _, _ = _request(port, "GET", "/api/runs",
                             host=f"127.0.0.1:{port}")
    assert status == 200
    status, _, _ = _request(port, "GET", "/api/runs",
                             host="madd.variantresearchgroup.com")
    assert status == 200


def test_cross_site_origin_post_is_refused(server):
    """A POST carrying another site's Origin is refused; same-site
    and header-less (non-browser) POSTs are not."""
    _, port = server
    status, _, _ = _request(
        port, "POST", "/api/stop", host=f"127.0.0.1:{port}",
        headers={"Origin": "https://evil.example.com"}, body=b"{}")
    assert status == 403
    status, _, _ = _request(
        port, "POST", "/api/stop", host=f"127.0.0.1:{port}",
        headers={"Origin": f"http://127.0.0.1:{port}"}, body=b"{}")
    assert status == 200
    status, _, _ = _request(port, "POST", "/api/stop",
                             host=f"127.0.0.1:{port}", body=b"{}")
    assert status == 200


def test_oversized_and_malformed_bodies_are_refused(server):
    """A body past the cap gets 413; a non-numeric length gets 400.

    The oversized case is sent over a raw socket with only a stub
    of the body: the server must refuse from the header alone,
    without waiting for (or buffering) the declared body. Sending
    the whole body through a client races the server's early
    response and close, which made this test intermittent.
    """
    import socket
    _, port = server
    with socket.create_connection(("127.0.0.1", port), timeout=30) as sock:
        sock.sendall((
            "POST /api/stop HTTP/1.1\r\n"
            f"Host: 127.0.0.1:{port}\r\n"
            "Content-Type: application/json\r\n"
            f"Content-Length: {MAX_POST_BODY + 1}\r\n\r\n"
            "{}").encode())
        response = sock.recv(4096).decode("utf-8", "replace")
    assert " 413 " in response.split("\r\n", 1)[0]
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=30)
    conn.putrequest("POST", "/api/stop")
    conn.putheader("Host", f"127.0.0.1:{port}")
    conn.putheader("Content-Length", "not-a-number")
    conn.endheaders()
    response = conn.getresponse()
    response.read()
    conn.close()
    assert response.status == 400


def test_security_headers_are_set(server):
    """The page carries the CSP; API responses carry the base set."""
    _, port = server
    status, headers, _ = _request(port, "GET", "/",
                                   host=f"127.0.0.1:{port}")
    assert status == 200
    assert headers.get("X-Content-Type-Options") == "nosniff"
    assert headers.get("X-Frame-Options") == "DENY"
    assert "frame-ancestors 'none'" in headers.get(
        "Content-Security-Policy", "")
    status, headers, _ = _request(port, "GET", "/api/runs",
                                   host=f"127.0.0.1:{port}")
    assert headers.get("X-Content-Type-Options") == "nosniff"
    assert headers.get("Referrer-Policy") == "no-referrer"


def test_prompts_fence_data_from_instructions():
    """Every prompt that embeds source or model text states the
    data boundary, and the research user prompt fences the frame."""
    user = build_user_prompt({"frame_id": "F-1"})
    assert "<<<BEGIN DATA>>>" in user and "<<<END DATA>>>" in user
    assert "never instructions" in user
    assert "Data boundary" in SYSTEM_PROMPT
    from madd.contradictions import CONTRADICTION_SYSTEM_PROMPT
    from madd.design import DESIGN_SYSTEM_PROMPT
    from madd.entailment import ENTAILMENT_SYSTEM_PROMPT
    from madd.meta_review import META_REVIEW_SYSTEM_PROMPT
    from madd.tournament import TOURNAMENT_SYSTEM_PROMPT
    for prompt in (CONTRADICTION_SYSTEM_PROMPT, DESIGN_SYSTEM_PROMPT,
                   ENTAILMENT_SYSTEM_PROMPT, META_REVIEW_SYSTEM_PROMPT,
                   TOURNAMENT_SYSTEM_PROMPT):
        assert "never instructions" in prompt
