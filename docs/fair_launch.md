# Fairer eigener Launch: Anleitung mit Zahlen (OQ-029)

Stand: 2026-10-04. Anlass: Nutzerfrage, wie ein eigener Coin „durchkommt", Aufmerksamkeit bekommt, ein kleiner Teil
verkauft werden kann und die neuen Halter trotzdem gute Chancen behalten. Dieses Dokument ist Wissen, keine
Empfehlung zu kaufen. Ob Kapital fließt, bleibt Entscheidung des Nutzers (Eskalationspunkte Geld, Live-Kapital,
Recht in `docs/experte.md`). Kennzeichnung: **[direkt geprüft]**, **[Snippet]**, **NICHT VERIFIZIERT**,
**Erfahrungswissen** (verbreitete Praxis ohne eigene Messung).

---

## 1. Was „durchkommen" bedeutet

Ein pump.fun-Coin graduiert, wenn die reale Token-Reserve der Kurve auf 0 fällt. Mit den offiziellen Startparametern
[direkt geprüft, pump-public-docs, 2026-09-29] ist das Produkt der virtuellen Reserven unveränderlich; die Kurve
endet immer bei 115 SOL virtueller SOL-Reserve, also nach **rund 85 SOL Netto-Zufluss**, bei einer MC von rund
411 SOL. Ein Dev-Kauf ersetzt davon nur den eigenen Betrag und hebt zugleich den Einstiegspreis aller anderen. Nur
etwa jeder hundertste Launch kommt dort an (0,2–2,7 % laut Snippets, OQ-019). Alles Weitere gilt unter der Bedingung
„der Coin kommt durch".

## 2. Zahlen aus dem Launch-Rechner

`python -m holder_scorer launch rechner` rechnet Szenarien aus der geprüften Kurvenmathematik (Gebühr 1,25 %,
Verkauf auf der Kurve kurz vor der Vollendung als Näherung; der PumpSwap-Pool danach ist anders tief). Auszug:

| Dev-Kauf | Anteil Supply | MC nach Dev-Kauf | Fremdzufluss bis Graduation | Dev-Position bei Graduation | Verkauf 25 % netto | Kursimpact | Creator-Fee bis Graduation* |
|---|---|---|---|---|---|---|---|
| 0,5 SOL | 1,7 % | 28,9 SOL | 84,5 SOL | 7,1 SOL | 1,74 SOL | 3,0 % | 0,51 SOL |
| 1 SOL | 3,4 % | 29,8 SOL | 84,0 SOL | 14,1 SOL | 3,37 SOL | 5,8 % | 0,51 SOL |
| 2 SOL | 6,6 % | 31,8 SOL | 83,0 SOL | 27,2 SOL | 6,35 SOL | 10,9 % | 0,51 SOL |
| 5 SOL | 15,2 % | 37,9 SOL | 80,1 SOL | 62,3 SOL | 13,55 SOL | 22,4 % | 0,51 SOL |

*Annahme Kurvenvolumen = 2 × Zufluss; 0,30 % davon an den Creator [direkt geprüft, fees.png]; bei Holder-Rewards-Coins
0 (die Fee geht an die Halter). Ab 10 % Supply löst der Dev-Anteil die Sniper-Warnung DEV-GROSS aus; bei 5 SOL
Dev-Kauf ist das der Fall, bei 2 SOL noch nicht.

Lesart: Mit 1 SOL Einsatz hält der Dev rund 3,4 % der Supply. Kommt der Coin durch, ist das rund 14 SOL wert. Der
Verkauf eines Viertels bringt rund 3,4 SOL netto, drückt den Kurs um knapp 6 % und lässt rund 10 SOL im Bestand. Das
ist der „kleine Teil", der die Halter nicht in den Abgrund verkauft. Wer die Hälfte oder mehr verkauft, wirkt wie
DEV-RAUS, auch wenn er es vorher angekündigt hat.

## 3. Fairness-Regeln, die Halter schützen und zugleich die Bot-Filter passieren

Die Türsteher des Marktes sind Bots mit Regeln wie unserem Sniper. Was sie markieren, ist zugleich das, was Halter
schädigt. Ein fairer Launch vermeidet jede dieser Warnungen von selbst:

| Sniper-Warnung | Was sie misst | Faire Regel für den Dev |
|---|---|---|
| BUNDLE | fremde Käufe im Create-Block | keine eigenen Zweit-Wallets, kein „Sniper-Schutz" durch Vorkauf |
| DEV-GROSS | Dev hält ≥ 10 % der Supply | Dev-Kauf ≤ 1 SOL (≈ 3 %), öffentlich genannt |
| DEV-RAUS, DEV-DUMP | Dev verkauft früh oder viel | Verkaufsplan vorab veröffentlichen: ≤ 25 % der Dev-Token, erst nach Graduation, in angekündigten Tranchen, nie in eine Pump-Kerze |
| FRISCH, SERIE | frisches Dev-Wallet, Serie toter Launches | eine Dev-Wallet mit Historie, die auch nach einem Flop weiterbenutzt wird; keine Wegwerf-Wallets |
| BOTS, Wash | Umsatz aus denselben Wallets | keine Volume-Bots, keine Bump-Bots, kein Wash-Trading |
| UNSICHTBAR | Float, den kein Trade erklärt | nichts außerhalb der Kurve verteilen |
| keine Socials, kein Bild | Metadaten | Bild, Beschreibung, X, Telegram, Website beim Create vollständig |

Dazu, was kein Bot prüft, aber jeder Halter spürt: Sag, wer du bist (ein Pseudonym ist in Ordnung, aber konsistent
und mit Historie), was der Coin ist (ein Meme, kein Produktversprechen), was du tust und wann du verkaufst. Jeder
Verkauf wird vorher im Telegram angekündigt und danach mit Transaktion belegt. Keine Aussagen zu Kurszielen oder
Renditen, keine erfundenen Partnerschaften, keine bezahlten Shill-Gruppen, keine Boosts, um in den Abverkauf zu
locken (`docs/dexscreener_paid.md`). Holder-Rewards sind das stärkste Fairness-Signal, das die Plattform bietet,
weil der Dev dabei auf die Creator-Fee verzichtet; der Rechner zeigt mit `--holder-rewards`, was das kostet.

## 4. Aufmerksamkeit ehrlich bekommen (Erfahrungswissen, nicht gemessen)

- **Narrativ zuerst.** Der erste Launch auf einer frischen Welle schlägt die zehnte Kopie. Das Themen-Register des
  Sniper (`Them`-Zeile, OQ-028) zeigt live, welche Begriffe gerade eine Welle bilden und welche gesättigt sind.
  Ein eigenes, visuell klares Meme mit kurzem, eindeutigem Ticker schlägt ein generisches.
- **Community vor dem Launch.** Telegram-Gruppe und X-Konto mit echten Menschen, bevor der Create gesendet wird;
  Mint-Adresse nur dort und erst zum Launch nennen, sonst launchen Kopierer vorher.
- **Dev-Präsenz danach.** Fragen beantworten, Wallet-Adresse offenlegen, Verkäufe ankündigen. Was Halter hält, ist
  ein Dev, der da ist.
- **Enhanced Token Info** (299 USD, „Dex paid") erwarten viele Trader. Es ist Werbung und Pflege, kein Kurstreiber
  (`docs/dexscreener_paid.md`). Kauf = Eskalationspunkt Geld.
- **Nicht:** Boost-Reseller, Trending-Bots, Volume-Bots, Fake-Airdrops, „Partnerschafts"-Angebote per DM. Devs sind
  das Hauptziel dieser Angebote.

## 5. Recht und Steuern (NICHT VERIFIZIERT, nur mit Berater)

Krypto-Emissionen in der EU unterliegen MiCA (Whitepaper-Pflichten mit Ausnahmen für kleine Angebote); Gewinne aus
privaten Veräußerungen sind in Deutschland steuerlich relevant; falsche Angaben zu Projekt, Team oder Verkäufen
können Betrug oder Marktmanipulation sein. Keine dieser Aussagen konnte hier geprüft werden (Hosts gesperrt). Vor
einem Launch: Steuerberater und Anwalt, einmal.

## 6. Realistische Erwartung

Aufwand hoch, Erfolgswahrscheinlichkeit klein. Ein fairer Launch tauscht die Dump-Rendite gegen Reputation: Der
zweite und dritte Launch eines Devs mit sauberer Historie hat bessere Chancen als der erste, weil genau diese
Historie das ist, was Sniper prüfen. Vorab festlegen: Budget-Obergrenze (was verloren sein darf), Erfolgskriterium
(Graduation ja oder nein; Creator-Fee mindestens Kosten), kein Nachlegen bei Misserfolg. Erst dann entscheiden.

## 7. Was Edge Lab dafür bereitstellt

Seit Sniper 0.3.4 setzt der Sniper die Regeln aus Abschnitt 3 selbst durch (Fairness-Gate, OQ-031): Ein Coin, der sie
verletzt, bekommt kein GO, sondern ⛔ GESPERRT in die Aufzeichnung. Dein eigener Launch würde also genau an diesen
Punkten gemessen.

`launch rechner` (Szenarien), Themen-Register und `--beobachte` (Wellen und Begriffe live), `tape report`
(Creator-Fee je beobachtetem Coin als Untergrenze, OQ-029), `dex report` (was Bezahlsignale bringen, OQ-030), und
der Sniper selbst, mit dem du deinen eigenen Launch beobachten kannst: Du siehst dann, was die Bots sehen.
