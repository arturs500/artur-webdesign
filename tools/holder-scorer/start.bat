@echo off
rem Startet den Live-Modus mit Papier-Trading (Windows). Voraussetzungen: Python 3.10+ und
rem SOLANA_RPC_URL, z. B.  set SOLANA_RPC_URL=https://mainnet.helius-rpc.com/?api-key=DEIN_KEY
rem Optional: TELEGRAM_BOT_TOKEN und TELEGRAM_CHAT_ID (dann gehen GO und RUG per Telegram), STUFE=1|2|3.
cd /d "%~dp0"
if "%SOLANA_RPC_URL%"=="" (
  echo SOLANA_RPC_URL fehlt ^(z. B. https://mainnet.helius-rpc.com/?api-key=DEIN_KEY^)
  exit /b 2
)
if not exist .venv (
  python -m venv .venv
)
call .venv\Scripts\activate.bat
pip -q install -e . websockets
set TG=
if not "%TELEGRAM_BOT_TOKEN%"=="" if not "%TELEGRAM_CHAT_ID%"=="" set TG=--telegram --notify go,rug
if "%STUFE%"=="" set STUFE=2
echo Aufzeichnung: papier.jsonl (Papier-Trades), live.jsonl (Alarme). Auswertung: python -m holder_scorer paper report papier.jsonl
python -m holder_scorer live --stufe %STUFE% --paper papier.jsonl --record live.jsonl %TG% %*
