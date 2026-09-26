"""Live mode: listen to new pump.fun launches and score each after a delay.

Uses the free PumpPortal data stream (wss://pumpportal.fun/api/data). This
module needs the optional ``websockets`` package. It is meant for people who
trade through a bot or terminal they cannot modify: run it next to the bot
and only buy tokens that come back with the label JA.
"""
from __future__ import annotations

import asyncio
import json
import time
from typing import Callable

from .rpc import SolanaRpc
from .scoring import ScoringConfig, Verdict

PUMPPORTAL_WS = "wss://pumpportal.fun/api/data"


async def _worker(
    queue: "asyncio.Queue[tuple[float, str]]",
    scorer: Callable[[str], Verdict],
    on_verdict: Callable[[Verdict], None],
) -> None:
    while True:
        due, mint = await queue.get()
        wait = due - time.time()
        if wait > 0:
            await asyncio.sleep(wait)
        try:
            verdict = await asyncio.to_thread(scorer, mint)
            on_verdict(verdict)
        except Exception as exc:  # noqa: BLE001 - keep the stream alive
            print(f"[{mint[:8]}] Bewertung fehlgeschlagen: {exc}")
        finally:
            queue.task_done()


async def watch_async(
    rpc: SolanaRpc,
    delay_s: float,
    on_verdict: Callable[[Verdict], None],
    config: ScoringConfig | None = None,
    deep: bool = True,
    workers: int = 2,
) -> None:
    try:
        import websockets
    except ImportError as exc:
        raise SystemExit("Für den Watch-Modus fehlt das Paket 'websockets': pip install websockets") from exc

    from . import evaluate_token

    queue: "asyncio.Queue[tuple[float, str]]" = asyncio.Queue()
    scorer = lambda mint: evaluate_token(mint, rpc=rpc, config=config, deep=deep)  # noqa: E731
    tasks = [asyncio.create_task(_worker(queue, scorer, on_verdict)) for _ in range(workers)]
    try:
        while True:
            try:
                async with websockets.connect(PUMPPORTAL_WS, ping_interval=20) as ws:
                    await ws.send(json.dumps({"method": "subscribeNewToken"}))
                    print(f"Verbunden. Neue Token werden {delay_s:.0f} s nach dem Start bewertet.")
                    async for raw in ws:
                        try:
                            msg = json.loads(raw)
                        except ValueError:
                            continue
                        mint = msg.get("mint")
                        if not isinstance(mint, str):
                            continue
                        name = msg.get("name") or msg.get("symbol") or ""
                        print(f"neu: {mint} {name}".rstrip())
                        await queue.put((time.time() + delay_s, mint))
            except (OSError, asyncio.TimeoutError) as exc:
                print(f"Stream getrennt ({exc}), neuer Versuch in 5 s")
                await asyncio.sleep(5)
            except Exception as exc:  # noqa: BLE001
                print(f"Stream-Fehler ({exc}), neuer Versuch in 5 s")
                await asyncio.sleep(5)
    finally:
        for t in tasks:
            t.cancel()


def watch(rpc: SolanaRpc, delay_s: float, on_verdict: Callable[[Verdict], None], **kwargs) -> None:
    asyncio.run(watch_async(rpc, delay_s, on_verdict, **kwargs))
