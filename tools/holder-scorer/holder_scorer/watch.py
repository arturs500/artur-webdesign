"""Live mode: listen to new pump.fun launches and score each after a delay.

Uses the free PumpPortal data stream (wss://pumpportal.fun/api/data). This
module needs the optional ``websockets`` package. It is meant for people who
trade through a bot or terminal they cannot modify: run it next to the bot
and only buy tokens that come back with the label JA.

pump.fun launches far more tokens per hour than a 10-requests-per-second
endpoint can score in depth, so the watcher (1) only accepts pump.fun pool
launches, (2) drops launches it cannot score within ``max_lateness`` seconds
of their due time, and (3) triages each token with one cheap signature
lookup before spending the full request budget on it.
"""
from __future__ import annotations

import asyncio
import json
import time
from typing import Callable

from .collect import ProfileCache
from .rpc import RpcError, SolanaRpc
from .scoring import ScoringConfig, Verdict

PUMPPORTAL_WS = "wss://pumpportal.fun/api/data"


def accept_launch(msg: dict) -> tuple[bool, str]:
    """Filter a PumpPortal frame: only create events on the pump.fun pool."""
    mint = msg.get("mint")
    if not isinstance(mint, str) or len(mint) < 32:
        return False, "kein Mint"
    if msg.get("txType", "create") != "create":
        return False, f"txType={msg.get('txType')}"
    pool = msg.get("pool") or "pump"
    if pool != "pump":
        return False, f"pool={pool}"
    return True, ""


async def _worker(
    queue: "asyncio.Queue[tuple[float, float, str]]",
    scorer: Callable[[str, float], Verdict | None],
    on_verdict: Callable[[Verdict], None],
    max_lateness: float,
    stats: dict[str, int],
) -> None:
    while True:
        due, launched_at, mint = await queue.get()
        try:
            wait = due - time.time()
            if wait > 0:
                await asyncio.sleep(wait)
            elif -wait > max_lateness:
                stats["skipped_late"] += 1
                print(f"[{mint[:8]}] übersprungen, {-wait:.0f} s zu spät (Rückstand {queue.qsize()})")
                continue
            verdict = await asyncio.to_thread(scorer, mint, launched_at)
            if verdict is None:
                stats["skipped_prefilter"] += 1
            else:
                stats["scored"] += 1
                on_verdict(verdict)
        except RpcError as exc:
            if "abgebrochen" in str(exc):
                return
            print(f"[{mint[:8]}] RPC-Fehler: {exc}")
        except Exception as exc:  # noqa: BLE001 - keep the stream alive
            print(f"[{mint[:8]}] Bewertung fehlgeschlagen: {exc!r}")
        finally:
            queue.task_done()


async def watch_async(
    rpc: SolanaRpc,
    delay_s: float,
    on_verdict: Callable[[Verdict], None],
    config: ScoringConfig | None = None,
    deep: bool = True,
    workers: int = 2,
    max_lateness: float = 30.0,
    min_trades: int = 6,
    cache: ProfileCache | None = None,
) -> None:
    try:
        import websockets
    except ImportError as exc:
        raise SystemExit("Für den Watch-Modus fehlt das Paket 'websockets': pip install websockets") from exc

    from . import evaluate_token

    cache = cache or ProfileCache()
    queue: "asyncio.Queue[tuple[float, float, str]]" = asyncio.Queue(maxsize=max(4, 3 * workers))
    stats = {"seen": 0, "queued": 0, "dropped_full": 0, "skipped_late": 0, "skipped_prefilter": 0, "scored": 0}
    seen: set[str] = set()

    def scorer(mint: str, launched_at: float) -> Verdict | None:
        if min_trades > 0:
            sigs = rpc.get_signatures(mint, limit=200)
            if sum(1 for s in sigs if s.get("err") is None) < min_trades:
                return None
        return evaluate_token(mint, rpc=rpc, config=config, deep=deep, cache=cache, launch_hint=launched_at)

    tasks = [asyncio.create_task(_worker(queue, scorer, on_verdict, max_lateness, stats)) for _ in range(workers)]
    backoff = 5.0
    try:
        while True:
            try:
                async with websockets.connect(PUMPPORTAL_WS, ping_interval=20) as ws:
                    await ws.send(json.dumps({"method": "subscribeNewToken"}))
                    backoff = 5.0
                    print(f"Verbunden. pump.fun-Token werden {delay_s:.0f} s nach dem Start bewertet (Vorfilter: mindestens {min_trades} Transaktionen).")
                    async for raw in ws:
                        try:
                            msg = json.loads(raw)
                        except ValueError:
                            continue
                        if not isinstance(msg, dict):
                            continue
                        ok, why = accept_launch(msg)
                        if not ok:
                            if msg.get("mint"):
                                stats["seen"] += 1
                            continue
                        mint = msg["mint"]
                        stats["seen"] += 1
                        if mint in seen:
                            continue
                        seen.add(mint)
                        if len(seen) > 20_000:
                            seen.clear()
                        now = time.time()
                        try:
                            queue.put_nowait((now + delay_s, now, mint))
                            stats["queued"] += 1
                        except asyncio.QueueFull:
                            stats["dropped_full"] += 1
                            if stats["dropped_full"] % 25 == 1:
                                print(f"Warteschlange voll, Launches werden verworfen (bisher {stats['dropped_full']})")
                        if stats["queued"] % 50 == 0:
                            print(
                                f"Statistik: gesehen {stats['seen']}, geplant {stats['queued']}, verworfen {stats['dropped_full']}, "
                                f"zu spät {stats['skipped_late']}, Vorfilter {stats['skipped_prefilter']}, bewertet {stats['scored']}, "
                                f"Cache-Treffer {cache.hits}"
                            )
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001 - reconnect with backoff
                print(f"Stream getrennt ({exc!r}), neuer Versuch in {backoff:.0f} s")
                await asyncio.sleep(backoff)
                backoff = min(60.0, backoff * 2)
    finally:
        rpc.stop.set()
        for t in tasks:
            t.cancel()
        print(
            f"Beendet: gesehen {stats['seen']}, bewertet {stats['scored']}, zu spät {stats['skipped_late']}, "
            f"Vorfilter {stats['skipped_prefilter']}, verworfen {stats['dropped_full']}"
        )


def watch(rpc: SolanaRpc, delay_s: float, on_verdict: Callable[[Verdict], None], **kwargs) -> None:
    try:
        asyncio.run(watch_async(rpc, delay_s, on_verdict, **kwargs))
    except KeyboardInterrupt:
        rpc.stop.set()
