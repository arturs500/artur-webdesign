#!/usr/bin/env bash
# Startet den Live-Modus mit Papier-Trading (Mac/Linux). Voraussetzungen: Python 3.10+ und
# SOLANA_RPC_URL, z. B. export SOLANA_RPC_URL="https://mainnet.helius-rpc.com/?api-key=DEIN_KEY"
# Optional: TELEGRAM_BOT_TOKEN und TELEGRAM_CHAT_ID (dann gehen GO und RUG per Telegram), STUFE=1|2|3.
# Weitere Optionen werden durchgereicht, z. B. ./start.sh --paper-telegram GO-3x --narratives trends.txt
set -euo pipefail
cd "$(dirname "$0")"
if [ -z "${SOLANA_RPC_URL:-}" ]; then
  echo "SOLANA_RPC_URL fehlt (z. B. https://mainnet.helius-rpc.com/?api-key=DEIN_KEY)" >&2
  exit 2
fi
if [ ! -d .venv ]; then
  python3 -m venv .venv
fi
# shellcheck disable=SC1091
. .venv/bin/activate
pip -q install -e . websockets
TG=()
if [ -n "${TELEGRAM_BOT_TOKEN:-}" ] && [ -n "${TELEGRAM_CHAT_ID:-}" ]; then
  TG=(--telegram --notify go,rug)
fi
echo "Aufzeichnung: papier.jsonl (Papier-Trades), live.jsonl (Alarme). Auswertung: python -m holder_scorer paper report papier.jsonl"
exec python -m holder_scorer live --stufe "${STUFE:-2}" --paper papier.jsonl --record live.jsonl "${TG[@]}" "$@"
