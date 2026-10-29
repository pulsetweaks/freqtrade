# Paper trading 100 USDT — EmaRsiPaperStrategy

Projet de backtesting et de paper trading (dry-run) construit **au-dessus** de Freqtrade,
sans modifier le moteur. Aucun argent réel n'est engagé.

> ⚠️ Cette stratégie est un point de départ pédagogique. **Aucune rentabilité n'est
> revendiquée.** Seuls des backtests et des dry-runs mesurés peuvent l'évaluer, et des
> résultats passés ne garantissent rien.

## Fichiers

| Fichier | Rôle |
| --- | --- |
| `user_data/strategies/EmaRsiPaperStrategy.py` | Stratégie (spot, long uniquement, sans levier) |
| `user_data/config_paper_100usdt.json` | Config dry-run, portefeuille fictif 100 USDT, Binance spot, sans clés API |
| `tests/user_strategies/test_ema_rsi_paper_strategy.py` | Tests hors-ligne (config, signaux, garde-fous, backtest moteur) |

## Stratégie

- Timeframe par défaut : `1h` (modifiable avec `--timeframe`).
- Indicateurs : EMA 20, EMA 50, RSI 14 (TA-Lib).
- **Entrée** : EMA 20 croise au-dessus de l'EMA 50, RSI < 70, volume > 0.
- **Sortie** : EMA 20 croise sous l'EMA 50, ou RSI > 80.
- Stoploss −5 %, table `minimal_roi` (8 % → 4 % après 12 h → 2 % après 24 h → 0 % après 48 h).
- `startup_candle_count = 200` (préchauffage des EMA).

## Garde-fous de sécurité

- `dry_run: true` et `dry_run_wallet: 100` dans la config.
- `key` / `secret` vides : aucune clé API privée, aucun ordre réel possible.
- `trading_mode: spot`, `can_short = False`, callback `leverage()` qui retourne toujours 1.
- `bot_start()` lève une erreur si le bot est lancé en mode live (`dry_run: false`) ou hors spot.
- Telegram, API REST et `force_entry_enable` désactivés.
- `stake_amount: "unlimited"` + `max_open_trades: 3` ⇒ ≈ 33 USDT par trade
  (au-dessus du minimum Binance d'environ 5 USDT par ordre).

## Commandes (sur votre ordinateur ou serveur)

Pré-requis : Python 3.12+, et une installation Freqtrade de ce dépôt
(voir `docs/installation.md`, ex. `./setup.sh -i`, ou Docker).

```bash
python3 -m venv .venv
```

```bash
source .venv/bin/activate
```

```bash
pip install -r requirements-dev.txt && pip install -e .
```

### 1. Vérifier la configuration et la stratégie

```bash
freqtrade show-config -c user_data/config_paper_100usdt.json
```

```bash
freqtrade list-strategies -c user_data/config_paper_100usdt.json
```

### 2. Lancer les tests

```bash
pytest tests/user_strategies -n 0
```

### 3. Télécharger les données historiques (API publique, sans clé)

Inclut 1h (timeframe principal) et 5m (détail intrabougie pour un backtest plus réaliste) :

```bash
freqtrade download-data -c user_data/config_paper_100usdt.json --timeframes 1h 5m --timerange 20250101-
```

### 4. Backtest avec frais (0,1 % par ordre, appliqué à l'entrée et à la sortie)

```bash
freqtrade backtesting -c user_data/config_paper_100usdt.json --strategy EmaRsiPaperStrategy --timeframe 1h --timeframe-detail 5m --timerange 20250101- --fee 0.001 --export trades
```

Réafficher le dernier résultat :

```bash
freqtrade backtesting-show
```

Contrôles recommandés avant toute conclusion (biais d'anticipation / calcul récursif) :

```bash
freqtrade lookahead-analysis -c user_data/config_paper_100usdt.json --strategy EmaRsiPaperStrategy --timerange 20250101-
```

```bash
freqtrade recursive-analysis -c user_data/config_paper_100usdt.json --strategy EmaRsiPaperStrategy --timerange 20250101-
```

### 5. Dry-run (paper trading en direct, aucun ordre réel)

```bash
freqtrade trade -c user_data/config_paper_100usdt.json --strategy EmaRsiPaperStrategy --db-url sqlite:///user_data/paper_100usdt.dryrun.sqlite
```

Arrêt : `Ctrl+C`. Consulter les trades simulés :

```bash
freqtrade show-trades --db-url sqlite:///user_data/paper_100usdt.dryrun.sqlite --print-json
```

Le dry-run simule les ordres localement (`dry_run_wallet`) à partir des prix publics
du marché : rien n'est envoyé à l'exchange.

## Résultats mesurés

### Backtest hors-ligne (données de test du dépôt)

Exécuté dans l'environnement de développement, sans accès réseau aux exchanges :
moteur `Backtesting` de Freqtrade, exchange simulé, données `tests/testdata/BTC_USDT-5m.feather`
et `XRP_USDT-5m.feather`, timeframe **5m** (et non 1h), frais 0,1 %, portefeuille 100 USDT.

| Métrique | Valeur |
| --- | --- |
| Période | 2025-11-24 16:40 → 2025-12-04 18:45 (≈ 10 jours) |
| Trades | 55 (14 gagnants / 41 perdants, 25,5 %) |
| Solde final | 97,196 USDT |
| Profit total | **−2,804 USDT (−2,80 %)** |
| Variation du marché | +2,39 % |
| Drawdown max | 3,54 % |
| Profit factor | 0,64 |

Interprétation : sur cet échantillon court, la stratégie **perd de l'argent** et fait moins
bien que la simple détention. En 5m, les nombreux croisements d'EMA génèrent des trades
dont les frais absorbent les gains. Ce test valide le fonctionnement technique de la
chaîne (stratégie → moteur → frais → wallet), pas la qualité de la stratégie.
Un backtest sur données réelles 1h et sur plusieurs mois reste à faire (étape 4 ci-dessus).

### Backtest V1 sur données réelles (exécuté par l'utilisateur)

Binance spot, 1h avec détail 5m, du 2025-01-09 au 2026-10-29, frais 0,1 %, 100 USDT.

| Métrique | Valeur |
| --- | --- |
| Trades | 598 (232 gagnants / 366 perdants, 38,8 %) |
| Solde final | 58,249 USDT |
| Profit total | **−41,75 %** |
| Variation du marché | −25,61 % |
| Drawdown max | 44,95 % |
| Profit factor | 0,78 |

Diagnostic : la sortie `ema_cross_down` a clôturé 340 trades, dont 339 en perte (−154 USDT),
car le croisement arrive après la baisse. Environ 29 USDT de frais (29 038 USDT échangés).

## Version 2 — `EmaRsiPaperStrategyV2`

Fichier : `user_data/strategies/EmaRsiPaperStrategyV2.py` (la V1 reste inchangée pour comparer).

Changements (hypothèses à mesurer, pas des améliorations garanties) :

1. Suppression de la sortie `ema_cross_down` : sortie uniquement par ROI, stoploss ou RSI > 80.
2. Filtre de tendance longue : achat seulement si le prix est au-dessus de l'EMA 200,
   pour trader moins souvent et éviter d'acheter en marché baissier.

Pour éviter le sur-ajustement, on mesure sur deux périodes séparées.

Période 1 (2025) :

```bash
freqtrade backtesting -c user_data/config_paper_100usdt.json --strategy-list EmaRsiPaperStrategy EmaRsiPaperStrategyV2 --timeframe 1h --timeframe-detail 5m --timerange 20250101-20260101 --fee 0.001
```

Période 2 (2026, jamais utilisée pour concevoir la V2) :

```bash
freqtrade backtesting -c user_data/config_paper_100usdt.json --strategy-list EmaRsiPaperStrategy EmaRsiPaperStrategyV2 --timeframe 1h --timeframe-detail 5m --timerange 20260101- --fee 0.001
```

Avec Docker, préfixer chaque commande `freqtrade ...` par `docker compose run --rm`.

Contrôle technique hors-ligne (données de test du dépôt, 5m, ≈ 10 jours, non représentatif) :
12 trades, 97,121 USDT final (−2,88 %). Ce chiffre valide seulement que la V2 tourne dans le moteur.

### Résultats V1 / V2 mesurés par l'utilisateur (5 paires, 1h + détail 5m)

| Période | Marché | V1 | V2 |
| --- | --- | --- | --- |
| 2025 | −19,31 % | −37,72 % (323 trades) | −40,48 % (157 trades) |
| 2026 (→ 29/10) | −18,91 % | −9,88 % (266 trades) | +2,05 % (120 trades) |

V2 2025 par raison de sortie : ROI +39,31 USDT, RSI +6,21 USDT, stoploss −85,88 USDT (63 trades).
Conclusion : ni la V1 ni la V2 ne sont rentables.

## Version 3 — `DonchianBreakoutStrategy` (cassure de plus haut)

Fichiers : `user_data/strategies/DonchianBreakoutStrategy.py`, `user_data/config_paper_v3_100usdt.json`
(10 paires, `max_open_trades: 5`, mêmes garde-fous : dry-run, sans clés, spot, sans levier).

Logique (1h, spot, long uniquement) :

- **Entrée** : clôture au-dessus du plus haut des 50 jours précédents, et BTC au-dessus de sa SMA 100 jours.
- **Sortie** : clôture sous le plus bas des 5 jours précédents, ou stoploss −12 %. Pas de take-profit.

### Méthode de recherche

Backtests hors-ligne avec le moteur Freqtrade (exchange simulé), données Binance 1h uploadées par
l'utilisateur, 10 paires (BTC, ETH, SOL, BNB, XRP, ADA, DOGE, AVAX, LINK, LTC), frais 0,1 %, 100 USDT.
Le harness reproduit les résultats V1/V2 de l'utilisateur (V1 2025 : 323 trades, −37,80 % contre −37,72 %).

1. Trois familles testées sur 2022–2025, année par année : tendance lente (36 variantes),
   cassure Donchian (54 + 200 + 9 variantes), achat de creux RSI (108 variantes).
2. Donchian retenu : toutes ses variantes sont positives sur 2022–2025 cumulé, avec une zone stable
   (entrée 40–60 jours, sortie 3–7 jours). Réglage choisi au centre de cette zone.
3. 2026 gardé de côté et testé **une seule fois** à la fin.
4. `freqtrade lookahead-analysis` : aucun biais (0 signal biaisé sur 20).

### Résultats V3 (10 paires, 1h, frais 0,1 %, 100 USDT)

| Période | Trades | V3 | Marché | Drawdown max |
| --- | --- | --- | --- | --- |
| 2022 (dès avril, préchauffage) | 6 | −5,58 % | −62,76 % | 6,15 % |
| 2023 | 49 | +65,28 % | +189,10 % | 16,52 % |
| 2024 | 41 | +105,90 % | +99,75 % | 13,52 % |
| 2025 | 33 | −3,77 % | −30,03 % | 10,12 % |
| **2026 (jamais vu, → 29/10)** | 27 | **−2,12 %** | −23,04 % | 9,96 % |
| Continu 2022 → 2026 | 156 | +189,92 % | −8,67 % | 19,08 % |

Lecture honnête :

- La V3 gagne dans les marchés haussiers et perd peu dans les marchés baissiers.
- Elle **n'est pas rentable chaque année** : 2022, 2025 et 2026 sont légèrement négatifs.
- Le +189,92 % continu porte surtout sur des années ayant servi aux réglages : c'est un chiffre optimiste.
  Le seul test indépendant (2026) donne −2,12 % dans un marché à −23 %.
- Le backtest suppose des exécutions au prix d'ouverture de la bougie suivante, sans glissement.
  Le dry-run est l'étape suivante pour mesurer l'écart avec la réalité.

### Commandes V3

```bash
freqtrade download-data -c user_data/config_paper_v3_100usdt.json --timeframes 1h --timerange 20220101-
```

```bash
freqtrade backtesting -c user_data/config_paper_v3_100usdt.json --strategy DonchianBreakoutStrategy --timeframe 1h --timerange 20220101- --fee 0.001
```

```bash
freqtrade trade -c user_data/config_paper_v3_100usdt.json --strategy DonchianBreakoutStrategy --db-url sqlite:///user_data/paper_v3.dryrun.sqlite
```
