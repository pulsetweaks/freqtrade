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
