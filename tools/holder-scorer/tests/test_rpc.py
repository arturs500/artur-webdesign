"""SolanaRpc against a stub HTTP session."""
from __future__ import annotations

import json
import threading
import time

import pytest

from holder_scorer.rpc import RpcError, SolanaRpc


class Resp:
    def __init__(self, status: int, body, headers=None):
        self.status_code = status
        self._body = body
        self.headers = headers or {}
        self.text = json.dumps(body) if not isinstance(body, str) else body

    def json(self):
        if isinstance(self._body, str):
            raise ValueError("not json")
        return self._body


class StubSession:
    def __init__(self, handler):
        self.handler = handler
        self.posts = []

    def post(self, url, json=None, timeout=None):
        self.posts.append(json)
        return self.handler(json)


def make(handler, **kw) -> SolanaRpc:
    return SolanaRpc("https://rpc.test", rps=1000, das_rps=1000, session=StubSession(handler), **kw)


def test_call_and_error_codes():
    def handler(body):
        if body["method"] == "ok":
            return Resp(200, {"jsonrpc": "2.0", "id": body["id"], "result": {"x": 1}})
        return Resp(200, {"jsonrpc": "2.0", "id": body["id"], "error": {"code": -32601, "message": "Method not found"}})

    rpc = make(handler)
    assert rpc.call("ok", []) == {"x": 1}
    with pytest.raises(RpcError) as exc:
        rpc.call("nope", [])
    assert exc.value.code == -32601
    assert rpc.stats["requests"] == 2 and rpc.stats["by_method"] == {"ok": 1, "nope": 1}


def test_http_401_is_fatal_and_429_retries_with_retry_after():
    calls = {"n": 0}

    def handler(body):
        calls["n"] += 1
        if calls["n"] == 1:
            return Resp(429, "slow down", {"Retry-After": "0"})
        return Resp(200, {"jsonrpc": "2.0", "id": body["id"], "result": 7})

    rpc = make(handler)
    assert rpc.call("m", []) == 7 and rpc.stats["retries"] == 1
    bad = make(lambda body: Resp(401, "unauthorized"))
    with pytest.raises(RpcError) as exc:
        bad.call("m", [])
    assert exc.value.http_status == 401


def test_batch_and_sequential_fallback():
    def batch_handler(body):
        if isinstance(body, list):
            return Resp(200, [{"jsonrpc": "2.0", "id": b["id"], "result": b["params"][0]} if b["params"][0] != "bad" else {"jsonrpc": "2.0", "id": b["id"], "error": {"code": 1, "message": "x"}} for b in body])
        return Resp(200, {"jsonrpc": "2.0", "id": body["id"], "result": "single"})

    rpc = make(batch_handler, max_batch=2)
    out = rpc.batch([("getTransaction", ["a"]), ("getTransaction", ["bad"]), ("getTransaction", ["c"])])
    assert out == ["a", None, "c"]
    assert rpc.stats["requests"] == 3 and rpc.stats["posts"] == 2

    def no_batch(body):
        if isinstance(body, list):
            return Resp(200, {"jsonrpc": "2.0", "error": {"code": -32600, "message": "batch not supported"}})
        return Resp(200, {"jsonrpc": "2.0", "id": body["id"], "result": body["params"][0]})

    rpc2 = make(no_batch)
    assert rpc2.batch([("getTransaction", ["a"]), ("getTransaction", ["b"])]) == ["a", "b"]
    rpc3 = make(lambda body: Resp(403, "forbidden"))
    with pytest.raises(RpcError):
        rpc3.batch([("getTransaction", ["a"])])


def test_das_latch_only_on_method_not_found():
    def per_request_error(body):
        return Resp(200, {"jsonrpc": "2.0", "id": body["id"], "error": {"code": -32602, "message": "Invalid params"}})

    rpc = make(per_request_error)
    with pytest.raises(RpcError):
        rpc.das_get_token_accounts("mint")
    assert rpc.das_supported is None  # not latched: the next mint may work

    def not_found(body):
        return Resp(200, {"jsonrpc": "2.0", "id": body["id"], "error": {"code": -32601, "message": "Method not found"}})

    rpc2 = make(not_found)
    assert rpc2.das_get_token_accounts("mint") is None and rpc2.das_supported is False
    assert rpc2.das_get_token_accounts("other") is None and rpc2.stats["requests"] == 1  # no second call

    def ok(body):
        page = body["params"]["page"]
        items = [{"address": f"a{page}", "owner": f"o{page}", "amount": 5}]
        return Resp(200, {"jsonrpc": "2.0", "id": body["id"], "result": {"token_accounts": items}})

    rpc3 = make(ok)
    assert rpc3.das_get_token_accounts("mint") == [{"address": "a1", "owner": "o1", "amount": 5}] and rpc3.das_supported is True


def test_rate_limiter_is_thread_safe_and_stoppable():
    rpc = make(lambda body: Resp(200, {"jsonrpc": "2.0", "id": body["id"], "result": 1}))
    rpc.rps = 40.0
    t0 = time.monotonic()

    def work():
        for _ in range(10):
            rpc.call("m", [])

    threads = [threading.Thread(target=work) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    elapsed = time.monotonic() - t0
    assert rpc.stats["requests"] == 40
    assert elapsed >= 0.9  # 40 requests at 40 rps need about a second even across threads
    rpc.stop.set()
    with pytest.raises(RpcError):
        rpc.call("m", [])
