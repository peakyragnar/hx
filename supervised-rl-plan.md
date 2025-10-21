Great—let’s slow down and make this crystal clear, in plain language, for your local, SQLite‑first setup.

⸻

What you’re building conceptually (why it’s RL/ML‑ready)

Think of each forecast you run as one data point in a learning loop:
	1.	State (what you knew before deciding):
	•	Model‑only prior (RPL) probability and CI.
	•	Web estimate (WEL) probability and CI, plus evidence stats (docs, domains, agreement, freshness).
	•	Any claim features (e.g., “has date?”, “sports?”, “company?”).
	2.	Action (what you controlled):
	•	How you fused prior+web (the weight w_{\text{web}}).
	•	Optional knobs (K, R, how many docs, which provider, etc.).
	3.	Outcome / Reward (how good the forecast was after the market resolves):
	•	Scoring rule (e.g., Brier score) or profit vs. Kalshi/Polymarket prices.

If you log “state + action + outcome” for every forecast, you can later:
	•	Supervised learn: a small model that maps state → best probability (minimize Brier).
	•	Policy learn (RL): a policy that chooses actions (e.g., w_{\text{web}}, sampling budget, which sources to query) to maximize expected reward under cost/time constraints.

You don’t have to run RL today. You just need to record the right fields so future learning is possible.

⸻

Why supervised first, RL later
	•	Supervised calibration (regression to minimize Brier/log‑loss) is the fastest way to improve accuracy. It learns how to combine RPL+WEL features into a calibrated probability.
	•	RL becomes useful when actions change your information/cost trade‑off (e.g., “fetch more docs or stop?”, “call second provider or not?”, “how to size a bet?”). You’ll be ready because you’ll log state/action/reward.

Start simple:
	•	Predict probability well (supervised).
	•	Later optimize decisions (RL), once you see patterns.

⸻

How Kalshi/Polymarket fit (for accuracy and, later, edge)

You need two things from markets:
	1.	Price now (to compare your p to market’s p and estimate edge).
	2.	Resolution later (0/1) to compute accuracy (Brier) and hypothetical PnL.

With those, each run becomes a labeled training example:
	•	Input (state features) → Your probability → Compare to market price now → When resolved, compute reward (accuracy and/or profit).

⸻

Minimal local data design (SQLite + Parquet)

You can keep SQLite for the product logs and also write a Parquet file for analysis. This keeps your local workflow fast and simple.

1) Forecast runs (the “fat row”—one row per claim run)

Table: forecast_runs
	•	id (uuid/text), created_at (timestamp)
	•	claim_text (text), mode (baseline|web_informed)
	•	RPL: prior_p, prior_ci_lo, prior_ci_hi, prior_stability
	•	WEL: web_p, web_ci_lo, web_ci_hi, docs_count, domains_count, agreement, recency_days
	•	Fusion: combined_p, combined_ci_lo, combined_ci_hi, w_web, recency_score, strength_score
	•	Knobs: k, r, wel_reps, wel_max_docs, prompt_version
	•	Costs: tokens_in, tokens_out, cost_usd
	•	Seeds: seed_bigint
	•	provider_set: "openai:gpt-5" (for now)
	•	Optional: resolved_flag, resolved_truth (filled by the resolver or after market resolution)
	•	Analytics copy: also append each row to runs/forecast_runs.parquet

This is your future training dataset: all features you need to learn from later live here.

2) Markets (for linking and outcomes)
	•	markets (market_id, venue, question, type, settlement_rules, status)
	•	market_quotes (market_id, ts, bid, ask, mid)
	•	market_resolutions (market_id, resolved_at, outcome_bool)
	•	claim_market_link (forecast_run_id ↔ market_id, mapping_notes)

When you run a forecast for a market, store the current mid price and link the run to that market. When the market resolves, write the outcome.

⸻

The simple pipeline you will run locally

A. When you type a claim:
	1.	RPL (Model‑only) → prior probability + CI + stability.
	2.	WEL (Web) → web probability + CI + evidence stats.
	3.	Fuse in log‑odds using one scalar w_{\text{web}} from recency/strength scores.
	4.	Write one fat row to SQLite and append it to Parquet.
	5.	(Optional) If the claim maps to a Kalshi market, store the current market mid price in market_quotes and link with claim_market_link.

B. Later (daily cron or manual):
	1.	Pull market resolutions.
	2.	Join to your past runs via claim_market_link.
	3.	Compute Brier (and optional PnL) and store in a results table or add to forecast_runs as new columns (brier, hypothetical_pnl).

This gives you a growing labeled dataset: (features → your p → market p → resolution → reward).

⸻

What goes into features (state)

From each run, you already have great candidate features:
	•	From RPL: prior_p, prior_ci_width, prior_stability
	•	From WEL: web_p, web_ci_width, docs_count, domains_count, agreement, recency_days
	•	From Fusion (as inputs for learning a better fusion later): current w_web, recency_score, strength_score
	•	From market (when linked): contemporaneous market_mid (not the label—just a comparison point; the label is the final outcome)

With ~200–1000 labeled cases, a small logistic regression or gradient boosted trees can already beat a fixed w_{\text{web}}.

⸻

What “RL‑possible” really means here

Because you will log:
	•	State (all features above),
	•	Action (what w_{\text{web}} you used; what budgets you chose; whether you fetched 20 docs or 10),
	•	Reward (Brier or PnL after resolution),

…you can later train a policy that picks actions to maximize reward under constraints (latency/cost). Examples:
	•	Action = choose w_{\text{web}} adaptively from features (not just a formula).
	•	Action = decide “stop early” vs “fetch more docs” when evidence looks weak.
	•	Action = choose provider mix (once you add more models).

Today you’ll keep a static policy (your current heuristics). Learning comes later from the same logs.

⸻

How to keep it dead simple (SQLite‑only start)
	1.	Keep using SQLite for forecast_runs and the market tables above.
	2.	Also append each run to a local Parquet file for fast analytics (DuckDB/Pandas).
	3.	Add one mapping table from your claim to a market, so you can evaluate accuracy later.
	4.	Write a tiny eval script that reads forecast_runs.parquet, left‑joins resolved outcomes, and prints:
	•	Brier by month and by mode (Baseline vs Web‑Informed)
	•	Reliability plot (bin predictions and show true frequency)
	•	Edge vs market (our p − market mid)

This is enough to start learning what works.

⸻

Your immediate to‑do (in order)
	1.	Add the fat‑row write (one row per run) to SQLite and Parquet (fields listed above).
	2.	Add market tables and a tiny CLI:
	•	markets add <market_id> <venue> <question>
	•	markets quote <market_id> (store mid; or just paste it for now)
	•	runs link <run_id> <market_id>
	•	markets resolve <market_id> <0|1>
	3.	Add an eval.py:
	•	Join runs ↔ market outcomes.
	•	Compute Brier by mode and a global reliability chart.
	4.	Keep your fusion exactly as is (log‑odds, weight from recency/strength), but log your weight as the action. That’s your policy today.

When you accumulate some resolved cases, you can try:
	•	A simple supervised model that predicts the combined probability from all features.
	•	Or a model that predicts the optimal w_{\text{web}} given the features (and then you fuse with that learned weight).

Both are easy to do in a notebook with scikit‑learn.

⸻

Quick answers to your two implicit questions
	•	“Do I need both RPL and WEL for markets?”
Yes. RPL gives you the model’s bias/baseline; WEL gives you the current evidence. Markets are about now—WEL matters a lot—but logging RPL lets you see and learn how much the web should move the prior.
	•	“Why log to Parquet if I have SQLite?”
SQLite is great for product logic. Parquet makes analytics (joins, ML, plotting) fast and tool‑friendly. Do both; it’s just a few lines.

⸻

If you’d like, I can draft the exact SQLite CREATE TABLE statements and a tiny eval.py skeleton to compute Brier scores from your local files.

Great question. Kalshi markets trade continuously, so you want a sampling plan that (a) captures the signal you’ll learn from, (b) doesn’t explode storage/cost, and (c) lines up with the resolution time of each market.

Below is a practical, simple + learnable design you can implement now and scale later.

⸻

1) What to store (per snapshot)

At each snapshot, persist top‑of‑book + a few derived fields:
	•	market_id, ts_utc
	•	best_bid_yes, best_ask_yes (in dollars or cents)
	•	mid_yes = (bid+ask)/2
	•	spread = ask - bid
	•	bid_size_top, ask_size_top (if available)
	•	last_trade_price, last_trade_size (if available)
	•	day_volume (if available)
	•	derived: time_to_event_sec (event start/end or settle time – use the relevant one), is_halted (if available)

That’s enough to compute probability (mid), liquidity (spread, size), and simple risk/volatility features later.
If you need depth later, add a separate table for top‑5 levels, sampled much less frequently (e.g., every 5–15 min), to keep size modest.

⸻

2) How often to store (policy you can explain)

Use a heartbeat + change trigger policy:

A) Heartbeat (time‑to‑event aware)

Let TTE = time_to_event_sec.
	•	TTE > 7 days → every 15 min
	•	2–7 days → every 5 min
	•	12–48 hours → every 2 min
	•	1–12 hours → every 1 min
	•	0–60 min → every 10 sec
	•	0–5 min → every 2 sec (if rate limits allow; else 5–10 sec)

This concentrates samples where information flow is fastest (close to resolution) and saves space when far away.

B) Change trigger (event‑driven inserts between heartbeats)

Whenever a poll detects meaningful movement, insert an extra snapshot immediately:
	•	|mid_yes - last_mid| ≥ 0.005 (≥ 0.5 percentage points)
	•	OR spread crosses a threshold (e.g., from > 2c to ≤ 2c)
	•	OR a new high/low for the day

This gives you good coverage of jumps without hammering the API.

If the API supports websockets/streaming updates, consume those and still bucket to these intervals on write (or store raw ticks in a separate “ticks” table and roll up to bars offline).

⸻

3) Storage sizing (why this won’t explode)

Rough back‑of‑envelope per market:
	•	Far from event: 15‑min snaps → ~96/day
	•	Near event (last hour): 10‑sec snaps → 360/hour
	•	Most days won’t be “last hour”; across many markets, the load is manageable.

A single row with 10–15 numeric fields is tiny (~100–200 bytes uncompressed in Postgres; even less in Parquet). This policy is safe for tens to hundreds of markets.

⸻

4) Schema (minimal + extendable)

market_quotes (uniform snapshots & change‑triggered)
	•	id (uuid), market_id (text), ts_utc (timestamptz, indexed)
	•	best_bid_yes numeric, best_ask_yes numeric, mid_yes numeric
	•	spread numeric, bid_size_top int, ask_size_top int
	•	last_trade_price numeric, last_trade_size int, day_volume int
	•	time_to_event_sec int, is_halted bool default false
	•	ingest_source text (which adapter)
	•	Unique index suggestion if you stick to a strict heartbeat grid: (market_id, ts_utc);
if you also insert change‑trigger updates, skip the unique and dedupe in analytics.

Optional: market_ticks (raw prints/depth…) only if you later need tick models.

⸻

5) Resampling for learning (consistent features)

Most ML/RL pipelines prefer regular time steps. Keep snapshots raw, then nightly (or on demand) build bars:
	•	bars_1m, bars_5m, bars_15m with:
	•	open, high, low, close (use mid_yes)
	•	spread_mean, spread_min, spread_max
	•	vol_est (e.g., EWMA of returns), momentum (e.g., 5m/30m)
	•	liquidity features (avg spread, avg size, % time spread ≤ 2c)
	•	age_to_event (bucketed)

These bars are the inputs you’ll train on. Keep the raw table to rebuild features later.

⸻

6) Labels for learning (ground truth)

You’ll supervise on final settlement (YES=1, NO=0). For each bar/snapshot row:
	•	attach y_final once the market resolves
	•	store resolved_at to compute “distance to label” if you do horizon‑specific models

This lets you train models “X hours before resolution” and understand calibration across horizons.

⸻

7) Update cadence (ingest loop)
	•	Poll frequency = the heartbeat above (per market, based on TTE)
	•	On each poll:
	1.	Fetch top‑of‑book (and last trade/volume if available).
	2.	Compute mid_yes, spread, time_to_event_sec.
	3.	If ts_utc is at your heartbeat boundary or change‑trigger fired → insert.
	4.	Otherwise skip (no‑op).
	•	Backfill once when you onboard a market (call the API’s historical endpoint if available) or start fresh the day you begin.

⸻

8) Practical defaults (if you want it even simpler)

If you want one knob now:
	•	Every market every 60 seconds (1‑minute cadence)
	•	And every 10 seconds in the final hour
	•	Change‑trigger: extra snapshot when |Δmid| ≥ 0.5pp

You’ll still get enough data to learn good features (momentum, liquidity, regime shifts) without overcomplicating ingestion.

⸻

9) Why this works for learning
	•	Signal density where it matters (near resolution).
	•	Regular bars later for clean model inputs.
	•	Sufficient granularity to capture jumps without overwhelming storage.
	•	Time‑to‑event stored with every row → you can condition models by horizon, which is critical for calibration.

⸻

10) Nice‑to‑have later
	•	Depth snapshots (top‑5) every 5–15 min for liquidity features.
	•	Trades table for true realized volatility.
	•	Venue health metrics (API latency/failures) to mark data gaps.
	•	ETags/If‑Modified‑Since or websocket to reduce redundant pulls if supported.

⸻

TL;DR

Start with 1‑minute snapshots per market, escalate to 10 seconds in the last hour, and insert extra snapshots on ≥0.5pp moves. Store bid/ask/mid/spread/top sizes + time_to_event. Resample to 1‑/5‑/15‑minute bars for ML. Label rows after settlement. This is easy to build, cheap to run, and gives you exactly the structure you need for training and evaluation.

Absolutely—here are ready‑to‑paste SQLite DDLs plus a tiny eval.py you can run locally to compute Brier scores (and a few helpful summaries). I’ve kept types and constraints SQLite‑friendly and added indexes so queries stay snappy as you scale.

⸻

1) SQLite tables (DDL)

Save each block as its own migration SQL file (e.g., db/migrations/001_create_forecast_runs.sql, …) and apply with your usual migration tool or sqlite3 CLI.

001 — forecast_runs (one “fat row” per forecast)

-- db/migrations/001_create_forecast_runs.sql
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS forecast_runs (
  id                TEXT PRIMARY KEY,      -- uuid string you generate
  created_at        TEXT NOT NULL,         -- ISO8601 UTC "YYYY-MM-DDTHH:MM:SSZ"

  -- input
  claim_text        TEXT NOT NULL,
  mode              TEXT NOT NULL CHECK (mode IN ('baseline','web_informed')),

  -- RPL (prior)
  prior_p           REAL CHECK (prior_p >= 0.0 AND prior_p <= 1.0),
  prior_ci_lo       REAL,
  prior_ci_hi       REAL,
  prior_stability   REAL,

  -- WEL (web)
  web_p             REAL CHECK (web_p >= 0.0 AND web_p <= 1.0),
  web_ci_lo         REAL,
  web_ci_hi         REAL,
  docs_count        INTEGER,
  domains_count     INTEGER,
  agreement         REAL,       -- e.g., 0..1 agreement/dispersion metric
  recency_days      REAL,       -- median age of docs in days (if known)

  -- fusion
  combined_p        REAL CHECK (combined_p >= 0.0 AND combined_p <= 1.0),
  combined_ci_lo    REAL,
  combined_ci_hi    REAL,
  w_web             REAL,       -- weight placed on web in log-odds fusion 0..1
  recency_score     REAL,       -- 0..1 (your scoring function)
  strength_score    REAL,       -- 0..1 (your scoring function)

  -- knobs / provenance / cost
  k                 INTEGER,
  r                 INTEGER,
  wel_reps          INTEGER,
  wel_max_docs      INTEGER,
  prompt_version    TEXT,
  provider_set      TEXT,       -- e.g. "openai:gpt-5"
  seed_bigint       INTEGER,    -- bootstrap seed for determinism
  tokens_in         INTEGER,
  tokens_out        INTEGER,
  cost_usd          REAL,

  -- optional: if your resolver determined a final truth now
  resolved_flag     INTEGER DEFAULT 0 CHECK (resolved_flag IN (0,1)),
  resolved_truth    INTEGER CHECK (resolved_truth IN (0,1)),

  -- optional: market snapshot at run time (if linked)
  market_mid_at_run REAL,

  -- soft JSON field (optional) for extra diagnostics; store as text
  extra_json        TEXT
);

CREATE INDEX IF NOT EXISTS idx_forecast_runs_created_at ON forecast_runs(created_at);
CREATE INDEX IF NOT EXISTS idx_forecast_runs_mode ON forecast_runs(mode);
CREATE INDEX IF NOT EXISTS idx_forecast_runs_resolved ON forecast_runs(resolved_flag);

002 — markets

-- db/migrations/002_create_markets.sql
CREATE TABLE IF NOT EXISTS markets (
  market_id        TEXT PRIMARY KEY,          -- venue's id or your own
  venue            TEXT NOT NULL,             -- 'kalshi' | 'polymarket' | ...
  question         TEXT NOT NULL,
  market_type      TEXT,                      -- 'binary' | 'scalar' (for later)
  settlement_rules TEXT,
  status           TEXT,                      -- 'open'|'closed'|'settled'
  event_time       TEXT                       -- ISO8601 (if applicable)
);

003 — market_quotes (snapshots of top‑of‑book)

-- db/migrations/003_create_market_quotes.sql
CREATE TABLE IF NOT EXISTS market_quotes (
  id                INTEGER PRIMARY KEY AUTOINCREMENT,
  market_id         TEXT NOT NULL,
  ts_utc            TEXT NOT NULL,             -- ISO8601 UTC
  best_bid_yes      REAL,
  best_ask_yes      REAL,
  mid_yes           REAL,
  spread            REAL,
  bid_size_top      INTEGER,
  ask_size_top      INTEGER,
  last_trade_price  REAL,
  last_trade_size   INTEGER,
  day_volume        INTEGER,
  time_to_event_sec INTEGER,
  is_halted         INTEGER DEFAULT 0 CHECK (is_halted IN (0,1)),
  ingest_source     TEXT,                       -- adapter name

  FOREIGN KEY (market_id) REFERENCES markets(market_id)
);

CREATE INDEX IF NOT EXISTS idx_quotes_market_ts ON market_quotes(market_id, ts_utc);

004 — market_resolutions

-- db/migrations/004_create_market_resolutions.sql
CREATE TABLE IF NOT EXISTS market_resolutions (
  market_id    TEXT PRIMARY KEY,
  resolved_at  TEXT NOT NULL,                 -- ISO8601 UTC
  outcome_bool INTEGER NOT NULL CHECK (outcome_bool IN (0,1)),
  notes        TEXT,
  FOREIGN KEY (market_id) REFERENCES markets(market_id)
);

005 — claim_market_link (link a forecast run to a market)

-- db/migrations/005_create_claim_market_link.sql
CREATE TABLE IF NOT EXISTS claim_market_link (
  run_id     TEXT NOT NULL,
  market_id  TEXT NOT NULL,
  mapping_notes TEXT,
  PRIMARY KEY (run_id, market_id),
  FOREIGN KEY (run_id) REFERENCES forecast_runs(id) ON DELETE CASCADE,
  FOREIGN KEY (market_id) REFERENCES markets(market_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_link_market ON claim_market_link(market_id);


⸻

2) Tiny evaluator (eval.py) — Brier, calibration bins, market edge

Drop this file anywhere (e.g., tools/eval.py). It joins your runs to outcomes (from market_resolutions or forecast_runs.resolved_truth) and prints a compact report.
Requires pandas (pip install pandas).

# tools/eval.py
import argparse
import sqlite3
from typing import Optional
import pandas as pd
import math

def load_joined(db_path: str) -> pd.DataFrame:
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    q = """
    WITH outcomes AS (
      SELECT
        cml.run_id,
        mr.outcome_bool AS market_outcome
      FROM claim_market_link cml
      JOIN market_resolutions mr ON mr.market_id = cml.market_id
    )
    SELECT
      fr.id AS run_id,
      fr.created_at,
      fr.mode,
      fr.prior_p, fr.web_p, fr.combined_p,
      fr.market_mid_at_run,
      -- prefer market outcome if linked, else resolver truth if present
      COALESCE(outcomes.market_outcome, fr.resolved_truth) AS label
    FROM forecast_runs fr
    LEFT JOIN outcomes ON outcomes.run_id = fr.id
    WHERE COALESCE(outcomes.market_outcome, fr.resolved_truth) IS NOT NULL
    """
    df = pd.read_sql_query(q, con)
    con.close()
    return df

def brier(p: float, y: int) -> float:
    if p is None or math.isnan(p): return float('nan')
    return (p - y) ** 2

def reliability_bins(df: pd.DataFrame, col: str, bins=10) -> pd.DataFrame:
    # Drop NaNs
    tmp = df[[col, 'label']].dropna().copy()
    tmp['bin'] = pd.cut(tmp[col], bins=bins, right=False, labels=False)
    grp = tmp.groupby('bin', as_index=False).agg(
        n=('label', 'size'),
        p_hat=(col, 'mean'),
        y_rate=('label', 'mean')
    )
    grp['abs_calib_gap'] = (grp['p_hat'] - grp['y_rate']).abs()
    return grp

def summarize(df: pd.DataFrame) -> None:
    # overall Brier by mode & estimator
    rows = []
    for mode in ['baseline','web_informed']:
        sub = df[df['mode']==mode]
        if sub.empty: continue
        for col in ['prior_p','web_p','combined_p']:
            if col not in sub.columns: continue
            s = sub.apply(lambda r: brier(r[col], int(r['label'])), axis=1)
            rows.append({
                'mode': mode,
                'estimator': col.replace('_p',''),
                'n': int(s.notna().sum()),
                'brier_mean': float(s.mean(skipna=True))
            })
    print("\n=== Brier (lower is better) ===")
    print(pd.DataFrame(rows).sort_values(['mode','brier_mean']))

    # market edge when available
    df_edge = df[['combined_p','market_mid_at_run']].dropna()
    if not df_edge.empty:
        df_edge = df_edge.assign(edge = df_edge['combined_p'] - df_edge['market_mid_at_run'])
        print("\n=== Edge vs market (combined_p - market_mid_at_run) ===")
        print(df_edge['edge'].describe(percentiles=[.1,.25,.5,.75,.9]))

    # calibration bins for combined
    if 'combined_p' in df.columns:
        print("\n=== Calibration bins (combined) ===")
        print(reliability_bins(df, 'combined_p', bins=10))

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", required=True, help="Path to SQLite DB (e.g., data/heretix.db)")
    args = ap.parse_args()
    df = load_joined(args.db)
    if df.empty:
        print("No labeled rows yet (no market resolution or resolver truth).")
        return
    summarize(df)

if __name__ == "__main__":
    main()

Run it

uv run python tools/eval.py --db data/heretix.db

You’ll get:
	•	Brier per mode (baseline, web_informed) and per estimator (prior, web, combined)
	•	Edge summary (combined_p - market_mid_at_run)
	•	Calibration bins (how predicted probabilities line up with empirical frequencies)

⸻

3) (Optional) Append each run to Parquet (partitioned)

If you want a Parquet “data lake” locally, write one file per run into a directory; analytics tools read the whole directory as a single dataset.

# utils/parquet_sink.py
import uuid, os
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

def write_run_to_parquet(row_dict: dict, dataset_dir: str = "runs/forecast_runs"):
    os.makedirs(dataset_dir, exist_ok=True)
    df = pd.DataFrame([row_dict])
    table = pa.Table.from_pandas(df)
    fname = os.path.join(dataset_dir, f"part-{uuid.uuid4().hex}.parquet")
    pq.write_table(table, fname)
    return fname

Later, read with pyarrow.dataset.dataset("runs/forecast_runs").to_table().to_pandas() or with DuckDB:
duckdb.sql("SELECT * FROM 'runs/forecast_runs/*.parquet'").

⸻

4) Where to write each field (quick map)
	•	After a run finishes, write one row to forecast_runs:
	•	All RPL fields (prior, CI, stability)
	•	All WEL fields (web, CI, docs/domains/agreement/recency)
	•	Fusion outputs (combined_p, CI, w_web, recency_score, strength_score)
	•	Knobs / provenance (k,r,wel_reps,wel_max_docs,prompt_version,provider_set,seed_bigint)
	•	Cost (tokens_in/out, cost_usd)
	•	If you captured a market mid at the run time, set market_mid_at_run
	•	Also append the same dict to Parquet if you want fast analytics.
	•	When you link a run to a market, insert a row into claim_market_link.
	•	When a market resolves, insert/update in market_resolutions (then eval.py will pick it up next time).

⸻

That’s it

With these tables and the evaluator, you can:
	•	Log every forecast in one tidy row.
	•	Link runs to Kalshi/Polymarket markets.
	•	Compute accuracy (Brier), calibration, and edge as soon as outcomes arrive.
	•	Grow a consistent, ML/RL‑ready dataset—all on your laptop, SQLite‑first.

Totally get it—staring at tables via CLI is rough. Here are two simple, friendly ways to explore your data locally today, using your existing SQLite DB. You can start with the 2‑minute option (Datasette) and then graduate to a richer, purpose‑built dashboard (Streamlit) that shows calibration, bias, and market edges.

⸻

Option A (2‑minute setup): Datasette — point‑and‑click SQLite browser

What you get
	•	Clickable tables and filters for forecast_runs, markets, market_quotes, etc.
	•	Instant search and saved queries.
	•	Runs entirely on your laptop.

How

pip install datasette
datasette data/heretix.db --open

Then open the browser tab it launches. You’ll be able to sort/filter and export rows. This is great for quick inspection and debugging.

Tip: you can add a view for just the essentials with a saved SQL:

SELECT created_at, mode, prior_p, web_p, combined_p,
       combined_ci_lo, combined_ci_hi, w_web, docs_count, domains_count,
       market_mid_at_run
FROM forecast_runs
ORDER BY created_at DESC
LIMIT 500;


⸻

Option B (simple, guided analytics): Streamlit “Heretix Viewer”

What you get
	•	A clean, local web dashboard with:
	•	Overview KPIs: #runs, %resolved, median CI width, average stability (baseline), average cost/tokens.
	•	Bias chart: distribution of (web − prior).
	•	Calibration plot: how predicted probability matches true frequency (Brier included).
	•	Market edge: our combined_p vs market mid, plus edge histogram.
	•	Run explorer: searchable/filterable table; click a run to see details (prior | web | combined, weights, evidence stats).
	•	Still local. No auth. One command to run.

1) Install

pip install streamlit pandas matplotlib

2) Create viewer/app.py

Paste the code below; it reads from your SQLite and renders the main views.

# viewer/app.py
import sqlite3, math
from datetime import datetime, timedelta
from typing import Optional, Tuple
import pandas as pd
import streamlit as st
import matplotlib.pyplot as plt

st.set_page_config(page_title="Heretix Viewer", layout="wide")

# ---------- Config ----------
DEFAULT_DB = "data/heretix.db"

# ---------- Data helpers ----------
def load_runs(db_path: str, days: int = 90) -> pd.DataFrame:
    con = sqlite3.connect(db_path)
    q = """
    SELECT
      id, created_at, mode,
      prior_p, prior_ci_lo, prior_ci_hi, prior_stability,
      web_p, web_ci_lo, web_ci_hi, docs_count, domains_count, agreement, recency_days,
      combined_p, combined_ci_lo, combined_ci_hi, w_web, recency_score, strength_score,
      k, r, wel_reps, wel_max_docs, prompt_version, provider_set,
      tokens_in, tokens_out, cost_usd, seed_bigint,
      resolved_flag, resolved_truth, market_mid_at_run
    FROM forecast_runs
    ORDER BY created_at DESC
    """
    df = pd.read_sql_query(q, con)
    con.close()
    # Parse time; filter by recent days
    if not df.empty:
        df["created_at"] = pd.to_datetime(df["created_at"], errors="coerce", utc=True)
        cutoff = pd.Timestamp.utcnow() - pd.Timedelta(days=days)
        df = df[df["created_at"] >= cutoff]
    return df

def brier(p: float, y: int) -> Optional[float]:
    if p is None or pd.isna(p) or y is None or pd.isna(y): return None
    return (float(p) - int(y))**2

def reliability_bins(df: pd.DataFrame, col: str, bins: int = 10) -> pd.DataFrame:
    tmp = df[[col, "label"]].dropna()
    if tmp.empty: return pd.DataFrame(columns=["bin","n","p_hat","y_rate","abs_gap"])
    tmp["bin"] = pd.cut(tmp[col], bins=bins, right=False, labels=False)
    grp = tmp.groupby("bin", as_index=False).agg(
        n=("label","size"),
        p_hat=(col,"mean"),
        y_rate=("label","mean")
    )
    grp["abs_gap"] = (grp["p_hat"] - grp["y_rate"]).abs()
    return grp

# ---------- Sidebar ----------
st.sidebar.title("Heretix Viewer")
db_path = st.sidebar.text_input("SQLite DB path", value=DEFAULT_DB)
days = st.sidebar.slider("Show last N days", min_value=7, max_value=365, value=90, step=7)
mode_filter = st.sidebar.multiselect("Modes", options=["baseline","web_informed"], default=["baseline","web_informed"])
st.sidebar.caption("Tip: update DB path to point at any SQLite file.")

# ---------- Load ----------
df = load_runs(db_path, days=days)
if df.empty:
    st.warning("No runs found. Check DB path or run some forecasts.")
    st.stop()

df = df[df["mode"].isin(mode_filter)]

# Create label column (resolved truth if available)
df["label"] = df["resolved_truth"]
resolved_df = df.dropna(subset=["label"]).copy()

# ---------- Header ----------
st.markdown("## Heretix Analytics")
st.caption("Local dashboard for RPL / Web‑Informed runs")

# ---------- KPIs ----------
col1, col2, col3, col4, col5 = st.columns(5)
col1.metric("Runs (last {}d)".format(days), len(df))
col2.metric("Resolved with labels", len(resolved_df))
med_ci = (df["combined_ci_hi"] - df["combined_ci_lo"]).median(skipna=True)
col3.metric("Median CI width (combined)", f"{med_ci:.3f}" if not math.isnan(med_ci) else "—")
stab = df.loc[df["mode"]=="baseline","prior_stability"].mean(skipna=True)
col4.metric("Avg stability (baseline)", f"{stab:.3f}" if stab==stab else "—")
avg_cost = df["cost_usd"].mean(skipna=True)
col5.metric("Avg cost/run (USD)", f"{avg_cost:.3f}" if avg_cost==avg_cost else "—")

st.divider()

# ---------- Bias: web - prior ----------
st.subheader("Bias: Web vs Prior")
bias_df = df[["web_p","prior_p"]].dropna()
if not bias_df.empty:
    bias = (bias_df["web_p"] - bias_df["prior_p"]).dropna()
    fig, ax = plt.subplots()
    ax.hist(bias, bins=25)
    ax.set_title("Histogram: (web_p − prior_p)")
    ax.set_xlabel("Delta")
    ax.set_ylabel("Count")
    st.pyplot(fig)
else:
    st.info("No runs with both web_p and prior_p available.")

st.divider()

# ---------- Market edge ----------
st.subheader("Edge vs Market (when available)")
edge_df = df[["combined_p","market_mid_at_run"]].dropna()
if not edge_df.empty:
    edge_df = edge_df.assign(edge = edge_df["combined_p"] - edge_df["market_mid_at_run"])
    colA, colB = st.columns([2,1])
    with colA:
        fig2, ax2 = plt.subplots()
        ax2.hist(edge_df["edge"], bins=25)
        ax2.set_title("Histogram: Edge = combined_p − market_mid")
        ax2.set_xlabel("Edge")
        ax2.set_ylabel("Count")
        st.pyplot(fig2)
    with colB:
        st.write(edge_df["edge"].describe(percentiles=[.1,.25,.5,.75,.9]))
else:
    st.info("No market snapshots stored on runs yet.")

st.divider()

# ---------- Calibration & Brier (resolved only) ----------
st.subheader("Calibration & Brier (resolved only)")
if not resolved_df.empty:
    # Brier by estimator
    briers = {}
    for col in ["prior_p","web_p","combined_p"]:
        if col in resolved_df.columns:
            briers[col] = resolved_df.apply(lambda r: brier(r[col], r["label"]), axis=1).dropna()
    cols = st.columns(len(briers))
    for (i,(name, series)) in enumerate(briers.items()):
        cols[i].metric(f"Brier: {name.replace('_p','')}", f"{series.mean():.3f}")

    # Reliability bins for combined
    rel = reliability_bins(resolved_df, "combined_p", bins=10)
    if not rel.empty:
        fig3, ax3 = plt.subplots()
        ax3.plot(rel["p_hat"], rel["y_rate"], marker="o")
        ax3.plot([0,1],[0,1], linestyle="--")
        ax3.set_title("Reliability: combined_p")
        ax3.set_xlabel("Predicted")
        ax3.set_ylabel("Empirical")
        st.pyplot(fig3)
        st.dataframe(rel, use_container_width=True)
else:
    st.info("No resolved labels yet—add market outcomes or resolver truth to see calibration.")

st.divider()

# ---------- Run explorer ----------
st.subheader("Run Explorer")
q = st.text_input("Search claim text (contains)...", "")
view = df.copy()
if q:
    view = view[view["claim_text"].str.contains(q, case=False, na=False)]
view_show = view[[
    "created_at","mode","claim_text",
    "prior_p","web_p","combined_p",
    "combined_ci_lo","combined_ci_hi","w_web",
    "docs_count","domains_count","agreement","recency_days",
    "market_mid_at_run","resolved_truth"
]].sort_values("created_at", ascending=False)
st.dataframe(view_show, use_container_width=True, height=350)

# ---------- Run details ----------
st.subheader("Run Details")
run_id = st.selectbox("Pick a run id", options=view["id"].tolist())
detail = df[df["id"]==run_id].iloc[0]

colL, colR = st.columns(2)
with colL:
    st.write("**Prior (RPL)**")
    st.write({
        "prior_p": detail["prior_p"],
        "prior_ci": [detail["prior_ci_lo"], detail["prior_ci_hi"]],
        "prior_stability": detail["prior_stability"]
    })
    st.write("**Web (WEL)**")
    st.write({
        "web_p": detail["web_p"],
        "web_ci": [detail["web_ci_lo"], detail["web_ci_hi"]],
        "docs_count": detail["docs_count"],
        "domains_count": detail["domains_count"],
        "agreement": detail["agreement"],
        "recency_days": detail["recency_days"]
    })
with colR:
    st.write("**Combined**")
    st.write({
        "combined_p": detail["combined_p"],
        "combined_ci": [detail["combined_ci_lo"], detail["combined_ci_hi"]],
        "w_web": detail["w_web"],
        "recency_score": detail["recency_score"],
        "strength_score": detail["strength_score"]
    })
    st.write("**Provenance / Cost**")
    st.write({
        "k": detail["k"], "r": detail["r"],
        "wel_reps": detail["wel_reps"], "wel_max_docs": detail["wel_max_docs"],
        "prompt_version": detail["prompt_version"],
        "provider_set": detail["provider_set"],
        "tokens_in": detail["tokens_in"], "tokens_out": detail["tokens_out"],
        "cost_usd": detail["cost_usd"], "seed_bigint": detail["seed_bigint"]
    })

3) Run it

streamlit run viewer/app.py

It will open at http://localhost:8501. Point it at your SQLite file in the sidebar if your DB path differs.

⸻

Why these two are enough (for now)
	•	Datasette gets you instant browsing and filtering with no code changes.
	•	Streamlit viewer gives you a “lab notebook” you can live in:
	•	See how the web shifts the prior (bias).
	•	Check calibration and Brier as markets resolve.
	•	Inspect individual runs with all the knobs and weights.
	•	Compare our probability vs market at the time of each run.

When you’re ready to add multi‑model and RL, this same viewer can sprout:
	•	A provider filter (provider_set),
	•	A feature importance chart (once you train a small calibrator),
	•	And a “what‑if” panel to try different w_web fusions on a past claim.

If you want me to, I can also sketch a Datasette plugin config for quick charts, or add a “Download CSV” button & Parquet ingest to the Streamlit app.