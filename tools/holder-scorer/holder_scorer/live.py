"""Live-Modus: alerts as early as the chain allows, without polling.

Data flow:

* launches come from the free PumpPortal stream (``subscribeNewToken``);
  the create message already carries creator, name, symbol, uri, the dev's
  initial buy and the curve state
* trades come from the standard Solana websocket of your RPC provider:
  one ``logsSubscribe`` per tracked token; pump.fun writes every trade as a
  ``Program data:`` log line, so each notification is decoded on the spot,
  no ``getTransaction`` needed (a log without a decodable event is fetched
  once as fallback)
* the on-chain side checks that need RPC calls (creator history, wallet
  profiles, the create transaction's slot) run in the background and are
  only started once a token shows real buyers, within an hourly budget

Every token is re-scored after each trade (at most once a second) and
produces at most three alerts:

* BLICK: first real buyers, no warning signal, still no full verdict
* GO: the scorer's verdict incl. minimum quantities, no warning signal
* RUG / TOT: a token that got BLICK or GO turned bad (get out): dev dump,
  bundle or first buyers exiting, a price crash, a stall, or the market cap
  falling more than a third below its level at GO

Which thresholds apply is chosen by ``stufe`` 1 (careful), 2 (default) or 3
(aggressive: more calls, more wrong calls).
"""
from __future__ import annotations

import asyncio
import base64
import json
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Any, Callable

from .collect import (
    CreatorHistory,
    HolderInfo,
    ProfileCache,
    Snapshot,
    WalletProfile,
    _creator_history,
    _early_wallets,
    _fetch_json,
    derive_balances,
)
from .encoding import BorshError
from .extern import RECENT_ALERTS_MAX, TIER_RANK, append_row, feed_row, parse_migration, rugcheck_fetch
from .fair import FairConfig, FairResult, fair_check, fair_line
from .features import CREATION_WINDOW_SLOTS, compute_features
from .market import sol_usd
from .narrative import NameRegistry, ThemeRegistry, link_anchors, normalize, theme_line
from .narrative import terms as text_terms
from .profile import (
    CHECKPOINTS,
    DEFAULT_ENTRY_AGE_S,
    checkpoint_for,
    checkpoints_before,
    cp_key,
    early_vector,
    load_profile,
    profile_checkpoints,
    profile_suffix,
    similarity,
    ticks_from_trades,
)
from .pump import (
    COMPLETE_EVENT_DISC,
    CREATE_EVENT_DISC,
    INITIAL_REAL_TOKEN_RESERVES,
    INITIAL_VIRTUAL_SOL_RESERVES,
    INITIAL_VIRTUAL_TOKEN_RESERVES,
    LAMPORTS_PER_SOL,
    PUMP_PROGRAM_ID,
    TOKEN_DECIMALS,
    TOKEN_TOTAL_SUPPLY,
    TRADE_EVENT_DISC,
    BondingCurveState,
    CreateEvent,
    TradeEvent,
    decode_create_event,
    decode_trade_event,
    derive_bonding_curve,
    parse_transaction,
)
from .quick import QuickReport, go_blockers, report_from_features
from .rpc import RpcError, SolanaRpc
from .scoring import ScoringConfig, score_features
from .watch import PUMPPORTAL_WS, accept_launch

PROGRAM_DATA = "Program data: "
TRADE_B64_PREFIX = "vdt/007mYe"  # base64 of the TradeEvent discriminator
CREATE_B64_PREFIX = "G3KpTd7rY3"
COMPLETE_B64_PREFIX = "X3JhnNQumA"
VIRTUAL_TOKEN_OFFSET = INITIAL_VIRTUAL_TOKEN_RESERVES - INITIAL_REAL_TOKEN_RESERVES  # virtual - real tokens on a fresh curve
CREATION_WINDOW_S = 1.5  # trades arriving this soon after the create are treated as the creation block
BLICK_VETO_FLAGS = (
    "DEV-DUMP", "DEV-RAUS", "DEV-GROSS", "SERIE", "SCHNELL", "FUNDER", "FRISCH", "TOP1", "TOP10", "WASH", "BOTS",
    "SELF-PUMP", "EXIT", "DUMP", "STILL", "MAYHEM", "USDC", "UNSICHTBAR",
)


@dataclass
class LiveConfig:
    stufe: int = 2
    track_seconds: float = 240.0
    final_linger_s: float = 30.0
    idle_expire_s: float = 60.0  # drop a token that never saw an outside trade
    max_keep_alive_s: float = 1800.0  # hard cap for tokens a paper trader or other hook wants to keep watching
    eval_interval_s: float = 1.0
    blick_min_outside_buyers: int = 5
    blick_min_inflow_sol: float = 0.5
    blick_max_age_s: float = 60.0
    max_bundle_share: float = 0.10  # creation-block share above which neither BLICK nor GO is sent
    go_mc_drop: float = 0.35  # RUG alert when the market cap falls this far below its level at GO
    creator_scan_min_buyers: int = 5
    profiles_min_buyers: int = 5
    creator_scan_tx: int = 30
    max_side_tasks: int = 4
    max_http_tasks: int = 6
    rpc_units_per_hour: float = 4000.0  # budget for background RPC work (about 100 000 Helius credits a day)
    create_tx_delay_s: float = 2.0
    guessed_window_grace_s: float = 15.0  # with a guessed creation slot, wait this long for the real one
    max_alert_retries: int = 3
    commitment: str = "confirmed"
    fetch_missing_events: bool = True
    fetch_create_tx: bool = True
    include_link: bool = True
    tiers: tuple[str, ...] = ("BLICK", "GO", "WIDERRUF", "RUG", "GESPERRT")
    max_tracked: int = 400
    fair: FairConfig = field(default_factory=FairConfig)  # fairness gate (fair.py): the principles of docs/fair_launch.md as conditions
    tape_path: str | None = None  # append every seen trade of an alerted token here (JSONL), for offline replays
    tape_sample: float = 0.0  # share of tracked tokens taped from their first seen trade regardless of alerts (control group)
    # precision gate (profile.py): new holders in the last seconds, similarity to the saved good coins
    profile_path: str | None = None  # reference profile from `profil bauen`; without it only the holder-rise rule applies
    profile_min_similarity: float = 0.7  # GO needs at least this share of features inside the bands of good coins
    profile_required: bool = False  # True: no GO at all while no usable profile is loaded
    blick_min_holder_rise: int = 2  # new non-dev holders within holder_rise_window_s needed for BLICK ...
    go_min_holder_rise: int = 2  # ... and for GO
    holder_rise_window_s: float = 15.0
    watch_terms: tuple[str, ...] = ()  # --beobachte: a launch whose name, symbol or description carries one of these sends 👁️ WATCH at once
    # Außenquellen (extern.py, 0.3.6): record-only, no RPC
    extern_path: str | None = None  # --extern: graduations of the whole platform from the PumpPortal migration feed, Rugcheck rows
    rugcheck: bool = False  # one Rugcheck query per GO/GESPERRT into the extern file (HTTP group, outside the RPC budget)

    @classmethod
    def for_stufe(cls, stufe: int) -> tuple["LiveConfig", ScoringConfig]:
        if stufe <= 1:
            return cls(
                stufe=1, blick_min_outside_buyers=8, blick_min_inflow_sol=1.0, max_bundle_share=0.05, creator_scan_min_buyers=8,
                blick_min_holder_rise=3, go_min_holder_rise=3, fair=FairConfig.for_stufe(1),
            ), ScoringConfig()
        if stufe >= 3:
            scoring = ScoringConfig.early()
            scoring.min_age_s = 15.0
            scoring.yes_threshold = 55.0
            scoring.yes_min_outside_buyers = 4
            scoring.yes_min_outside_buys_120s = 3
            scoring.yes_min_net_inflow_120s_sol = 0.3
            return cls(stufe=3, blick_min_outside_buyers=3, blick_min_inflow_sol=0.25, max_bundle_share=0.15, creator_scan_min_buyers=3, fair=FairConfig.for_stufe(3)), scoring
        return cls(stufe=2, fair=FairConfig.for_stufe(2)), ScoringConfig.early()


@dataclass
class Alert:
    tier: str  # BLICK | GO | WIDERRUF | RUG
    report: QuickReport
    text: str
    state: "TokenState"


@dataclass
class TokenState:
    mint: str
    created_at: float
    creator: str
    create: CreateEvent
    bonding_curve: str
    trades: list[TradeEvent] = field(default_factory=list)
    seen_sigs: set[str] = field(default_factory=set)
    failed: int = 0
    curve: BondingCurveState | None = None
    curve_slot: int = 0
    last_trade_at: float | None = None
    create_slot_known: bool = False
    window_guessed: bool = False  # the creation slot was inferred from a late trade, bundles may be misclassified
    missing_sigs: list[str] = field(default_factory=list)
    missing_retries: dict[str, int] = field(default_factory=dict)
    creator_history: CreatorHistory | None = None
    creator_profile: WalletProfile | None = None
    creator_first_sig: str | None = None
    early_wallets: list[WalletProfile] = field(default_factory=list)
    metadata: dict[str, Any] | None = None
    metadata_ok: bool = False
    pending: set[str] = field(default_factory=set)
    done: set[str] = field(default_factory=set)
    tiers_sent: dict[str, float] = field(default_factory=dict)
    go_mc_sol: float | None = None
    last_eval: float = 0.0
    last_word: str = "?"
    final: bool = False
    final_at: float | None = None
    complete: bool = False
    dirty: bool = True
    alert_failures: int = 0
    tape_started: bool = False
    tape_control: bool = False  # taped as a random control token (tape_sample), not because of an alert
    profil: dict[str, Any] | None = None  # last precision check: holder rise, similarity, checkpoint vectors (see profile.py)
    profil_blockiert: bool = False  # a GO was held back by the holder-rise/profile gate at least once
    profil_cache: dict[str, tuple[int, dict[str, Any]]] = field(default_factory=dict)  # checkpoint -> (ticks up to it, vector)
    narrativ: dict[str, Any] | None = None  # theme wave of the launch stream: term, launches, devs, rank by inflow, shared source (OQ-028)
    welle_gezaehlt: bool = False
    fair: dict[str, Any] | None = None  # last fairness check (fair.py): ok, hard_ok, fails, pending, values
    wartet_gezaehlt: bool = False  # a GO was held back only by checks still loading (counted once)

    @property
    def age(self) -> float:
        return time.time() - self.created_at

    def outside_trades(self) -> int:
        return sum(1 for t in self.trades if t.user != self.creator)


def tape_sampled(mint: str, share: float) -> bool:
    """Deterministic sampling by mint hash, so the control group does not depend on run order or restarts."""
    import hashlib

    if share <= 0:
        return False
    if share >= 1:
        return True
    return int(hashlib.sha256(mint.encode("utf-8")).hexdigest()[:8], 16) / 2**32 < share


def _lamports(x: Any) -> int:
    try:
        v = float(x)
    except (TypeError, ValueError):
        return 0
    return int(round(v * LAMPORTS_PER_SOL)) if v < 10**7 else int(v)


def _raw_tokens(x: Any) -> int:
    try:
        v = float(x)
    except (TypeError, ValueError):
        return 0
    return int(round(v * 10**TOKEN_DECIMALS)) if v < 5 * 10**9 else int(v)


def parse_log_events(logs: list[str], program_id: str = PUMP_PROGRAM_ID) -> tuple[list[TradeEvent], list[CreateEvent], bool]:
    """Decode pump.fun events from ``Program data:`` log lines. Returns (trades, creates, completed).

    Only lines emitted while the pump.fun program is the innermost invocation are
    decoded: other programs (Raydium Launchpad, Moonshot) emit an event with the
    same Anchor discriminator but a different layout.
    """
    trades: list[TradeEvent] = []
    creates: list[CreateEvent] = []
    completed = False
    stack: list[str] = []
    for line in logs:
        if line.startswith("Program ") and " invoke [" in line:
            stack.append(line.split(" ")[1])
            continue
        if line.startswith("Program ") and (line.endswith(" success") or " failed" in line):
            if stack:
                stack.pop()
            continue
        if not line.startswith(PROGRAM_DATA) or (stack and stack[-1] != program_id):
            continue
        payload = line[len(PROGRAM_DATA) :]
        try:
            if payload.startswith(TRADE_B64_PREFIX):
                raw = base64.b64decode(payload)
                if raw[:8] == TRADE_EVENT_DISC:
                    trades.append(decode_trade_event(raw[8:]))
            elif payload.startswith(CREATE_B64_PREFIX):
                raw = base64.b64decode(payload)
                if raw[:8] == CREATE_EVENT_DISC:
                    creates.append(decode_create_event(raw[8:]))
            elif payload.startswith(COMPLETE_B64_PREFIX):
                raw = base64.b64decode(payload)
                if raw[:8] == COMPLETE_EVENT_DISC:
                    completed = True
        except (ValueError, BorshError):
            continue
    return trades, creates, completed


class LiveEngine:
    """The pure state machine: feed it launches and log notifications, read alerts from the callback.

    RPC side work is delegated to ``run_side_task(name, fn, done, delay, group)`` (a callable that runs
    ``fn`` in a thread and calls ``done`` with the result on the event loop) so tests can drive the
    engine synchronously. ``group`` is "rpc" or "http"; rpc work is subject to the hourly budget.
    """

    def __init__(
        self,
        rpc: SolanaRpc | None,
        config: LiveConfig,
        scoring: ScoringConfig,
        on_alert: Callable[[Alert], None],
        cache: ProfileCache | None = None,
        run_side_task: Callable[..., None] | None = None,
        price_hint: Callable[[], float | None] | None = None,
        on_evaluate: Callable[..., None] | None = None,
        keep_alive: Callable[[str, float], bool] | None = None,
    ):
        self.rpc = rpc
        self.cfg = config
        self.scoring = scoring
        self.on_alert = on_alert
        self.cache = cache or ProfileCache(ttl_s=7200.0)
        self.run_side_task = run_side_task
        self.price_hint = price_hint
        self.on_evaluate = on_evaluate  # (state, report, features, now) after every evaluation, e.g. the paper trader
        self.keep_alive = keep_alive  # (mint, now) -> True keeps a token subscribed beyond track_seconds
        self.names = NameRegistry()  # recent launch names, to spot copycats
        self.themes = ThemeRegistry()  # terms of all launches: a theme wave is the earliest narrative signal we receive
        self.anchors = ThemeRegistry(window_s=1800.0, min_launches=2, min_devs=2, min_ratio=1.0)  # shared social-link targets
        self.tokens: dict[str, TokenState] = {}
        self.stats = {
            "launches": 0, "tracked": 0, "trades": 0, "missing": 0, "dropped_missing": 0, "alerts": 0,
            "blick": 0, "go": 0, "rug": 0, "expired": 0, "side_tasks": 0, "side_skipped_budget": 0, "in_welle": 0, "watch": 0, "gesperrt": 0, "go_wartet": 0,
            "graduierungen": 0, "graduierungen_alarm": 0,
        }
        self.recent_alerts: "OrderedDict[str, str]" = OrderedDict()  # mint -> highest tier sent; joins migration events to our calls
        self.rugcheck_fetch: Callable[[str], dict[str, Any]] = rugcheck_fetch  # replaceable in tests (no network)
        self._budget_window_start = 0.0
        self._budget_units_start = 0
        self._lock = threading.Lock()
        self.profile: dict[str, Any] | None = None
        if config.profile_path:
            try:
                self.profile = load_profile(config.profile_path)
            except (OSError, ValueError) as exc:
                print(f"Profil {config.profile_path} nicht ladbar: {exc}")
                if config.profile_required:
                    raise

    # --- budget ---------------------------------------------------------------------------------
    def rpc_budget_ok(self, now: float | None = None) -> bool:
        """True while the background RPC work of the current hour is within the configured budget."""
        if self.rpc is None or not hasattr(self.rpc, "stats"):
            return True
        now = now if now is not None else time.time()
        units = int(self.rpc.stats.get("requests", 0))
        if now - self._budget_window_start >= 3600:
            self._budget_window_start, self._budget_units_start = now, units
        return (units - self._budget_units_start) < self.cfg.rpc_units_per_hour

    # --- launches ---------------------------------------------------------------------------
    def on_launch(self, msg: dict[str, Any], now: float | None = None) -> TokenState | None:
        now = now if now is not None else time.time()
        ok, _ = accept_launch(msg)
        if not ok:
            return None
        mint = msg["mint"]
        if mint in self.tokens:
            return None
        self.stats["launches"] += 1
        if len(self.tokens) >= self.cfg.max_tracked:
            self.stats["dropped_full"] = self.stats.get("dropped_full", 0) + 1  # visible instead of silent
            return None
        creator = msg.get("traderPublicKey") or msg.get("creator") or ""
        curve_key = msg.get("bondingCurveKey") or derive_bonding_curve(mint)
        create = CreateEvent(
            name=str(msg.get("name") or ""),
            symbol=str(msg.get("symbol") or ""),
            uri=str(msg.get("uri") or ""),
            mint=mint,
            bonding_curve=curve_key,
            user=creator,
            creator=creator,
            timestamp=int(now),
            virtual_token_reserves=INITIAL_VIRTUAL_TOKEN_RESERVES,
            virtual_sol_reserves=INITIAL_VIRTUAL_SOL_RESERVES,
            real_token_reserves=INITIAL_REAL_TOKEN_RESERVES,
            token_total_supply=TOKEN_TOTAL_SUPPLY,
            is_mayhem_mode=bool(msg.get("is_mayhem_mode")) if "is_mayhem_mode" in msg else None,
            signature=str(msg.get("signature") or ""),
            slot=0,
            block_time=int(now),
        )
        state = TokenState(mint=mint, created_at=now, creator=creator, create=create, bonding_curve=curve_key)
        # the create transaction's own log notification (if the subscription is fast enough) is welcome:
        # it carries the real slot and the exact dev buy, so its signature is deliberately not marked as seen
        v_tokens = _raw_tokens(msg.get("vTokensInBondingCurve") or 0) or INITIAL_VIRTUAL_TOKEN_RESERVES
        v_sol = _lamports(msg.get("vSolInBondingCurve") or 0) or INITIAL_VIRTUAL_SOL_RESERVES
        initial_buy = _raw_tokens(msg.get("initialBuy") or 0)
        sol_amount = _lamports(msg.get("solAmount") or 0)
        if initial_buy > 0 and creator:
            if sol_amount <= 0:
                sol_amount = max(0, v_sol - INITIAL_VIRTUAL_SOL_RESERVES)
            state.trades.append(
                TradeEvent(
                    mint=mint,
                    sol_amount=sol_amount,
                    token_amount=initial_buy,
                    is_buy=True,
                    user=creator,
                    timestamp=int(now),
                    virtual_sol_reserves=v_sol,
                    virtual_token_reserves=v_tokens,
                    real_sol_reserves=max(0, v_sol - INITIAL_VIRTUAL_SOL_RESERVES),
                    real_token_reserves=max(0, v_tokens - VIRTUAL_TOKEN_OFFSET),
                    creator=creator,
                    ix_name="create",
                    signature=create.signature,
                    slot=0,
                    block_time=int(now),
                )
            )
            self._update_curve(state, state.trades[-1])
        self.tokens[mint] = state
        self.stats["tracked"] = len(self.tokens)
        self.names.register(mint, create.name, create.symbol, now)
        self.themes.register(mint, creator, [create.name, create.symbol], now)
        self._schedule_metadata(state)
        hits = self.watch_hits(create.name, create.symbol)
        if hits:
            self.themes.register(mint, creator, hits, now, raw=True)  # a watched term inside a longer name still counts for its wave
            self._watch_alert(state, hits, "Name", now)
        return state

    # --- trades -----------------------------------------------------------------------------
    # --- Außenquellen (0.3.6, OQ-033): Migrationsfeed und Rugcheck, record-only ----------------------------------
    def _extern_write(self, row: dict[str, Any]) -> None:
        if not self.cfg.extern_path:
            return
        try:
            append_row(self.cfg.extern_path, row)
        except OSError as exc:
            print(f"Außenquellen-Datei nicht schreibbar: {exc!r}")

    def on_feed(self, ereignis: str, now: float | None = None) -> None:
        """Verbindungsereignis des Migrationsfeeds protokollieren (Lücken sind später Rechtszensur im Report)."""
        self._extern_write(feed_row(ereignis, now if now is not None else time.time()))

    def _remember_alert(self, mint: str, tier: str) -> None:
        if tier not in TIER_RANK:
            return
        prev = self.recent_alerts.get(mint)
        if prev is None or TIER_RANK[tier] > TIER_RANK[prev]:
            self.recent_alerts[mint] = tier
            self.recent_alerts.move_to_end(mint)
        while len(self.recent_alerts) > RECENT_ALERTS_MAX:
            self.recent_alerts.popitem(last=False)

    def on_migration(self, msg: dict[str, Any], now: float | None = None) -> bool:
        """Eine Graduation vom PumpPortal-Migrationsfeed zählen und protokollieren. Ändert keinen Alarm.

        Der Token ist zu diesem Zeitpunkt längst nicht mehr im Blick (COMPLETE-Event, dann entfernt ihn ``tick``),
        darum läuft die Verknüpfung mit den eigenen Calls nur über das Alarm-Gedächtnis ``recent_alerts``.
        """
        now = now if now is not None else time.time()
        row = parse_migration(msg, now)
        if row is None:
            return False
        self.stats["graduierungen"] += 1
        alarm = self.recent_alerts.get(row["mint"])
        row["alarm"] = alarm
        if alarm:
            self.stats["graduierungen_alarm"] += 1
        self._extern_write(row)
        return True

    def _schedule_rugcheck(self, state: TokenState, tier: str) -> None:
        """Eine Rugcheck-Abfrage je Token, direkt über ``run_side_task``: ``_spawn`` lässt finale oder schon entfernte
        Token aus, also genau die interessanten Fälle. Mint und Tier by value; die Zeile wird in jedem Fall geschrieben."""
        if not (self.cfg.rugcheck and self.cfg.extern_path and self.run_side_task is not None) or "rugcheck" in state.done:
            return
        state.done.add("rugcheck")
        self.stats["side_tasks"] += 1
        mint = state.mint

        def done(row: Any) -> None:
            if not isinstance(row, dict):
                row = {"typ": "risiko", "t": round(time.time(), 3), "mint": mint, "quelle": "rugcheck", "status": 0, "fehlt": True}
            row["alarm"] = tier
            self._extern_write(row)

        fetcher = self.rugcheck_fetch
        self.run_side_task("rugcheck", lambda: fetcher(mint), done, 0.0, "http")

    def on_logs(self, mint: str, slot: int, signature: str, err: Any, logs: list[str], now: float | None = None) -> int:
        """Apply one logsNotification. Returns the number of trades added."""
        now = now if now is not None else time.time()
        state = self.tokens.get(mint)
        if state is None or signature in state.seen_sigs:
            return 0
        state.seen_sigs.add(signature)
        if err is not None:
            state.failed += 1
            return 0
        trades, creates, completed = parse_log_events(logs)
        if completed:
            state.complete = True
        for ce in creates:
            if ce.mint == mint:
                ce.slot, ce.signature = slot, signature
                had_uri = bool(state.create.uri)
                state.create = ce
                state.create_slot_known = True
                state.window_guessed = False
                if ce.uri and not had_uri:
                    self._schedule_metadata(state)
        added = 0
        for tr in trades:
            if tr.mint != mint:
                continue
            tr.slot, tr.signature, tr.block_time = slot, signature, int(now)
            if not tr.timestamp:
                tr.timestamp = int(now)
            self._add_trade(state, tr, now)
            added += 1
        truncated = any(line == "Log truncated" for line in logs)
        if (not trades and not creates and not completed) or truncated:
            # no decodable event, or Solana cut the log at 10 000 bytes: fetch the transaction once
            if self.cfg.fetch_missing_events:
                state.missing_sigs.append(signature)
                self.stats["missing"] += 1
        return added

    def _add_trade(self, state: TokenState, tr: TradeEvent, now: float) -> None:
        # The dev buy inside the create tx can arrive twice (synthetic from PumpPortal, then decoded): replace it.
        idx = next((i for i, t in enumerate(state.trades) if t.signature == tr.signature and t.user == tr.user and t.is_buy == tr.is_buy), None)
        if idx is not None:
            state.trades[idx] = tr
        else:
            state.trades.append(tr)
        if not state.create_slot_known and tr.slot:
            if now - state.created_at <= CREATION_WINDOW_S:
                # bundles land in the creation block: the earliest slot seen within 1.5 s stands in for slot 0
                state.create.slot = tr.slot if state.create.slot == 0 else min(state.create.slot, tr.slot)
            elif state.create.slot == 0:
                # no trade seen inside the creation window: put the create well before this trade (a guess)
                state.create.slot = max(0, tr.slot - CREATION_WINDOW_SLOTS - 1)
                state.window_guessed = True
            for t in state.trades:
                # the synthetic dev buy follows the create slot until the real create transaction is known
                if t.slot == 0 or (t.ix_name == "create" and t.signature == state.create.signature):
                    t.slot = state.create.slot
        state.trades.sort(key=lambda t: (t.slot, t.timestamp))
        state.last_trade_at = now
        if self.cfg.tape_path:
            if not state.tape_started and self.cfg.tape_sample > 0 and tape_sampled(state.mint, self.cfg.tape_sample):
                # control group: a deterministic random share of tokens is taped from the first seen trade on
                state.tape_started, state.tape_control = True, True
                for t in list(state.trades):
                    self._tape(state, t, now, backfill=True)
            elif state.tape_started:
                self._tape(state, tr, now)
        state.dirty = True
        self.stats["trades"] += 1
        self._update_curve(state, tr)
        if not state.create_slot_known and self.cfg.fetch_create_tx and state.create.signature and tr.user != state.creator:
            self._schedule_create_tx(state)

    def _update_curve(self, state: TokenState, tr: TradeEvent) -> None:
        if tr.virtual_token_reserves <= 0 or tr.slot < state.curve_slot:
            return  # an older transaction applied late must not roll the curve back
        state.curve_slot = tr.slot
        quote_is_sol = tr.quote_is_sol
        v_quote = tr.virtual_sol_reserves if quote_is_sol else (tr.virtual_quote_reserves or tr.virtual_sol_reserves)
        r_quote = tr.real_sol_reserves if quote_is_sol else (tr.real_quote_reserves or tr.real_sol_reserves)
        state.curve = BondingCurveState(
            virtual_token_reserves=tr.virtual_token_reserves,
            virtual_quote_reserves=v_quote,
            real_token_reserves=tr.real_token_reserves,
            real_quote_reserves=r_quote,
            token_total_supply=TOKEN_TOTAL_SUPPLY,
            complete=state.complete,
            creator=state.creator or None,
            quote_mint=None if quote_is_sol else tr.quote_mint,
            is_mayhem_mode=tr.mayhem_mode if tr.mayhem_mode is not None else state.create.is_mayhem_mode,
        )

    def apply_fetched_transactions(self, txs: dict[str, Any], now: float | None = None) -> int:
        """Fallback path: decode fetched transactions for signatures whose logs carried no event."""
        now = now if now is not None else time.time()
        added = 0
        for sig, tx in txs.items():
            parsed = parse_transaction(sig, tx)
            if parsed is None:
                continue
            for ce in parsed.creates:
                state = self.tokens.get(ce.mint)
                if state is not None:
                    had_uri = bool(state.create.uri)
                    state.create = ce
                    state.create_slot_known = True
                    state.window_guessed = False
                    state.dirty = True
                    for t in state.trades:
                        if t.ix_name == "create" and t.signature == ce.signature:
                            t.slot = ce.slot
                    if ce.uri and not had_uri:
                        self._schedule_metadata(state)  # about 5 % of PumpPortal frames carry no name/symbol/uri
            for tr in parsed.trades:
                state = self.tokens.get(tr.mint)
                if state is None:
                    continue
                if any(
                    t.signature == sig and t.user == tr.user and t.token_amount == tr.token_amount and t.ix_name != "create" for t in state.trades
                ):
                    continue
                if not tr.timestamp:
                    tr.timestamp = int(now)
                self._add_trade(state, tr, now)
                added += 1
        return added

    def take_missing(self, limit: int = 20) -> list[str]:
        out: list[str] = []
        for state in self.tokens.values():
            while state.missing_sigs and len(out) < limit:
                out.append(state.missing_sigs.pop(0))
            if len(out) >= limit:
                break
        return out

    def requeue_missing(self, sigs: list[str], max_retries: int = 2) -> int:
        """Put signatures back after a failed fetch; gives up after ``max_retries`` attempts each."""
        kept = 0
        for state in self.tokens.values():
            for sig in sigs:
                if sig in state.seen_sigs and sig not in state.missing_sigs:
                    n = state.missing_retries.get(sig, 0) + 1
                    if n <= max_retries:
                        state.missing_retries[sig] = n
                        state.missing_sigs.append(sig)
                        kept += 1
                    else:
                        self.stats["dropped_missing"] += 1
        return kept

    # --- side tasks ---------------------------------------------------------------------------
    def _spawn(
        self, state: TokenState, name: str, fn: Callable[[], Any], apply: Callable[[TokenState, Any], None], delay: float = 0.0, group: str = "rpc"
    ) -> None:
        if self.run_side_task is None or name in state.pending or name in state.done:
            return
        if group == "rpc" and not self.rpc_budget_ok():
            self.stats["side_skipped_budget"] += 1
            return
        state.pending.add(name)
        self.stats["side_tasks"] += 1

        def guarded() -> Any:
            # by the time a slot is free the token may be gone or final: then do not spend the request
            if state.mint not in self.tokens or state.final:
                return None
            return fn()

        def done(result: Any) -> None:
            state.pending.discard(name)
            state.done.add(name)
            if result is not None:
                apply(state, result)
            state.dirty = True

        self.run_side_task(name, guarded, done, delay, group)

    def _schedule_metadata(self, state: TokenState) -> None:
        if not state.create.uri:
            return

        def apply(st: TokenState, data: Any) -> None:
            self.apply_metadata(st, data)

        self._spawn(state, "metadata", lambda: _fetch_json(state.create.uri), apply, group="http")

    # --- theme wave and watch list (0.3.3, OQ-028) -----------------------------------------------------------
    def apply_metadata(self, state: TokenState, data: Any, now: float | None = None) -> None:
        """Take over fetched metadata and feed its terms and link targets into the theme and source registries."""
        if not isinstance(data, dict):
            return
        now = now if now is not None else time.time()
        state.metadata, state.metadata_ok = data, True
        desc = str(data.get("description") or "")[:200]
        self.themes.register(state.mint, state.creator, [desc], now)
        self.anchors.register(state.mint, state.creator, link_anchors(data), now, raw=True)
        hits = self.watch_hits(desc)
        if hits:
            self.themes.register(state.mint, state.creator, hits, now, raw=True)
            self._watch_alert(state, hits, "Beschreibung", now)

    def watch_hits(self, *texts: str | None) -> set[str]:
        """Watched terms (``--beobachte``) found in name, symbol or description: as a word, or inside the name."""
        watch = {w for w in (normalize(t) for t in self.cfg.watch_terms) if len(w) >= 3}
        if not watch:
            return set()
        words = text_terms(*texts, max_terms=50)
        blob = "".join(normalize(t) for t in texts if t)
        return {w for w in watch if w in words or (len(w) >= 4 and w in blob)}

    def _watch_alert(self, state: TokenState, hits: set[str], where: str, now: float) -> None:
        if "WATCH" in state.tiers_sent:
            return
        curve = state.curve
        mc = None
        if curve is not None and curve.virtual_token_reserves > 0:
            mc = curve.virtual_quote_reserves / curve.virtual_token_reserves * TOKEN_TOTAL_SUPPLY / LAMPORTS_PER_SOL
        report = QuickReport(
            mint=state.mint, word="WATCH", phase="curve", name=state.create.name or None, symbol=state.create.symbol or None,
            age_s=max(0.0, now - state.created_at), mc_sol=mc,
        )
        report.theme = theme_line(self._theme_check(state, now))
        self._emit(state, "WATCH", report, f"Beobachtungsliste: {', '.join(sorted(hits))} ({where})", now)

    @staticmethod
    def _outside_inflow_sol(state: TokenState) -> float:
        return sum((t.quote_lamports if t.is_buy else -t.quote_lamports) for t in state.trades if t.user != state.creator) / LAMPORTS_PER_SOL

    def _theme_check(self, state: TokenState, now: float) -> dict[str, Any] | None:
        """Theme of this coin in the launch stream: wave, rank by outside inflow among its theme, shared source. Information only."""
        st = self.themes.theme_for(state.mint, now)
        quelle = None
        for anchor in self.anchors.terms_of(state.mint):
            s = self.anchors.stats(anchor, now, state.mint)
            if s is not None and s.n_recent >= 2 and (quelle is None or s.n_recent > quelle["n"]):
                quelle = {"anker": anchor, "n": s.n_recent, "devs": s.devs_recent}
        if st is None and quelle is None:
            state.narrativ = None
            return None
        out: dict[str, Any] = {"thema": None, "quelle": quelle, "fenster_s": self.themes.window_s}
        if st is not None:
            inflows = sorted(((m, self._outside_inflow_sol(self.tokens[m])) for m in st.mints if m in self.tokens), key=lambda x: -x[1])
            rank = next((i + 1 for i, (m, _) in enumerate(inflows) if m == state.mint), None)
            out.update(
                thema=st.term, n=st.n_recent, devs=st.devs_recent, grundrate=st.baseline, verhaeltnis=st.ratio, welle=st.wave,
                position=st.position, rang=rank, beobachtet=len(inflows), zufluss_thema_sol=round(sum(v for _, v in inflows), 3),
            )
            if st.wave and not state.welle_gezaehlt:
                state.welle_gezaehlt = True
                self.stats["in_welle"] = self.stats.get("in_welle", 0) + 1
        state.narrativ = out
        return out

    def _schedule_create_tx(self, state: TokenState) -> None:
        if self.rpc is None:
            return
        sig = state.create.signature

        def fetch() -> Any:
            if state.create_slot_known:
                return None  # the create's own log notification arrived in the meantime
            txs = self.rpc.get_transactions([sig])
            if txs.get(sig) is None:
                time.sleep(2.0)  # not confirmed yet: one more try
                txs = self.rpc.get_transactions([sig])
            return txs

        def apply(st: TokenState, txs: Any) -> None:
            self.apply_fetched_transactions(txs)

        self._spawn(state, "create_tx", fetch, apply, delay=self.cfg.create_tx_delay_s)

    def _schedule_creator(self, state: TokenState) -> None:
        if self.rpc is None or not state.creator:
            return
        creator, mint, launch = state.creator, state.mint, int(state.created_at)
        scan_tx = self.cfg.creator_scan_tx

        def apply(st: TokenState, res: Any) -> None:
            st.creator_history, st.creator_profile, st.creator_first_sig = res

        self._spawn(state, "creator", lambda: _creator_history(self.rpc, creator, mint, launch, scan_tx, self.cache), apply)

    def _schedule_profiles(self, state: TokenState) -> None:
        if self.rpc is None:
            return
        devs = {state.creator}
        wallets: list[str] = []
        for t in state.trades:
            if t.is_buy and t.user not in devs and t.user not in wallets:
                wallets.append(t.user)
            if len(wallets) >= 4:
                break
        if not wallets:
            return
        launch = int(state.created_at)
        creator, first_sig = state.creator, state.creator_first_sig

        def apply(st: TokenState, res: Any) -> None:
            profiles, creator_funder, _notes = res
            st.early_wallets = profiles
            if creator_funder and st.creator_profile:
                st.creator_profile.funder = creator_funder

        self._spawn(state, "profiles", lambda: _early_wallets(self.rpc, wallets, launch, self.cache, creator, first_sig), apply)

    # --- evaluation ---------------------------------------------------------------------------
    def snapshot(self, state: TokenState, now: float) -> Snapshot:
        balances = derive_balances(state.trades)
        snap = Snapshot(
            mint=state.mint,
            bonding_curve=state.bonding_curve,
            collected_at=now,
            curve=state.curve,
            create=state.create,
            trades=list(state.trades),
            total_signatures=len(state.trades) + state.failed + (0 if state.trades and state.trades[0].ix_name == "create" else 1),
            failed_tx=state.failed,
            sig_meta=[],  # block times of failed txs are unknown here: never fabricate "failed after 30 s"
            history_ok=True,
            head_complete=True,
            partial_history=False,
            launch_hint=state.created_at,
            holders=[HolderInfo(o, a) for o, a in balances.items() if a > 0],
            holders_source="trades",
            metadata=state.metadata or {},
            metadata_ok=state.metadata_ok,
            creator_history=state.creator_history,
            creator_profile=state.creator_profile,
            early_wallets=list(state.early_wallets),
        )
        return snap

    def evaluate(self, state: TokenState, now: float | None = None) -> QuickReport:
        now = now if now is not None else time.time()
        snap = self.snapshot(state, now)
        feats = compute_features(snap, now)
        verdict = score_features(feats, self.scoring)
        price = self.price_hint() if self.price_hint else None
        report = report_from_features(state.mint, feats, verdict, self.scoring, None, price, state.create.name or None, state.create.symbol or None, "curve")
        report.theme = theme_line(self._theme_check(state, now))
        state.last_eval = now
        state.dirty = False
        state.last_word = report.word
        # side checks once the token shows real buyers
        if feats.unique_outside_buyers >= self.cfg.creator_scan_min_buyers:
            self._schedule_creator(state)
        if feats.unique_outside_buyers >= self.cfg.profiles_min_buyers:
            self._schedule_profiles(state)
        self._alerts(state, report, feats, now)
        if self.on_evaluate is not None:
            try:
                self.on_evaluate(state, report, feats, now)
            except Exception as exc:  # noqa: BLE001 - a hook must not stop the scoring loop
                print(f"[{state.mint[:8]}] Bewertungs-Hook fehlgeschlagen: {exc!r}")
        return report

    def _emit(self, state: TokenState, tier: str, report: QuickReport, suffix: str | None, now: float) -> None:
        from .notify import format_short

        text = format_short(report, suffix=suffix, link=self.cfg.include_link)
        try:
            self.on_alert(Alert(tier=tier, report=report, text=text, state=state))
        except Exception as exc:  # noqa: BLE001 - a broken callback must not lose the alert silently
            state.alert_failures += 1
            print(f"[{state.mint[:8]}] Alarm {tier} konnte nicht zugestellt werden: {exc!r}")
            if state.alert_failures < self.cfg.max_alert_retries:
                state.dirty = True  # retried on the next evaluation
                return
        state.tiers_sent[tier] = now
        self.stats["alerts"] += 1
        self.stats[tier.lower()] = self.stats.get(tier.lower(), 0) + 1
        self._remember_alert(state.mint, tier)
        if tier in ("GO", "GESPERRT"):
            self._schedule_rugcheck(state, tier)
        if self.cfg.tape_path and not state.tape_started:
            # first alert: back-fill everything seen so far, then stream every further trade (see _add_trade)
            state.tape_started = True
            for t in list(state.trades):
                self._tape(state, t, now, backfill=True)

    def _tape(self, state: TokenState, tr: TradeEvent, now: float, backfill: bool = False) -> None:
        """Append one seen trade of an alerted token to the tape (compact JSONL, append-only, never rewritten)."""
        import json

        row = {
            "mint": state.mint,
            "seen_at": round(now, 3),
            "t0": round(state.created_at, 3),
            "control": state.tape_control,
            "backfill": backfill,
            "slot": tr.slot,
            "ts": tr.timestamp,
            "sig": tr.signature,
            "buy": tr.is_buy,
            "user": tr.user,
            "sol": tr.sol_amount,
            "tok": tr.token_amount,
            "dev": state.creator or None,
            "vS": tr.virtual_sol_reserves,
            "vT": tr.virtual_token_reserves,
            "rS": tr.real_sol_reserves,
            "rT": tr.real_token_reserves,
            "fee": tr.fee,
            "creator_fee": tr.creator_fee,
        }
        try:
            with open(self.cfg.tape_path, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(row, separators=(",", ":")) + "\n")
        except OSError as exc:
            print(f"[{state.mint[:8]}] Tape nicht schreibbar: {exc!r}")

    def _profile_check(self, state: TokenState, now: float) -> dict[str, Any]:
        """Holder rise over the last seconds and similarity to the saved good coins, from the seen trades only.

        Checkpoint vectors are cached per (checkpoint, number of trades up to it): late-arriving trades
        refresh them, otherwise every evaluation costs one pass over the trades for the rise.
        """
        cfg = self.cfg
        out: dict[str, Any] = {
            "anstieg": 0,
            "fenster_s": cfg.holder_rise_window_s,
            "aehnlich": None,
            "checkpoint": None,
            "ausserhalb": [],
            "vektoren": {},
            "hash": self.profile.get("hash") if self.profile else None,
        }
        ticks = ticks_from_trades(state.trades)
        if not ticks:
            state.profil = out
            return out
        dev = state.creator or None
        vec_now = early_vector(ticks, now, dev, cfg.holder_rise_window_s)
        if vec_now is not None:
            out["anstieg"] = int(vec_now["holders_rise"])
            out["halter"] = int(vec_now["holders"])
        t0 = ticks[0].ts
        age = now - t0
        # vectors are recorded even without a profile: that is what a later `profil bauen` learns from
        cps = profile_checkpoints(self.profile) if self.profile else list(checkpoints_before(DEFAULT_ENTRY_AGE_S, CHECKPOINTS))
        for cp in cps:
            if cp > age:
                continue
            n_upto = sum(1 for t in ticks if t.ts <= t0 + cp)
            cached = state.profil_cache.get(cp_key(cp))
            if cached is None or cached[0] != n_upto:
                vec = early_vector(ticks, t0 + cp, dev, cfg.holder_rise_window_s)
                if vec is None:
                    continue
                cached = (n_upto, vec)
                state.profil_cache[cp_key(cp)] = cached
            out["vektoren"][cp_key(cp)] = cached[1]
        if self.profile:
            cp = checkpoint_for(age, cps)
            vec = out["vektoren"].get(cp_key(cp)) if cp is not None else None
            sim = similarity(self.profile, vec, cp) if vec is not None else None
            if sim is not None:
                out["aehnlich"], out["checkpoint"], out["ausserhalb"] = sim["aehnlich"], cp, sim["ausserhalb"]
        state.profil = out
        return out

    def _fair_check(self, state: TokenState, feats, now: float) -> FairResult:
        """The fairness principles (docs/fair_launch.md) against what the engine knows right now."""
        cfg = self.cfg
        if not state.create.uri:
            meta = "fehlt"
        elif state.metadata_ok:
            meta = "ok"
        elif "metadata" in state.done:
            meta = "fehler"
        else:
            meta = "laedt"
        checks_possible = self.run_side_task is not None
        res = fair_check(
            feats,
            cfg.fair,
            bundle_limit=cfg.max_bundle_share,
            copycat=self.names.is_copycat(state.mint, state.create.name, state.create.symbol, now),
            creator_done=state.creator_history is not None or "creator" in state.done,
            creator_possible=checks_possible and self.rpc is not None and cfg.creator_scan_min_buyers <= 1000,
            metadata_state=meta,
            checks_possible=checks_possible,
        )
        state.fair = res.to_dict()
        return res

    def _alerts(self, state: TokenState, report: QuickReport, feats, now: float) -> None:
        if state.final:
            return
        word = report.word
        age = now - state.created_at
        sent = state.tiers_sent
        cfg = self.cfg
        bundle_share = feats.creation_window_share
        bundle_ok = bundle_share is None or bundle_share < cfg.max_bundle_share
        # a creation slot inferred from a late trade may hide a bundle: wait a little for the real one
        window_uncertain = state.window_guessed and not state.create_slot_known and cfg.fetch_create_tx and age < cfg.guessed_window_grace_s
        veto = any(f.split(" ")[0] in BLICK_VETO_FLAGS for f in report.flags)
        # precision gate: are new holders still arriving right now, and does the start look like the saved good coins?
        prof = self._profile_check(state, now)
        rise_blick = prof["anstieg"] >= cfg.blick_min_holder_rise
        rise_go = prof["anstieg"] >= cfg.go_min_holder_rise
        if self.profile is None:
            sim_ok = not cfg.profile_required
        else:
            sim_ok = prof["aehnlich"] is not None and prof["aehnlich"] >= cfg.profile_min_similarity
        gate_text = profile_suffix(prof, self.profile is not None)
        # fairness gate: the principles of a fair launch as conditions (fast ones for BLICK, all for GO)
        fair = self._fair_check(state, feats, now)
        report.fair = fair_line(fair)
        if (
            "BLICK" in cfg.tiers
            and "BLICK" not in sent
            and "GO" not in sent
            and age <= cfg.blick_max_age_s
            and word not in ("RUG", "TOT", "GO")
            and not veto
            and bundle_ok
            and not window_uncertain
            and rise_blick
            and fair.hard_ok
            and feats.unique_outside_buyers >= cfg.blick_min_outside_buyers
            and (feats.organic_net_flow_120s_sol or 0.0) >= cfg.blick_min_inflow_sol
        ):
            blick = QuickReport(**{**report.__dict__})
            blick.word = "BLICK"
            self._emit(state, "BLICK", blick, gate_text, now)
        go_ok = (
            word == "GO"
            and not veto
            and bundle_ok
            and not window_uncertain
            and not go_blockers(report.flags, cfg.max_bundle_share)
            and (feats.organic_net_flow_120s_sol is None or feats.organic_net_flow_120s_sol > 0)
        )
        if "GO" in cfg.tiers and go_ok and "GO" not in sent:
            if rise_go and sim_ok and fair.ok:
                state.go_mc_sol = feats.mc_sol
                suffix = " · ".join(x for x in (("nach BLICK" if "BLICK" in sent else None), gate_text) if x) or None
                self._emit(state, "GO", report, suffix, now)
            else:
                if not (rise_go and sim_ok) and not state.profil_blockiert:
                    # the scorer said GO, the precision gate did not: counted once per token, visible in the status line
                    state.profil_blockiert = True
                    self.stats["go_profil"] = self.stats.get("go_profil", 0) + 1
                # a definitive breach (not a check still loading, not a momentary holder dip) is recorded once as GESPERRT,
                # so `tape report --tiers GESPERRT` can later show whether the gate kept bad coins out
                reasons = list(fair.fails)
                if self.profile is not None and not sim_ok and prof["aehnlich"] is not None:
                    reasons.append(f"Profil {prof['aehnlich'] * 100:.0f} % unter {cfg.profile_min_similarity * 100:.0f} %")
                if reasons and "GESPERRT" in cfg.tiers and "GESPERRT" not in sent:
                    out = QuickReport(**{**report.__dict__})
                    out.word = "GESPERRT"
                    self._emit(state, "GESPERRT", out, "statt GO · " + "; ".join(reasons[:3]), now)
                elif not reasons and fair.pending and rise_go and sim_ok and not state.wartet_gezaehlt:
                    # nothing is wrong yet, a check is still loading: visible in the status line instead of a silent sniper
                    state.wartet_gezaehlt = True
                    self.stats["go_wartet"] = self.stats.get("go_wartet", 0) + 1
        bad = word in ("RUG", "TOT")
        # a soft veto after BLICK (SCHNELL, FRISCH, FUNDER, UNSICHTBAR, bundle over the limit, ...) used to stay
        # silent: the phone kept a stale BLICK while the engine had already ruled the token out. Say so once.
        blockers = go_blockers(report.flags, cfg.max_bundle_share)
        if (
            "WIDERRUF" in cfg.tiers
            and "BLICK" in sent
            and "GO" not in sent
            and "RUG" not in sent
            and "WIDERRUF" not in sent
            and not bad
            and (veto or not bundle_ok or blockers or not fair.hard_ok)
        ):
            out = QuickReport(**{**report.__dict__})
            out.word = "WIDERRUF"
            reasons = [f for f in report.flags if f.split(" ")[0] in BLICK_VETO_FLAGS or f in blockers]
            if not fair.hard_ok:
                reasons = list(fair.fails) + reasons
            reasons = reasons or list(report.flags)
            self._emit(state, "WIDERRUF", out, "nach BLICK · " + (", ".join(reasons[:4]) if reasons else "Warnsignal"), now)
        # the same principle after a GO: the call is withdrawn when a fast fairness check newly fails (e.g. the dev
        # sells a part below the 20 % DEV-RAUS threshold); RUG rules stay as they are and may follow
        if (
            "WIDERRUF" in cfg.tiers
            and "GO" in sent
            and "WIDERRUF" not in sent
            and "RUG" not in sent
            and not bad
            and not fair.hard_ok
        ):
            out = QuickReport(**{**report.__dict__})
            out.word = "WIDERRUF"
            self._emit(state, "WIDERRUF", out, "nach GO · " + "; ".join(fair.hard_fails[:3]), now)
        # get-out signals for tokens that got an alert
        mc_drop = (
            "GO" in sent
            and state.go_mc_sol
            and feats.mc_sol is not None
            and feats.mc_sol <= state.go_mc_sol * (1.0 - cfg.go_mc_drop)
        )
        if (bad or mc_drop) and "RUG" in cfg.tiers and ("BLICK" in sent or "GO" in sent) and "RUG" not in sent:
            suffix = "nach GO" if "GO" in sent else "nach BLICK"
            if mc_drop and not bad:
                out = QuickReport(**{**report.__dict__})
                out.word = "RUG"
                drop = 1.0 - feats.mc_sol / state.go_mc_sol
                self._emit(state, "RUG", out, f"{suffix} · MC −{drop * 100:.0f} % seit GO", now)
            else:
                self._emit(state, "RUG", report, suffix, now)
        if bad and (age >= 30 or word == "RUG"):
            state.final, state.final_at = True, now
        elif mc_drop and "RUG" in sent:
            state.final, state.final_at = True, now

    def tick(self, now: float | None = None) -> list[str]:
        """Evaluate due tokens, expire old ones. Returns mints to unsubscribe."""
        now = now if now is not None else time.time()
        expired: list[str] = []
        for mint, state in list(self.tokens.items()):
            age = now - state.created_at
            idle = state.outside_trades() == 0 and age > self.cfg.idle_expire_s and not state.tiers_sent
            keep = False
            if self.keep_alive is not None and age <= self.cfg.max_keep_alive_s and not state.complete:
                try:
                    keep = bool(self.keep_alive(mint, now))
                except Exception:  # noqa: BLE001
                    keep = False
            if not keep and (
                age > self.cfg.track_seconds
                or (state.final and state.final_at is not None and now - state.final_at > self.cfg.final_linger_s)
                or state.complete
                or idle
            ):
                expired.append(mint)
                continue
            if state.complete and not keep:
                expired.append(mint)
                continue
            if state.final:
                continue  # nothing more to say about it; the linger only keeps the subscription a little longer
            due = state.dirty or now - state.last_eval >= max(5.0, self.cfg.eval_interval_s * 5)
            if due and now - state.last_eval >= self.cfg.eval_interval_s and (state.trades or age >= 5):
                try:
                    self.evaluate(state, now)
                except Exception as exc:  # noqa: BLE001 - one token must not stop the loop
                    state.dirty = False
                    state.last_eval = now
                    print(f"[{mint[:8]}] Bewertung fehlgeschlagen: {exc!r}")
        for mint in expired:
            self.tokens.pop(mint, None)
            self.stats["expired"] += 1
        self.stats["tracked"] = len(self.tokens)
        return expired


# --- websocket runner -----------------------------------------------------------------------------


def ws_url_from_rpc(url: str) -> str:
    if url.startswith("https://"):
        return "wss://" + url[len("https://") :]
    if url.startswith("http://"):
        return "ws://" + url[len("http://") :]
    return url


class SolanaLogStream:
    """One websocket connection with a logsSubscribe per tracked mint."""

    def __init__(self, url: str, commitment: str, on_logs: Callable[[str, int, str, Any, list[str]], None]):
        self.url = url
        self.commitment = commitment
        self.on_logs = on_logs
        self.ws = None
        self._id = 0
        self.pending: dict[int, str] = {}  # request id -> mint
        self.subs: dict[int, str] = {}  # subscription id -> mint
        self.mint_sub: dict[str, int] = {}
        self.wanted: set[str] = set()
        self.stats = {"notifications": 0, "reconnects": 0, "bytes": 0}

    async def subscribe(self, mint: str) -> None:
        self.wanted.add(mint)
        if self.ws is None or mint in self.mint_sub or mint in self.pending.values():
            return
        self._id += 1
        self.pending[self._id] = mint
        try:
            await self.ws.send(json.dumps({"jsonrpc": "2.0", "id": self._id, "method": "logsSubscribe", "params": [{"mentions": [mint]}, {"commitment": self.commitment}]}))
        except Exception:  # noqa: BLE001 - the socket is gone; run() reconnects and resubscribes everything in `wanted`
            self.pending.pop(self._id, None)

    async def unsubscribe(self, mint: str) -> None:
        self.wanted.discard(mint)
        sub = self.mint_sub.pop(mint, None)
        if sub is None or self.ws is None:
            return
        self.subs.pop(sub, None)
        self._id += 1
        try:
            await self.ws.send(json.dumps({"jsonrpc": "2.0", "id": self._id, "method": "logsUnsubscribe", "params": [sub]}))
        except Exception:  # noqa: BLE001
            pass

    def handle(self, raw: str) -> None:
        self.stats["bytes"] += len(raw)
        try:
            msg = json.loads(raw)
        except ValueError:
            return
        if not isinstance(msg, dict):
            return
        if msg.get("method") == "logsNotification":
            params = msg.get("params") or {}
            sub = params.get("subscription")
            mint = self.subs.get(sub)
            if mint is None:
                return
            result = params.get("result") or {}
            slot = int((result.get("context") or {}).get("slot") or 0)
            value = result.get("value") or {}
            self.stats["notifications"] += 1
            try:
                self.on_logs(mint, slot, str(value.get("signature") or ""), value.get("err"), list(value.get("logs") or []))
            except Exception as exc:  # noqa: BLE001 - one bad notification must not drop the whole stream
                print(f"[{mint[:8]}] Log-Verarbeitung fehlgeschlagen: {exc!r}")
            return
        rid = msg.get("id")
        if rid in self.pending:
            mint = self.pending.pop(rid)
            if "result" in msg and isinstance(msg["result"], int):
                self.subs[msg["result"]] = mint
                self.mint_sub[mint] = msg["result"]
                if mint not in self.wanted:
                    # unsubscribed while the request was in flight: release it again
                    try:
                        asyncio.get_running_loop().create_task(self.unsubscribe(mint))
                    except RuntimeError:
                        pass
            else:
                print(f"logsSubscribe für {mint[:8]} abgelehnt: {msg.get('error')}")

    async def run(self, stop: asyncio.Event) -> None:
        import websockets

        backoff = 2.0
        while not stop.is_set():
            try:
                async with websockets.connect(self.url, ping_interval=20, max_size=4 * 1024 * 1024) as ws:
                    self.ws = ws
                    self.pending.clear()
                    self.subs.clear()
                    self.mint_sub.clear()
                    for mint in list(self.wanted):
                        await self.subscribe(mint)
                    backoff = 2.0
                    async for raw in ws:
                        self.handle(raw)
                        if stop.is_set():
                            break
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001
                self.ws = None
                self.stats["reconnects"] += 1
                print(f"Log-Stream getrennt ({exc!r}), neuer Versuch in {backoff:.0f} s")
                await asyncio.sleep(backoff)
                backoff = min(60.0, backoff * 2)
        self.ws = None


async def run_live(
    rpc: SolanaRpc,
    config: LiveConfig,
    scoring: ScoringConfig,
    on_alert: Callable[[Alert], None],
    ws_url: str | None = None,
    cache: ProfileCache | None = None,
    status_every_s: float = 60.0,
    paper: Any = None,
) -> None:
    try:
        import websockets
    except ImportError as exc:
        raise SystemExit("Für den Live-Modus fehlt das Paket 'websockets': pip install websockets") from exc

    user_on_alert = on_alert
    if paper is not None:

        def on_alert(alert: Alert) -> None:  # noqa: F811 - the paper trader sees every alert first
            try:
                paper.on_alert(alert)
            except Exception as exc:  # noqa: BLE001
                print(f"Papier-Händler (Alarm) fehlgeschlagen: {exc!r}")
            user_on_alert(alert)

    loop = asyncio.get_running_loop()
    stop = asyncio.Event()
    sems = {"rpc": asyncio.Semaphore(config.max_side_tasks), "http": asyncio.Semaphore(config.max_http_tasks)}
    rpc.stop.clear()

    def run_side_task(name: str, fn: Callable[[], Any], done: Callable[[Any], None], delay: float = 0.0, group: str = "rpc") -> None:
        async def runner() -> None:
            if delay > 0:
                await asyncio.sleep(delay)  # wait outside the semaphore so the slot stays free
            async with sems.get(group, sems["rpc"]):
                try:
                    result = await asyncio.to_thread(fn)
                except RpcError as exc:
                    if "abgebrochen" in str(exc):
                        return
                    result = None
                    print(f"Hintergrundabfrage {name} fehlgeschlagen: {exc}")
                except Exception as exc:  # noqa: BLE001
                    result = None
                    print(f"Hintergrundabfrage {name} fehlgeschlagen: {exc!r}")
                done(result)

        loop.create_task(runner())

    price_state = {"value": None, "at": 0.0}

    def price_hint() -> float | None:
        return price_state["value"]

    engine = LiveEngine(
        rpc,
        config,
        scoring,
        on_alert,
        cache=cache,
        run_side_task=run_side_task,
        price_hint=price_hint,
        on_evaluate=paper.on_evaluate if paper is not None else None,
        keep_alive=paper.keep_alive if paper is not None else None,
    )
    if paper is not None:
        paper.attach(engine)
    stream = SolanaLogStream(ws_url or ws_url_from_rpc(rpc.url), config.commitment, lambda *a: engine.on_logs(*a))

    async def pumpportal() -> None:
        backoff = 5.0
        while not stop.is_set():
            try:
                async with websockets.connect(PUMPPORTAL_WS, ping_interval=20) as ws:
                    await ws.send(json.dumps({"method": "subscribeNewToken"}))
                    await ws.send(json.dumps({"method": "subscribeMigration"}))  # graduations of the whole platform, free (0.3.6)
                    backoff = 5.0
                    engine.on_feed("verbunden")
                    print(f"Live-Modus Stufe {config.stufe}: Launches und Graduierungen von PumpPortal, Trades aus den Logs von {stream.url.split('?')[0]}")
                    async for raw in ws:
                        try:
                            msg = json.loads(raw)
                        except ValueError:
                            continue
                        if not isinstance(msg, dict):
                            continue
                        # dispatch by message type, not by on_launch's return value (None also means duplicate or list full)
                        if msg.get("txType", "create") == "create" and (msg.get("pool") or "pump") == "pump":
                            state = engine.on_launch(msg)
                            if state is not None:
                                await stream.subscribe(state.mint)
                        else:
                            engine.on_migration(msg)
                        if stop.is_set():
                            break
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001
                engine.on_feed("getrennt")
                print(f"PumpPortal getrennt ({exc!r}), neuer Versuch in {backoff:.0f} s")
                await asyncio.sleep(backoff)
                backoff = min(60.0, backoff * 2)

    async def ticker() -> None:
        last_status = time.time()
        while not stop.is_set():
            await asyncio.sleep(config.eval_interval_s)
            now = time.time()
            if paper is not None:
                try:
                    paper.on_tick(now)  # before the engine expires tokens, so closes see the last curve state
                except Exception as exc:  # noqa: BLE001
                    print(f"Papier-Händler (Tick) fehlgeschlagen: {exc!r}")
            for mint in engine.tick(now):
                await stream.unsubscribe(mint)
            missing = engine.take_missing()
            if missing:

                def fetch(sigs=missing):
                    return rpc.get_transactions(sigs)

                def apply(txs, sigs=missing):
                    if txs:
                        engine.apply_fetched_transactions(txs)
                        failed = [s for s in sigs if txs.get(s) is None]
                        if failed:
                            engine.requeue_missing(failed)
                    else:
                        engine.requeue_missing(sigs)

                run_side_task("missing", fetch, apply)
            if now - price_state["at"] > 120:
                price_state["at"] = now

                def load_price():
                    return sol_usd()

                run_side_task("price", load_price, lambda v: price_state.update(value=v) if v else None, 0.0, "http")
            if now - last_status >= status_every_s:
                last_status = now
                s = engine.stats
                print(
                    f"Status: {s['tracked']} Token im Blick, {s['launches']} Launches, {s['trades']} Trades, "
                    f"Alarme BLICK {s['blick']} / GO {s['go']} / WIDERRUF {s.get('widerruf', 0)} / RUG {s['rug']} / GESPERRT {s.get('gesperrt', 0)}, "
                    f"GO wartet auf Historie/Metadaten {s.get('go_wartet', 0)}, GO durch Profil/Halter-Anstieg gesperrt {s.get('go_profil', 0)}, "
                    f"Graduierungen (PumpPortal) {s.get('graduierungen', 0)} (davon mit Alarm {s.get('graduierungen_alarm', 0)}), Hintergrundabfragen {s['side_tasks']} "
                    f"(wegen Budget ausgelassen {s['side_skipped_budget']}), nachgeladen {s['missing']}, "
                    f"Log-Benachrichtigungen {stream.stats['notifications']} ({stream.stats['bytes'] / 1e6:.1f} MB, "
                    f"bei Helius etwa {stream.stats['bytes'] / 1e6 * 20:.0f} Credits), RPC-Einheiten {rpc.stats['requests']}"
                )
                if paper is not None:
                    print(paper.status_line())

    tasks = [loop.create_task(pumpportal()), loop.create_task(stream.run(stop)), loop.create_task(ticker())]
    try:
        await asyncio.gather(*tasks)
    finally:
        stop.set()
        rpc.stop.set()
        for t in tasks:
            t.cancel()


def live(rpc: SolanaRpc, config: LiveConfig, scoring: ScoringConfig, on_alert: Callable[[Alert], None], **kwargs) -> None:
    try:
        asyncio.run(run_live(rpc, config, scoring, on_alert, **kwargs))
    except KeyboardInterrupt:
        pass
    finally:
        rpc.stop.clear()
