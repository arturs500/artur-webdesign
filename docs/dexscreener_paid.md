# DexScreener-Bezahlfunktionen („paid DEX"): Mechanik, Preise, Daten, und wo für uns ein Vorteil liegt

Stand: 2026-10-03. Anlass: Nutzerfrage „wie funktioniert dieses paid dex, beschäftige dich damit, damit wir daraus
profitieren können". Regel Edge-First gilt: kein Kauf, keine Boosts, keine Keys. Kennzeichnung wie in
`OPEN_QUESTIONS.md`: **[direkt geprüft]**, **[Snippet]**, **NICHT VERIFIZIERT**. Die offiziellen Seiten
(docs.dexscreener.com, marketplace.dexscreener.com, api.dexscreener.com) waren in der Arbeitsumgebung gesperrt; die
API-Referenz liegt als Spiegel in zwei öffentlichen GitHub-Repos vor und wurde dort direkt gelesen.

---

## 1. Was DexScreener verkauft

| Produkt | Was es tut | Preis | Quelle |
|---|---|---|---|
| **Boosts** (Pakete) | heben für 12–24 h den *Trending Score* eines Tokens; aktive Boost-Zahl steht neben dem Token; ab **500 aktiven Boosts** „Golden Ticker" (goldenes Symbol), solange ≥ 500 aktiv | 10 Boosts/12 h 99 USD · 30/12 h 249 USD · 50/12 h 399 USD · 100/24 h 899 USD · 500/24 h 3 999 USD | Mechanik: docs.dexscreener.com/boosting [Snippet, 2026-10-03]; Preise: dexrockets.com Preistabelle, openliquid.io [Snippet, Drittanbieter] → **NICHT VERIFIZIERT** gegen den Marktplatz |
| **Enhanced Token Info** („Dex paid") | Logo, Beschreibung, Social-Links auf der Token-Seite; Antrag wird geprüft | ab 299 USD (durchgestrichen 499) | marketplace.dexscreener.com/product/token-info [Snippet, 2026-10-03] |
| **Community Takeover** | Takeover-Claim für ein Token mit bestehendem Profil | 199 USD | marketplace.dexscreener.com/product/token-community-takeover [Snippet] |
| **Token Advertising**, **Trending Bar Advertising** | Werbeplätze | Preise unbekannt | Marktplatz-Seiten existieren [Snippet]; Preise NICHT VERIFIZIERT |

Wer zahlt: Boosts kann laut Drittquellen jeder kaufen, auch die „Community", nicht nur das Team [Snippet]. Ob ein
Boost den Token tatsächlich auf die Trending-Seite bringt, ist zwischen Quellen strittig: Die offizielle Boosting-Seite
spricht vom erhöhten Trending Score [Snippet]; ein Drittanbieter schreibt, Boosts seien „reine Sichtbarkeit" und
änderten die Rangfolge nicht [Snippet, pandaboost/blockster]. Beides ungeprüft.

## 2. Was „Dex paid" für den Markt bedeutet

„Dex paid" heißt in der Memecoin-Sprache: Das Team hat Enhanced Token Info gekauft [Snippet, mehrere Quellen]. Es
ist ein **kostenpflichtiges, öffentliches, zeitgestempeltes Signal**: 299 USD Einsatz des Teams, sichtbar für alle,
abrufbar als Auftrag mit `paymentTimestamp`. Darum bauen Sniper-Bots darauf Alarme („DEX PAID"). Kausal ist es ein
Commitment-Signal des Teams und zugleich ein Aufmerksamkeits-Auslöser; beides zieht Käufer an, und genau deshalb
kann es auch die Exit-Liquidität für Insider liefern.

## 3. Die kostenlose API (ohne Schlüssel)

Referenz-Spiegel [direkt geprüft, 2026-10-03]: `raw.githubusercontent.com/openSVM/dexscreener-mcp-server/main/docs/api-reference.md`
und `raw.githubusercontent.com/apeoutmeme/Solana/main/Dexscreener-API.md` (beide geben die offizielle Referenz
docs.dexscreener.com/api/reference wieder; Original gesperrt).

| Endpoint | Limit | Inhalt |
|---|---|---|
| `GET /token-boosts/latest/v1` | 60/min | zuletzt geboostete Token: `url, chainId, tokenAddress, icon?, header?, description?, links?, amount, totalAmount` |
| `GET /token-boosts/top/v1` | 60/min | Token mit den meisten aktiven Boosts, gleiche Felder |
| `GET /token-profiles/latest/v1` | 60/min | zuletzt angelegte Profile (= Enhanced Token Info), Felder ohne `amount` |
| `GET /orders/v1/{chainId}/{tokenAddress}` | 60/min | bezahlte Aufträge eines Tokens: `type` ∈ tokenProfile, communityTakeover, tokenAd, trendingBarAd; `status` ∈ processing, cancelled, on-hold, approved, rejected; `paymentTimestamp` |
| `GET /latest/dex/tokens/{tokenAddresses}` | 300/min | Paare je Token: `priceUsd, priceNative, liquidity{usd}, fdv, marketCap, volume{m5,h1,h24}, txns{m5{buys,sells}}, boosts{active}, pairCreatedAt` |
| `GET /latest/dex/pairs/{chainId}/{pairId}`, `GET /latest/dex/search?q=` | 300/min | Paare, Suche |

Base-URL `https://api.dexscreener.com`; `chainId` für Solana ist `solana`. Höchstzahl Adressen je Tokens-Aufruf
(30) stammt aus der Erinnerung an die Referenz: **NICHT VERIFIZIERT**, der Beobachter bleibt darunter. Nutzungsbedingungen
der API: nicht gelesen (gesperrt) → vor Dauerbetrieb prüfen (OQ-030).

Warnung: In Suchergebnissen tauchen Klon-Domains auf (z. B. „dexsrceener.ink", „dex-srceener.ink"). Nur
`dexscreener.com`, `docs.dexscreener.com`, `marketplace.dexscreener.com`, `api.dexscreener.com` sind echt.

## 4. Was über die Wirkung bekannt ist

- Studie „dethective" (X, Dezember 2024) [Snippet, via theholycoins.com/cryptopanic]: geboostete Token im Mittel
  **−48 %**; Projekte mit mehr als 3 000 Boosts durchgehend im Minus; die „erfolgreichsten" Token hatten 600–1 000
  Boosts. Stichprobe, Zeitraum, Messfenster und Kette sind aus den Snippets nicht erkennbar → **Methodik unbekannt**.
  Lesart: Wer nach dem Boost kauft, verliert im Mittel; Boosts wirken als Exit-Liquidität für die Zahler.
- Boost-Reseller und „Trending-Bots" existieren als Dienstleistung [Snippet: dexrockets, pandaboost, smithii,
  DexTrending-Pressemitteilung] – ein Hinweis, dass Boosts gekauft werden, um Käufer anzuziehen, nicht um Halter zu
  informieren.
- Keine Quelle berichtet eine positive Follower-Rendite nach Boost oder „Dex paid" mit Kontrollgruppe.

## 5. Drei Wege, „davon zu profitieren", nüchtern gerechnet

**(a) Als Creator Boosts kaufen.** Einnahmen eines Creators auf der pump.fun-Kurve sind 0,30 % des Volumens
(`fees.png` [direkt geprüft, 2026-09-29]; bei Holder-Rewards-Coins gehen sie an die Halter). Ein 10er-Boost für
99 USD müsste rund 33 000 USD zusätzliches Kurvenvolumen auslösen, um sich über die Fee zu tragen; ein 500er-Boost
für 3 999 USD rund 1,3 Mio. USD. Ohne Verkauf des eigenen Bestands in die angelockten Käufer rechnet sich das
praktisch nie. *Mit* diesem Verkauf ist es das Pump-and-Dump-Muster, das der Sniper als DEV-DUMP/RUG markiert,
Käufern schadet und rechtlich riskant ist. Dieser Weg wird hier nicht unterstützt (OQ-029).

**(b) Als Follower oder Fader der Signale.** Boosts und „Dex paid" sind öffentliche Ereignisse mit Zeitstempel.
Ob ein Follower daran verdient (kaufen beim Ereignis, verkaufen nach 5/15/60 min) oder im Mittel verliert, ist
messbar, ohne Geld: Modul `dexpaid.py`, Befehle `dex beobachten` und `dex report` (Abschnitt 6). Erwartung aus der
Evidenz: negativ bis null. Ein negatives Ergebnis ist ebenfalls nutzbar, als Warnsignal im Sniper („geboostet =
Finger weg"), aber auch das erst nach Messung (R2). Short-Positionen gegen Memecoins sind auf diesen DEXen nicht
praktikabel, ein „Fade" bleibt deshalb ein Nicht-Kaufen, kein Gewinn.

**(c) Als Dienstleister.** Reseller von Boosts und Trending-Diensten verdienen an Projekten. Das ist ein Geschäft
mit Vorkasse, Zahlungsabwicklung und Reputationsrisiko an der Grenze zur Pump-Förderung; kein Edge-Lab-Thema.

Fazit: Der einzige Weg, der zu Edge-First passt, ist (b) als **Messung**. Der einzige Weg, mit dem Creator
nachweislich Geld verdienen, ist der, den wir ablehnen.

## 6. Werkzeug (0.3.3): `dex beobachten`, `dex report`

```bash
python -m holder_scorer dex beobachten --out dex.jsonl                 # Feeds alle 60 s, Preise bei +0/+5/+15/+60 min
python -m holder_scorer dex report dex.jsonl --records live.jsonl      # Follower-Rendite je Gruppe, eigene Coins
```

Der Beobachter schreibt jeden neuen Boost-Kauf (Mint, Paketgröße, aktive Boosts) und jedes neue Profil als Zeile
und zieht Preis-Schnappschüsse aus dem liquidesten Solana-Paar. Budget: unter 60 Feed- und 300 Preis-Anfragen je
Minute, nach einem 429 eine Minute Pause. Der Report rechnet die Netto-Rendite eines Followers (Gebühr je Seite als
Annahme, Standard 50 bps; PumpSwap verlangt bis zu 125 bps, siehe `fees.png`), Trefferquote mit Wilson, Mittelwert mit
Block-Bootstrap nach Stunde, getrennt nach Boost-Paket und Ereignistyp, und zeigt, welche unserer Alarm-Coins später
ein Bezahlsignal bekamen und wie lange nach dem Launch. Kontrollgruppe (nicht bezahlte Token gleicher Größe) ist
offen (OQ-030); ohne sie ist das Ergebnis eine Beschreibung, kein Edge-Nachweis.

Gegen die echte API lief das Werkzeug in der Arbeitsumgebung nicht (Host gesperrt). Antwortformen folgen dem
Referenz-Spiegel und werden tolerant gelesen; Rohdaten jeder Ereigniszeile bleiben erhalten (`roh`).

## 7. Quellen (Abrufdatum 2026-10-03)

- docs.dexscreener.com/boosting, /trending, /privacy/boosting-terms-and-conditions, /api/reference – nur als
  Suchtreffer [Snippet]; Seiten gesperrt.
- marketplace.dexscreener.com/product/token-info, /product/token-community-takeover, /product/ad,
  /product/trending-bar-ad – [Snippet]; Seiten gesperrt.
- github.com/openSVM/dexscreener-mcp-server (docs/api-reference.md) und github.com/apeoutmeme/Solana
  (Dexscreener-API.md) – API-Spiegel [direkt geprüft].
- dexrockets.com (Preistabelle Boosts), openliquid.io, pandaboost.app, blockster.com, checkmymint.com – Drittanbieter
  [Snippet]; Seiten gesperrt.
- x.com/dethective/status/1867646889254170649 (Studie), theholycoins.com, cryptopanic.com (Berichte) – [Snippet].
- pypi.org/pypi/dexscreener/json – Python-Wrapper 1.3 vom 2025-09-04 [direkt geprüft]; dokumentiert nur Paar-Endpunkte.
