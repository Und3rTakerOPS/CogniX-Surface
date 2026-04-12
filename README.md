# CogniX Surface

> Cognitive risk analysis platform for detecting social engineering attacks in corporate communications.

<img width="1916" height="1077" alt="CongniX" src="https://github.com/user-attachments/assets/72d85b2e-7946-48ce-8b7a-a3124a4fa166" />

---

## Overview

CogniX Surface analyzes text communications for cognitive attack patterns (phishing, BEC, pretexting, CEO fraud). The system combines:

- **Semantic NLP** — sentence-transformers embeddings (`all-MiniLM-L6-v2`)
- **Feature engineering** — 11 psychological dimensions (urgency, authority, trust, fear, social proof, reciprocity, commitment, liking) + linguistic signals (sentiment, text length)
- **Explainable scoring** — configurable weights, exponential transformation, per-feature contribution breakdown
- **Interactive web dashboard** — FastAPI + Bootstrap + Vega-Lite
- **Operational triage** — prioritized queue with SLA, SQLite persistence, API Key authentication

The goal is to accelerate analyst workflows (prioritization, investigation, follow-up), not to replace human decision-making.

---

## Project Status

| Metric | Value |
|--------|-------|
| Backend API | `app/dashboard.py` — 20 REST endpoints |
| Frontend | `app/templates/dashboard.html` — Bootstrap 5 + Vanilla JS + Vega-Embed |
| Persistence | SQLite WAL (`app/database.py`) — 4 tables |
| Automated tests | **153** (13 test files) |
| Demo dataset | `datacommunications.txt.txt` — 115 messages, 20 users |
| Containerization | Docker + docker-compose |
| Authentication | API Key (`X-API-Key`) on 8 sensitive endpoints |
| Rate limiting | slowapi (120/min global, 3/min on pipeline) |

---

## Key Capabilities

### 1) Analytics Pipeline

| Step | Module | Description |
|------|--------|-------------|
| 1 | `ingestion/loader.py` | CSV loading (`;` separator), encoding fallback, deduplication |
| 2 | `analysis/nlp_engine.py` | Semantic embeddings (sentence-transformers, batch 64) |
| 3 | `analysis/analyzer.py` | VADER sentiment analysis + keyword counting across 7 categories |
| 4 | `analysis/feature_engineering.py` | Regex pattern matching + min-max normalization + `1-exp(-x)` transform |
| 5 | `model/risk_engine.py` | Weighted scoring with absolute normalization, per-feature contributions, dominant driver |
| 6 | `app/dashboard.py` | REST API + interactive dashboard visualization |

### 2) Interactive Dashboard

- **Core KPIs**: volume, risk distribution, average/max risk, high-risk percentage
- **9 visualizations**: histogram, donut, driver bar, user scatter, contribution heatmap, correlation matrix, boxplot, weights, feature averages
- **Advanced filters**: risk range, bands (Low/Medium/High), driver, users, text query, top-N
- **Tables**: sortable, searchable, paginated (offset/limit with `has_more` metadata)
- **Explainability**: detail cards with per-feature contribution breakdown for high-risk messages
- **Filter presets**: save/load filter configurations (max 50, persisted in SQLite)

### 3) Operations and Monitoring

- Real-time pipeline progress via **SSE** (`/api/run/stream`) with `progress`, `done`, `fatal` events
- Configurable auto-refresh
- **KPI Timeline**: snapshot history after each run (max 200, persisted in SQLite)
- Run history with KPI delta comparison between runs
- Run history persistence via IndexedDB + localStorage fallback
- **Audit log**: action recording (status changes, weight updates, webhooks) in SQLite

### 4) Advanced Alerting

- Native browser notifications
- Multi-rule triggers: high-risk percentage, average risk, high-risk count
- Anti-spam cooldown + daily max-per-rule cap
- **Backend webhook relay** with:
  - HMAC-SHA256 signing (`X-CogniX-Signature`)
  - Exponential retry (3 attempts, backoff up to 4s)
  - No retry on 4xx errors
- Dedicated alert history in UI

### 5) Operational Triage

- Case queue with workflow: `new` → `in_progress` → `mitigated` / `false_positive`
- **Automatic priority**: `P1` (High), `P2` (Medium), `P3` (Low) based on risk score
- **Automatic SLA** deadlines for open items with overdue flag; queue ordering prioritizes overdue items
- Assignee and operational notes (XSS-sanitized)
- **Bulk update**: mass update up to 250 items per request
- Automatic sync from results + manual bootstrap
- **Full persistence** in SQLite (triage, presets, timeline, audit)

### 6) UI Personalization

- Light/dark mode
- Custom color themes and backgrounds
- Custom sidebar appearance
- Preferences persisted in browser storage

### 7) Security and Hardening

- **API Key authentication** (`X-API-Key`) with constant-time comparison (`hmac.compare_digest`)
- **Input sanitization**: `html.escape()` on notes, assignee, preset names; `max_length` on all Pydantic string fields
- **Rate limiting**: 120 req/min global, 3 req/min on pipeline endpoints
- **Configurable CORS** via env (`COGNIX_CORS_ORIGINS`)
- **Environment variables** via `.env` (python-dotenv)
- **Dev mode**: authentication disabled when `COGNIX_API_KEY` is empty

---

## Repository Layout

```text
Cognitive_Attack_Mapper/
├── .dockerignore
├── .env                             # Environment variables (do not commit)
├── .env.example                     # Environment template
├── docker-compose.yml
├── Dockerfile
├── README.md                        # Italian version
├── README.en.md                     # This file
├── requirements.txt                 # 14 Python dependencies
├── datacommunications.txt.txt       # Demo dataset (115 messages, 20 users)
│
├── analysis/
│   ├── __init__.py
│   ├── analyzer.py                  # VADER sentiment + keyword counting
│   ├── constants.py                 # Keywords, regex, risk band thresholds
│   ├── feature_engineering.py       # Regex matching + normalization + transform
│   └── nlp_engine.py               # Sentence-transformers embeddings
│
├── app/
│   ├── __init__.py
│   ├── dashboard.py                 # Main FastAPI app (20 endpoints)
│   ├── database.py                  # SQLite persistence layer (4 tables, WAL mode)
│   ├── main.py                      # CLI entry point
│   ├── static/
│   │   └── favicon.svg
│   └── templates/
│       └── dashboard.html           # Jinja2 HTML frontend (Bootstrap + Vega-Embed)
│
├── config/
│   ├── __init__.py
│   └── risk_weights.json            # 11 risk weights (sum = 1.00)
│
├── data/                            # SQLite DB created at runtime
├── docs/
│   ├── executive-one-pager.md
│   ├── executive-one-pager.en.md
│   ├── technical-stakeholder-security.md
│   └── technical-stakeholder-security.en.md
│
├── ingestion/
│   ├── __init__.py
│   └── loader.py                    # CSV loader with encoding fallback
│
├── logs/                            # Loguru logs at runtime
├── model/
│   ├── __init__.py
│   └── risk_engine.py               # Weighted scoring + explanations
│
├── tests/                           # 13 files, 153 tests
│   ├── __init__.py
│   ├── test_analyzer.py             # 8 tests — keyword counting, feature extraction
│   ├── test_api_contracts.py        # 11 tests — API contracts, 400/404 validation
│   ├── test_edge_cases.py           # 22 tests — unicode, emoji, long text, regex
│   ├── test_feature_engineering.py  # 1 test — feature column creation
│   ├── test_hardening.py            # 32 tests — DB, auth, sanitization, Docker
│   ├── test_integration.py          # 2 tests — end-to-end pipeline + determinism
│   ├── test_loader.py               # 1 test — data cleanup
│   ├── test_negative.py             # 8 tests — missing files, encoding, invalid weights
│   ├── test_nlp_engine.py           # 7 tests — shape, normalization, batch, model
│   ├── test_p1_features.py          # 58 tests — pagination, webhook retry, presets, KPI
│   ├── test_quickwins_v2.py         # 16 tests — Swagger, CORS, bulk triage, rate limit
│   ├── test_risk_engine.py          # 2 tests — score output + weight loading
│   └── test_triage_alert_weights.py # 57 tests — triage ops, weights, webhook HMAC, LRU cache
│
├── utils/
│   ├── __init__.py
│   └── logger.py                    # Loguru configuration
│
└── visualization/
    ├── __init__.py
    └── report.py                    # Rich table CLI report
```

---

## Requirements

- **Python** 3.10+
- **Virtual environment** recommended (`.venv`)
- **14 dependencies** in `requirements.txt`:

| Package | Version | Purpose |
|---------|---------|---------|
| pandas | >=1.3,<3.0 | Data manipulation |
| numpy | >=1.21,<2.0 | Numeric computation |
| scikit-learn | >=1.0,<2.0 | Normalization |
| networkx | >=2.6 | Graph analysis (future) |
| sentence-transformers | >=2.2.0,<3.0 | NLP embeddings |
| rich | >=13.0 | CLI reporting |
| loguru | >=0.6.0 | Structured logging |
| nltk | >=3.8 | Tokenization, VADER sentiment |
| altair | >=4.2,<6.0 | Vega-Lite chart specs |
| fastapi | >=0.100,<1.0 | API framework |
| uvicorn[standard] | >=0.20,<1.0 | ASGI server |
| jinja2 | >=3.1,<4.0 | HTML templating |
| slowapi | >=0.1.9 | Rate limiting |
| python-dotenv | >=1.0,<2.0 | `.env` variable loading |

### Installation

```bash
python -m venv .venv
.venv\Scripts\activate        # Windows
# source .venv/bin/activate   # Linux/macOS
pip install -r requirements.txt
```

---

## Environment Configuration

Copy `.env.example` to `.env` and customize:

```ini
# API Key to protect sensitive endpoints (run, weights, triage, webhook).
# If empty, authentication is disabled (development mode).
COGNIX_API_KEY=

# HMAC-SHA256 secret for signing outgoing webhook payloads.
COGNIX_WEBHOOK_SECRET=

# SQLite database path for persistence.
# Default: ./data/cognix.db
COGNIX_DB_PATH=./data/cognix.db

# Allowed CORS origins (comma-separated). Use * for development only.
COGNIX_CORS_ORIGINS=*

# Log level: DEBUG, INFO, WARNING, ERROR
LOG_LEVEL=INFO

# Global rate limit (requests/minute)
COGNIX_RATE_LIMIT=120/minute
```

---

## Quick Start

### Terminal

```bash
& .\.venv\Scripts\python.exe -m uvicorn app.dashboard:app --host 127.0.0.1 --port 8000 --reload
```

Open: [http://127.0.0.1:8000](http://127.0.0.1:8000)

### Docker

```bash
docker compose up --build
```

Service available at `http://localhost:8000`. Data persists in the `cognix-data` volume.

### VS Code Run/Debug

Recommended setup:

- `.vscode/launch.json` with `Dashboard (Uvicorn)`
- `.vscode/tasks.json` with `Run Dashboard (Uvicorn)`

---

## Recommended Workflow

1. Configure dataset and weights in the sidebar
2. Start **Run Analysis**
3. Follow SSE progress bar
4. Apply filters and analyze main tabs (Results, Users, Charts)
5. Review Alerts and Audit sections
6. Manage cases in the **Triage** tab (status, owner, notes, bulk update)
7. Export CSV for reporting

Default paths:

- Dataset: `datacommunications.txt.txt`
- Weights: `config/risk_weights.json`

---

## API Reference (20 Endpoints)

### Core Pipeline

| Method | Path | Description | Protected |
|--------|------|-------------|-----------|
| `GET` | `/` | Dashboard HTML page | No |
| `GET` | `/api/run/stream` | Pipeline SSE (progress → done/fatal) | No (3/min) |
| `POST` | `/api/run` | Synchronous pipeline execution | Yes |
| `POST` | `/api/results` | KPIs + chart specs + filtered/paginated tables | No |
| `GET` | `/api/user/{username}` | User drill-down details | No |
| `GET` | `/api/health` | Health check | No |

### Export

| Method | Path | Description | Protected |
|--------|------|-------------|-----------|
| `GET` | `/api/export/csv` | Full CSV export | No |
| `GET` | `/api/export/users` | Per-user summary export | No |
| `POST` | `/api/export/filtered` | Filtered CSV export | No |

### Risk Weights

| Method | Path | Description | Protected |
|--------|------|-------------|-----------|
| `GET` | `/api/weights` | Current weights | No |
| `POST` | `/api/weights` | Update weights + optional rescore | Yes |

### Triage

| Method | Path | Description | Protected |
|--------|------|-------------|-----------|
| `POST` | `/api/triage/list` | Triage queue with status/priority/owner/text filters | No |
| `PATCH` | `/api/triage/item/{id}` | Update single item status/assignee/note | Yes |
| `POST` | `/api/triage/bulk-update` | Mass update (max 250 items) | Yes |
| `POST` | `/api/triage/bootstrap` | Sync triage queue from analysis results | Yes |

### Alerting

| Method | Path | Description | Protected |
|--------|------|-------------|-----------|
| `POST` | `/api/alerts/webhook` | Relay alert to external webhook (with HMAC) | Yes |

### Filter Presets

| Method | Path | Description | Protected |
|--------|------|-------------|-----------|
| `GET` | `/api/filter-presets` | List saved presets | No |
| `POST` | `/api/filter-presets` | Create/save preset (max 50) | Yes |
| `DELETE` | `/api/filter-presets/{name}` | Delete preset | Yes |

### KPI Timeline

| Method | Path | Description | Protected |
|--------|------|-------------|-----------|
| `GET` | `/api/kpi-timeline` | KPI snapshot history (max 200) | No |

---

## Input Data Format

Expected format (`;` separator, no header row):

```text
user;message text
```

Example from the demo dataset (20 realistic Italian users, bilingual IT/EN messages):

```text
marco.rossi;Buongiorno a tutti, la riunione e' stata spostata alle 15:00 in sala Galileo
giulia.bianchi;Ricordo che le richieste ferie per agosto vanno inserite sul portale HR entro venerdi
alessia.conti;URGENT: Your corporate account has been suspended due to a security breach...
```

The dataset contains 115 messages with a realistic distribution: ~87% Low, ~8% Medium, ~5% High risk.

---

## Risk Weights (11 Features)

| Feature | Weight | Type | Description |
|---------|--------|------|-------------|
| `urgency_score` | 0.18 | Keyword/Regex | Urgency: urgent, immediately, asap, now, quick |
| `authority_score` | 0.15 | Keyword/Regex | Authority: manager, director, admin, IT |
| `semantic_signal` | 0.12 | Embedding | Semantic similarity to attack templates |
| `social_proof_score` | 0.10 | Keyword/Regex | Social pressure: everyone, everybody, tutti, already approved |
| `text_length_signal` | 0.08 | Length | Text length signal (normalized) |
| `sentiment_risk_signal` | 0.08 | VADER | Negative/manipulative sentiment |
| `reciprocity_score` | 0.08 | Keyword/Regex | Reciprocity: favor, return the favor, ricambia, per favore |
| `commitment_score` | 0.07 | Keyword/Regex | Commitment: as promised, as agreed, come concordato, come promesso |
| `trust_score` | 0.06 | Keyword/Regex | Trust: trust, confidential, secure, official, verified |
| `liking_score` | 0.04 | Keyword/Regex | Liking: dear friend, caro amico, ti stimo |
| `fear_score` | 0.04 | Keyword/Regex | Fear: account suspended, legal action, penalty, sospeso, bloccato |

Weights sum to exactly **1.00**. They are customizable via API (`POST /api/weights`) or by editing `config/risk_weights.json`.

---

## Risk Score Formula

For count-based features (keyword/regex matches):

$$
f_i' = 1 - e^{-f_i}
$$

> 1 match → 0.632, 2 matches → 0.865, 3 matches → 0.950

For features already in $[0,1]$ (sentiment, semantic, text_length):

$$
f_i' = \text{clip}(f_i, 0, 1)
$$

Final normalized score:

$$
\text{risk\_score} = \frac{\sum_i w_i \cdot f_i'}{\sum_i w_i}
$$

Risk bands:

| Band | Range | Color |
|------|-------|-------|
| Low | [0.0, 0.4) | Blue |
| Medium | [0.4, 0.7) | Orange |
| High | [0.7, 1.0] | Red |

---

## SQLite Database

Automatic persistence with 4 tables (WAL mode, thread-safe):

| Table | Content |
|-------|---------|
| `triage_items` | Triage queue (id, JSON data, updated_at) |
| `filter_presets` | Saved filter presets (name, JSON data, created_at) |
| `kpi_timeline` | KPI snapshots after each run (JSON data, created_at) |
| `audit_log` | Action audit trail (action, details, created_at) |

The database is created automatically on first startup at `COGNIX_DB_PATH` (default: `./data/cognix.db`).

---

## Testing

Run all 153 tests:

```bash
.venv\Scripts\python.exe -m pytest tests/ -v --tb=short
```

Coverage by area:

| Area | Tests | File |
|------|-------|------|
| Text analysis | 8 | `test_analyzer.py` |
| API contracts | 11 | `test_api_contracts.py` |
| Edge cases | 22 | `test_edge_cases.py` |
| Feature engineering | 1 | `test_feature_engineering.py` |
| Hardening (DB, auth, XSS, Docker) | 32 | `test_hardening.py` |
| Pipeline integration | 2 | `test_integration.py` |
| Data loader | 1 | `test_loader.py` |
| Negative cases | 8 | `test_negative.py` |
| NLP engine | 7 | `test_nlp_engine.py` |
| P1 features (pagination, webhook, presets, KPI) | 58 | `test_p1_features.py` |
| Quick-wins v2 (Swagger, CORS, bulk, rate limit) | 16 | `test_quickwins_v2.py` |
| Risk engine | 2 | `test_risk_engine.py` |
| Triage, alerts, weights, LRU cache | 57 | `test_triage_alert_weights.py` |

---

## Docker

### Build and run

```bash
docker compose up --build
```

### Container details

- **Base image**: `python:3.12-slim`
- **Exposed port**: 8000
- **Data volume**: `cognix-data` → `/app/data` (SQLite DB)
- **Health check**: every 30s on `/api/system/status`
- **Env file**: `.env` loaded automatically
- **Restart policy**: `unless-stopped`

---

## Quick Troubleshooting

### 1) Frontend JSON error (`Unexpected token ... Internal Server Error`)

An API endpoint returned plain-text 500 instead of JSON. Check backend logs and ensure a run (`POST /api/run` or `/api/run/stream`) is executed before requesting results.

### 2) Backend changes not visible

If Uvicorn runs without `--reload`, restart the server.

### 3) Webhook test failed

Ensure URL starts with `http://` or `https://`, target is reachable, and target accepts JSON `POST`. The system automatically retries 3 times on 5xx errors.

### 4) Empty triage queue

Run an analysis first, then trigger `POST /api/triage/bootstrap` or use the "Sync from results" button in the Triage tab.

### 5) 401 Unauthorized error

If `COGNIX_API_KEY` is set in `.env`, all protected endpoints require the `X-API-Key` header. To disable authentication, leave the variable empty.

### 6) Rate limit exceeded (429)

The global limit is 120 req/min. Pipeline endpoints (`/api/run`, `/api/run/stream`) have a 3 req/min limit. Wait for the reset indicated in the `X-RateLimit-Reset` header.

---

## Known Limitations

- Linear weighted scoring (not supervised/adaptive model)
- No native out-of-the-box SIEM connector
- SSE endpoint (`/api/run/stream`) not protected by API Key
- No RBAC (role-based access control)

## Technical Roadmap

1. SSRF protection on webhook endpoints
2. Security headers (CSP, HSTS, X-Frame-Options)
3. Authentication on SSE endpoint
4. Dedicated SIEM/SOAR connectors
5. Advanced RBAC/governance
6. GitHub Actions CI for automated testing

---

## Related Documentation

- EN: `docs/technical-stakeholder-security.en.md`
- EN: `docs/executive-one-pager.en.md`
- IT: `README.md`
- IT: `docs/technical-stakeholder-security.md`
- IT: `docs/executive-one-pager.md`
