"""Small JSON-RPC client for Solana with batching, retries and rate limiting.

Works with any RPC endpoint. The Helius DAS methods (``getTokenAccounts``,
``getAssetsByCreator``) are used when the endpoint supports them and skipped
otherwise, so every feature that depends on them degrades gracefully.
"""
from __future__ import annotations

import base64
import time
from typing import Any

import requests


class RpcError(RuntimeError):
    def __init__(self, message: str, code: int | None = None):
        super().__init__(message)
        self.code = code


class SolanaRpc:
    def __init__(
        self,
        url: str,
        rps: float = 10.0,
        timeout: float = 25.0,
        max_batch: int = 20,
        max_retries: int = 4,
        session: requests.Session | None = None,
    ):
        self.url = url
        self.rps = max(0.1, rps)
        self.timeout = timeout
        self.max_batch = max(1, max_batch)
        self.max_retries = max_retries
        self.session = session or requests.Session()
        self._next_allowed = 0.0
        self._id = 0
        self._das_supported: bool | None = None
        self.stats = {"requests": 0, "retries": 0}

    # --- transport -------------------------------------------------------------
    def _throttle(self, units: int) -> None:
        now = time.monotonic()
        if self._next_allowed > now:
            time.sleep(self._next_allowed - now)
            now = self._next_allowed
        self._next_allowed = now + units / self.rps

    def _post(self, body: Any, units: int) -> Any:
        last_exc: Exception | None = None
        for attempt in range(self.max_retries + 1):
            self._throttle(units)
            try:
                self.stats["requests"] += units
                resp = self.session.post(self.url, json=body, timeout=self.timeout)
            except requests.RequestException as exc:
                last_exc = exc
                resp = None
            if resp is not None:
                if resp.status_code == 200:
                    try:
                        return resp.json()
                    except ValueError as exc:
                        last_exc = exc
                elif resp.status_code in (429, 500, 502, 503, 504):
                    last_exc = RpcError(f"HTTP {resp.status_code}: {resp.text[:200]}")
                else:
                    raise RpcError(f"HTTP {resp.status_code}: {resp.text[:300]}")
            if attempt < self.max_retries:
                self.stats["retries"] += 1
                time.sleep(0.5 * (2**attempt))
        raise RpcError(f"RPC request failed after retries: {last_exc}")

    def _next_id(self) -> int:
        self._id += 1
        return self._id

    def call(self, method: str, params: Any) -> Any:
        payload = {"jsonrpc": "2.0", "id": self._next_id(), "method": method, "params": params}
        data = self._post(payload, 1)
        if isinstance(data, dict) and "error" in data:
            err = data["error"] or {}
            raise RpcError(f"{method}: {err.get('message', err)}", err.get("code"))
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
            try:
                data = self._post(payload, len(payload))
            except RpcError:
                data = None
            if isinstance(data, list):
                for item in data:
                    if isinstance(item, dict) and item.get("id") in ids and "error" not in item:
                        results[ids[item["id"]]] = item.get("result")
                continue
            # Endpoint does not accept batches: fall back to sequential calls.
            for offset, (method, params) in enumerate(chunk):
                try:
                    results[start + offset] = self.call(method, params)
                except RpcError:
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

    def get_token_largest_accounts(self, mint: str) -> list[dict[str, Any]]:
        res = self.call("getTokenLargestAccounts", [mint, {"commitment": "confirmed"}])
        return (res or {}).get("value") or []

    # --- Helius DAS -----------------------------------------------------------
    def das_get_token_accounts(self, mint: str, max_pages: int = 5) -> list[dict[str, Any]] | None:
        """All token accounts of a mint as ``{owner, amount}`` or None if unsupported."""
        if self._das_supported is False:
            return None
        accounts: list[dict[str, Any]] = []
        page = 1
        while page <= max_pages:
            params = {"mint": mint, "limit": 1000, "page": page, "options": {"showZeroBalance": False}}
            try:
                res = self.call("getTokenAccounts", params)
            except RpcError as exc:
                if exc.code in (-32601, -32602) or "not found" in str(exc).lower() or "unknown" in str(exc).lower():
                    self._das_supported = False
                    return None
                raise
            self._das_supported = True
            items = (res or {}).get("token_accounts") or []
            for item in items:
                try:
                    accounts.append({"owner": item["owner"], "amount": int(item.get("amount", 0))})
                except (KeyError, TypeError, ValueError):
                    continue
            if len(items) < 1000:
                break
            page += 1
        return accounts

    def das_get_assets_by_creator(self, creator: str, max_pages: int = 3) -> list[str] | None:
        if self._das_supported is False:
            return None
        mints: list[str] = []
        page = 1
        while page <= max_pages:
            params = {"creatorAddress": creator, "onlyVerified": False, "page": page, "limit": 1000}
            try:
                res = self.call("getAssetsByCreator", params)
            except RpcError as exc:
                if exc.code in (-32601, -32602) or "not found" in str(exc).lower() or "unknown" in str(exc).lower():
                    self._das_supported = False
                    return None
                raise
            self._das_supported = True
            items = (res or {}).get("items") or []
            mints.extend(str(item.get("id")) for item in items if item.get("id"))
            if len(items) < 1000:
                break
            page += 1
        return mints
