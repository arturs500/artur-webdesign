"""Small JSON-RPC client for Solana with batching, retries and rate limiting.

Works with any RPC endpoint. The Helius DAS method ``getTokenAccounts`` is
used when the endpoint supports it and skipped otherwise, so every feature
that depends on it degrades gracefully.

The client is thread-safe: the rate limiter reserves send slots under a lock,
so several collectors (the watch mode runs two) share one request budget.
Helius meters DAS calls separately from standard RPC calls, hence two
buckets. By default every item of a JSON-RPC batch counts as one request
unit, which is how Helius bills; set ``units_per_batch_item=False`` for an
endpoint that limits per HTTP request.
"""
from __future__ import annotations

import base64
import threading
import time
from typing import Any

import requests

DAS_METHODS = {"getTokenAccounts", "getAssetsByCreator", "getAsset", "getAssetsByOwner", "searchAssets", "getAssetBatch"}


class RpcError(RuntimeError):
    def __init__(self, message: str, code: int | None = None, http_status: int | None = None):
        super().__init__(message)
        self.code = code
        self.http_status = http_status


class SolanaRpc:
    def __init__(
        self,
        url: str,
        rps: float = 10.0,
        das_rps: float = 2.0,
        timeout: float = 25.0,
        max_batch: int = 20,
        max_retries: int = 4,
        units_per_batch_item: bool = True,
        session: requests.Session | None = None,
    ):
        self.url = url
        self.rps = max(0.1, rps)
        self.das_rps = max(0.1, das_rps)
        self.timeout = timeout
        self.max_batch = max(1, max_batch)
        self.max_retries = max_retries
        self.units_per_batch_item = units_per_batch_item
        self.session = session or requests.Session()
        self.stop = threading.Event()
        self._lock = threading.Lock()
        self._next_allowed = {"rpc": 0.0, "das": 0.0}
        self._id = 0
        self._das_supported: bool | None = None
        self.stats: dict[str, Any] = {"requests": 0, "posts": 0, "retries": 0, "by_method": {}}

    # --- transport -------------------------------------------------------------
    def _sleep(self, seconds: float) -> None:
        deadline = time.monotonic() + seconds
        while True:
            if self.stop.is_set():
                raise RpcError("abgebrochen")
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return
            time.sleep(min(0.2, remaining))

    def _throttle(self, units: int, group: str) -> None:
        rate = self.das_rps if group == "das" else self.rps
        with self._lock:
            now = time.monotonic()
            start = max(now, self._next_allowed[group])
            self._next_allowed[group] = start + units / rate
        if start > now:
            self._sleep(start - now)

    def _post(self, body: Any, units: int, group: str) -> Any:
        last_exc: Exception | None = None
        for attempt in range(self.max_retries + 1):
            if self.stop.is_set():
                raise RpcError("abgebrochen")
            self._throttle(units, group)
            with self._lock:
                self.stats["requests"] += units
                self.stats["posts"] += 1
            try:
                resp = self.session.post(self.url, json=body, timeout=self.timeout)
            except requests.RequestException as exc:
                last_exc = exc
                resp = None
            wait = 0.5 * (2**attempt)
            if resp is not None:
                if resp.status_code == 200:
                    try:
                        return resp.json()
                    except ValueError as exc:
                        last_exc = exc
                elif resp.status_code in (429, 500, 502, 503, 504):
                    last_exc = RpcError(f"HTTP {resp.status_code}: {resp.text[:200]}", http_status=resp.status_code)
                    retry_after = resp.headers.get("Retry-After")
                    if retry_after:
                        try:
                            wait = max(wait, min(30.0, float(retry_after)))
                        except ValueError:
                            pass
                else:
                    raise RpcError(f"HTTP {resp.status_code}: {resp.text[:300]}", http_status=resp.status_code)
            if attempt < self.max_retries:
                with self._lock:
                    self.stats["retries"] += 1
                self._sleep(wait)
        raise RpcError(f"RPC request failed after retries: {last_exc}", http_status=getattr(last_exc, "http_status", None))

    def _next_id(self) -> int:
        with self._lock:
            self._id += 1
            return self._id

    def _count(self, method: str, n: int = 1) -> None:
        with self._lock:
            self.stats["by_method"][method] = self.stats["by_method"].get(method, 0) + n

    def call(self, method: str, params: Any) -> Any:
        payload = {"jsonrpc": "2.0", "id": self._next_id(), "method": method, "params": params}
        self._count(method)
        data = self._post(payload, 1, "das" if method in DAS_METHODS else "rpc")
        if isinstance(data, dict) and "error" in data:
            err = data["error"] or {}
            code = err.get("code") if isinstance(err, dict) else None
            msg = err.get("message", err) if isinstance(err, dict) else err
            raise RpcError(f"{method}: {msg}", code)
        if not isinstance(data, dict):
            raise RpcError(f"{method}: unexpected response {str(data)[:200]}")
        return data.get("result")

    def batch(self, calls: list[tuple[str, Any]]) -> list[Any]:
        """Run several calls; returns results in order, ``None`` for failed items."""
        results: list[Any] = [None] * len(calls)
        for start in range(0, len(calls), self.max_batch):
            chunk = calls[start : start + self.max_batch]
            payload = []
            ids: dict[int, int] = {}
            for offset, (method, params) in enumerate(chunk):
                rid = self._next_id()
                ids[rid] = start + offset
                payload.append({"jsonrpc": "2.0", "id": rid, "method": method, "params": params})
                self._count(method)
            units = len(payload) if self.units_per_batch_item else 1
            try:
                data = self._post(payload, units, "rpc")
            except RpcError as exc:
                # Auth errors and a rate limit that survived the retries apply to every further request.
                if exc.http_status in (401, 403, 429) or "abgebrochen" in str(exc):
                    raise
                continue  # transport or 5xx failure after retries: leave this chunk None, never re-send item by item
            if isinstance(data, list):
                for item in data:
                    if isinstance(item, dict) and item.get("id") in ids and "error" not in item:
                        results[ids[item["id"]]] = item.get("result")
                continue
            # Endpoint does not accept batches: fall back to sequential calls.
            for offset, (method, params) in enumerate(chunk):
                try:
                    results[start + offset] = self.call(method, params)
                except RpcError as exc:
                    if exc.http_status in (401, 403) or "abgebrochen" in str(exc):
                        raise
                    results[start + offset] = None
        return results

    # --- standard methods -----------------------------------------------------
    def get_signatures(self, address: str, limit: int = 1000, before: str | None = None) -> list[dict[str, Any]]:
        opts: dict[str, Any] = {"limit": min(1000, max(1, limit)), "commitment": "confirmed"}
        if before:
            opts["before"] = before
        return self.call("getSignaturesForAddress", [address, opts]) or []

    def get_transactions(self, signatures: list[str]) -> dict[str, Any]:
        opts = {"encoding": "json", "maxSupportedTransactionVersion": 0, "commitment": "confirmed"}
        calls = [("getTransaction", [sig, opts]) for sig in signatures]
        results = self.batch(calls)
        return dict(zip(signatures, results))

    def get_account_data(self, address: str) -> bytes | None:
        res = self.call("getAccountInfo", [address, {"encoding": "base64", "commitment": "confirmed"}])
        value = (res or {}).get("value")
        if not value:
            return None
        return base64.b64decode(value["data"][0])

    def get_multiple_account_data(self, addresses: list[str]) -> list[bytes | None]:
        out: list[bytes | None] = []
        for start in range(0, len(addresses), 100):
            chunk = addresses[start : start + 100]
            res = self.call("getMultipleAccounts", [chunk, {"encoding": "base64", "commitment": "confirmed"}])
            for value in (res or {}).get("value") or [None] * len(chunk):
                out.append(base64.b64decode(value["data"][0]) if value else None)
        return out

    def get_token_account_owners(self, addresses: list[str]) -> dict[str, str]:
        """Map token-account addresses to their owner wallets (jsonParsed)."""
        owners: dict[str, str] = {}
        for start in range(0, len(addresses), 100):
            chunk = addresses[start : start + 100]
            res = self.call("getMultipleAccounts", [chunk, {"encoding": "jsonParsed", "commitment": "confirmed"}])
            for addr, value in zip(chunk, (res or {}).get("value") or []):
                try:
                    owners[addr] = value["data"]["parsed"]["info"]["owner"]
                except (TypeError, KeyError):
                    continue
        return owners

    def get_token_largest_accounts(self, mint: str) -> list[dict[str, Any]]:
        res = self.call("getTokenLargestAccounts", [mint, {"commitment": "confirmed"}])
        return (res or {}).get("value") or []

    # --- Helius DAS -----------------------------------------------------------
    @property
    def das_supported(self) -> bool | None:
        return self._das_supported

    def das_get_token_accounts(self, mint: str, max_pages: int = 5) -> list[dict[str, Any]] | None:
        """All token accounts of a mint as ``{address, owner, amount}``, or None if the endpoint has no DAS."""
        if self._das_supported is False:
            return None
        accounts: list[dict[str, Any]] = []
        page = 1
        while page <= max_pages:
            params = {"mint": mint, "limit": 1000, "page": page, "options": {"showZeroBalance": False}}
            try:
                res = self.call("getTokenAccounts", params)
            except RpcError as exc:
                # Only "method not found" (or a 404) proves the endpoint has no DAS; anything else is per-request.
                if exc.code == -32601 or exc.http_status == 404:
                    self._das_supported = False
                    return None
                raise
            self._das_supported = True
            items = (res or {}).get("token_accounts") or []
            for item in items:
                try:
                    accounts.append({"address": item.get("address"), "owner": item["owner"], "amount": int(item.get("amount", 0))})
                except (KeyError, TypeError, ValueError):
                    continue
            if len(items) < 1000:
                break
            page += 1
        return accounts
