# StatSlap Predictions Log

Public, time-stamped record of every Over/Under forecast published by the StatSlap YouTube channel.

**Channel:** [@StatSlap on YouTube](https://www.youtube.com/channel/UCkK1XF33aD24CcRybTXWQEA)
**Live page:** https://statslap.github.io/predictions/

## Why this exists

Every prediction is logged to this public Git repository **before kickoff**, with a Git commit timestamp that cannot be edited after the fact. Once a match is settled, the result is added to the same record.

If you want to verify that a forecast in a StatSlap video was actually made before the match, browse to `predictions/YYYY-MM-DD.json` and check the `captured_at` timestamp plus the Git commit history.

## Structure

```
predictions/
  YYYY-MM-DD.json    # one file per kickoff date
results/
  YYYY-MM-DD.json    # historical aggregate (pending: same as predictions/)
index.html           # human-readable landing page
```

Each prediction object:

```json
{
  "match_id": 540691,
  "home": "FC Bayern München",
  "away": "1. FC Heidenheim 1846",
  "competition": "Bundesliga",
  "kickoff": "15:30 CEST",
  "prediction": "OVER 2.5",
  "p_model": 0.821,
  "lambda_total": 4.453,
  "final_score": "3-3",
  "final_total": 6,
  "result": "HIT",
  "status": "FINISHED",
  "captured_at": "2026-05-02T08:10:19+00:00"
}
```

## Model

`independent_poisson_v11` — recent-form-blended Poisson with Dixon-Coles correction and per-league λ adjustment.

Inputs are public data (football-data.org, OpenLigaDB, ESPN, Odds API). Filter rules: `p_model ≥ 0.60`, `λ_total ≥ 3.2`, market quote `1.65–2.50`.

## Disclaimer

This is **not betting advice**. The data and model output is published for transparency and entertainment purposes only. No part of this repository constitutes a recommendation to place a wager.
