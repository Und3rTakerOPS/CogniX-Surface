# CogniX Surface

> Piattaforma di analisi del rischio cognitivo per la rilevazione di attacchi di social engineering nelle comunicazioni aziendali.

---

## Panoramica

CogniX Surface analizza comunicazioni testuali alla ricerca di pattern di attacco cognitivo (phishing, BEC, pretexting, CEO fraud). Il sistema combina:

- **NLP semantico** — embedding con sentence-transformers (`all-MiniLM-L6-v2`)
- **Feature engineering** — 11 dimensioni psicologiche (urgenza, autorita, fiducia, paura, social proof, reciprocita, impegno, simpatia) + segnali linguistici (sentiment, lunghezza testo)
- **Scoring interpretabile** — pesi configurabili, trasformazione esponenziale, contributo spiegabile per feature
- **Dashboard web interattiva** — FastAPI + Bootstrap + Vega-Lite
- **Triage operativo** — coda prioritizzata con SLA, persistenza SQLite, autenticazione API Key

L'obiettivo non e sostituire l'analista umano, ma accelerare prioritizzazione, investigazione e follow-up.

---

## Stato del Progetto

| Metrica | Valore |
|---------|--------|
| Backend API | `app/dashboard.py` — 20 endpoint REST |
| Frontend | `app/templates/dashboard.html` — Bootstrap 5 + Vanilla JS + Vega-Embed |
| Persistenza | SQLite WAL (`app/database.py`) — 4 tabelle |
| Test automatici | **153** (13 file di test) |
| Dataset demo | `datacommunications.txt.txt` — 115 messaggi, 20 utenti |
| Containerizzazione | Docker + docker-compose |
| Autenticazione | API Key (`X-API-Key`) su 8 endpoint sensibili |
| Rate limiting | slowapi (120/min globale, 3/min su pipeline) |

---

## Funzionalita Principali

### 1) Pipeline Analitica

| Step | Modulo | Descrizione |
|------|--------|-------------|
| 1 | `ingestion/loader.py` | Caricamento CSV (`;` separator), fallback encoding, deduplicazione |
| 2 | `analysis/nlp_engine.py` | Embedding semantici (sentence-transformers, batch 64) |
| 3 | `analysis/analyzer.py` | Analisi VADER sentiment + conteggio keyword per 7 categorie |
| 4 | `analysis/feature_engineering.py` | Regex pattern matching + normalizzazione min-max + trasformazione `1-exp(-x)` |
| 5 | `model/risk_engine.py` | Scoring pesato con normalizzazione assoluta, contributi per feature, driver dominante |
| 6 | `app/dashboard.py` | Esposizione API REST + visualizzazione dashboard interattiva |

### 2) Dashboard Interattiva

- **KPI principali**: volumi, distribuzione rischio, rischio medio/max, percentuale high-risk
- **9 visualizzazioni**: histogram, donut, driver bar, scatter utenti, heatmap contributi, correlation matrix, boxplot, weights, feature averages
- **Filtri avanzati**: intervallo rischio, bande (Low/Medium/High), driver, utenti, query testo, top-N
- **Tabelle**: ordinamento, ricerca locale, paginazione (offset/limit con metadata `has_more`)
- **Explainability**: detail card con breakdown contributi per messaggi ad alto rischio
- **Preset filtri**: salvataggio/caricamento configurazioni filtro (max 50, persistiti su SQLite)

### 3) Operativita e Monitoraggio

- Progress pipeline real-time via **SSE** (`/api/run/stream`) con eventi `progress`, `done`, `fatal`
- Auto-refresh dashboard configurabile
- **KPI Timeline**: storico snapshot dopo ogni run (max 200, persistiti su SQLite)
- Run history con confronto KPI delta tra run
- Persistenza run history con IndexedDB + fallback localStorage
- **Audit log**: registrazione azioni (cambi stato, update pesi, webhook) su SQLite

### 4) Alerting Avanzato

- Notifiche browser native
- Regole multi-trigger: high-risk percentage, avg risk, high-risk count
- Cooldown anti-spam + limite giornaliero per regola
- **Webhook relay** backend con:
  - Firma HMAC-SHA256 (`X-CogniX-Signature`)
  - Retry esponenziale (3 tentativi, backoff fino a 4s)
  - No retry su errori 4xx
- Storico alert dedicato in UI

### 5) Triage Operativo

- Coda casi con workflow: `new` → `in_progress` → `mitigated` / `false_positive`
- **Priorita automatica**: `P1` (High), `P2` (Medium), `P3` (Low) basata su risk score
- **SLA automatici** per item aperti con flag overdue; ordinamento coda prioritizza SLA scaduti
- Assegnatario e note operative (sanitizzate anti-XSS)
- **Bulk update**: aggiornamento massivo fino a 250 item per richiesta
- Sync automatica da risultati + bootstrap manuale
- **Persistenza completa** su SQLite (triage, preset, timeline, audit)

### 6) Personalizzazione UI

- Tema chiaro/scuro
- Palette colore e background personalizzabili
- Sidebar theme personalizzabile
- Preferenze persistite su storage locale browser

### 7) Sicurezza e Hardening

- **Autenticazione API Key** (`X-API-Key`) con confronto costante (`hmac.compare_digest`)
- **Sanitizzazione input**: `html.escape()` su note, assegnatario, nomi preset; `max_length` su tutti i campi Pydantic
- **Rate limiting**: 120 req/min globale, 3 req/min sugli endpoint pipeline
- **CORS configurabile** via env (`COGNIX_CORS_ORIGINS`)
- **Variabili ambiente** via `.env` (python-dotenv)
- **Modalita sviluppo**: autenticazione disabilitata se `COGNIX_API_KEY` vuota

---

## Struttura Repository

```text
Cognitive_Attack_Mapper/
├── .dockerignore
├── .env                             # Variabili ambiente (non committare)
├── .env.example                     # Template variabili ambiente
├── docker-compose.yml
├── Dockerfile
├── README.md                        # Questo file
├── README.en.md                     # Versione inglese
├── requirements.txt                 # 14 dipendenze Python
├── datacommunications.txt.txt       # Dataset demo (115 messaggi, 20 utenti)
│
├── analysis/
│   ├── __init__.py
│   ├── analyzer.py                  # VADER sentiment + keyword counting
│   ├── constants.py                 # Keyword, regex, soglie bande rischio
│   ├── feature_engineering.py       # Regex matching + normalizzazione + trasformazione
│   └── nlp_engine.py               # Sentence-transformers embedding
│
├── app/
│   ├── __init__.py
│   ├── dashboard.py                 # FastAPI app principale (20 endpoint)
│   ├── database.py                  # Persistenza SQLite (4 tabelle, WAL mode)
│   ├── main.py                      # Entry point CLI
│   ├── static/
│   │   └── favicon.svg
│   └── templates/
│       └── dashboard.html           # Frontend Jinja2 (Bootstrap + Vega-Embed)
│
├── config/
│   ├── __init__.py
│   └── risk_weights.json            # 11 pesi rischio (somma = 1.00)
│
├── data/                            # SQLite DB generato a runtime
├── docs/
│   ├── executive-one-pager.md
│   ├── executive-one-pager.en.md
│   ├── technical-stakeholder-security.md
│   └── technical-stakeholder-security.en.md
│
├── ingestion/
│   ├── __init__.py
│   └── loader.py                    # CSV loader con fallback encoding
│
├── logs/                            # Log Loguru a runtime
├── model/
│   ├── __init__.py
│   └── risk_engine.py               # Scoring pesato + spiegazioni
│
├── tests/                           # 13 file, 153 test
│   ├── __init__.py
│   ├── test_analyzer.py             # 8 test — keyword counting, feature extraction
│   ├── test_api_contracts.py        # 11 test — contratti API, validazione 400/404
│   ├── test_edge_cases.py           # 22 test — unicode, emoji, testi lunghi, regex
│   ├── test_feature_engineering.py  # 1 test — creazione colonne feature
│   ├── test_hardening.py            # 32 test — DB, auth, sanitizzazione, Docker
│   ├── test_integration.py          # 2 test — pipeline end-to-end + determinismo
│   ├── test_loader.py               # 1 test — pulizia dati
│   ├── test_negative.py             # 8 test — file mancanti, encoding, pesi invalidi
│   ├── test_nlp_engine.py           # 7 test — shape, normalizzazione, batch, modello
│   ├── test_p1_features.py          # 58 test — paginazione, webhook retry, preset, KPI
│   ├── test_quickwins_v2.py         # 16 test — Swagger, CORS, bulk triage, rate limit
│   ├── test_risk_engine.py          # 2 test — output score + caricamento pesi
│   └── test_triage_alert_weights.py # 57 test — triage ops, pesi, webhook HMAC, LRU cache
│
├── utils/
│   ├── __init__.py
│   └── logger.py                    # Configurazione Loguru
│
└── visualization/
    ├── __init__.py
    └── report.py                    # Report Rich per terminale
```

---

## Requisiti

- **Python** 3.10+
- **Virtual environment** consigliato (`.venv`)
- **14 dipendenze** in `requirements.txt`:

| Pacchetto | Versione | Scopo |
|-----------|----------|-------|
| pandas | >=1.3,<3.0 | Manipolazione dati |
| numpy | >=1.21,<2.0 | Calcolo numerico |
| scikit-learn | >=1.0,<2.0 | Normalizzazione |
| networkx | >=2.6 | Analisi grafi (futuro) |
| sentence-transformers | >=2.2.0,<3.0 | Embedding NLP |
| rich | >=13.0 | Report CLI |
| loguru | >=0.6.0 | Logging strutturato |
| nltk | >=3.8 | Tokenizzazione, VADER sentiment |
| altair | >=4.2,<6.0 | Specifiche chart Vega-Lite |
| fastapi | >=0.100,<1.0 | Framework API |
| uvicorn[standard] | >=0.20,<1.0 | Server ASGI |
| jinja2 | >=3.1,<4.0 | Template HTML |
| slowapi | >=0.1.9 | Rate limiting |
| python-dotenv | >=1.0,<2.0 | Variabili `.env` |

### Installazione

```bash
python -m venv .venv
.venv\Scripts\activate        # Windows
# source .venv/bin/activate   # Linux/macOS
pip install -r requirements.txt
```

---

## Configurazione Ambiente

Copia `.env.example` in `.env` e personalizza:

```ini
# API Key per proteggere endpoint sensibili (run, weights, triage, webhook).
# Se vuota, l'autenticazione e disabilitata (modalita sviluppo).
COGNIX_API_KEY=

# Segreto HMAC-SHA256 per firmare i payload webhook in uscita.
COGNIX_WEBHOOK_SECRET=

# Percorso database SQLite per persistenza.
# Default: ./data/cognix.db
COGNIX_DB_PATH=./data/cognix.db

# Origini CORS ammesse (separate da virgola). Usa * solo in sviluppo.
COGNIX_CORS_ORIGINS=*

# Livello di log: DEBUG, INFO, WARNING, ERROR
LOG_LEVEL=INFO

# Rate limiting globale (richieste/minuto)
COGNIX_RATE_LIMIT=120/minute
```

---

## Avvio Rapido

### Da terminale

```bash
.venv\Scripts\python.exe -m uvicorn app.dashboard:app --host 127.0.0.1 --port 8000 --reload
```

Apri: [http://127.0.0.1:8000](http://127.0.0.1:8000)

### Con Docker

```bash
docker compose up --build
```

Il servizio e disponibile su `http://localhost:8000`. I dati persistono nel volume `cognix-data`.

### Da VS Code (Run/Debug)

Configurazioni consigliate:

- `.vscode/launch.json` con `Dashboard (Uvicorn)`
- `.vscode/tasks.json` con `Run Dashboard (Uvicorn)`

---

## Workflow Consigliato

1. Configura dataset e pesi nella sidebar
2. Avvia **Run Analysis**
3. Monitora avanzamento nella progress bar SSE
4. Applica filtri e analizza i tab principali (Results, Users, Charts)
5. Verifica la sezione Alert e Registro
6. Gestisci i casi nel tab **Triage** (stato, owner, note, bulk update)
7. Esporta CSV per reportistica

Percorsi default:

- Dataset: `datacommunications.txt.txt`
- Pesi: `config/risk_weights.json`

---

## API Reference (20 Endpoint)

### Core Pipeline

| Metodo | Path | Descrizione | Protetto |
|--------|------|-------------|----------|
| `GET` | `/` | Dashboard HTML | No |
| `GET` | `/api/run/stream` | Pipeline SSE (progress → done/fatal) | No (3/min) |
| `POST` | `/api/run` | Pipeline sincrona | Si |
| `POST` | `/api/results` | KPI + chart specs + tabelle filtrate/paginate | No |
| `GET` | `/api/user/{username}` | Dettaglio utente | No |
| `GET` | `/api/health` | Health check | No |

### Export

| Metodo | Path | Descrizione | Protetto |
|--------|------|-------------|----------|
| `GET` | `/api/export/csv` | Export CSV completo | No |
| `GET` | `/api/export/users` | Export aggregato per utente | No |
| `POST` | `/api/export/filtered` | Export CSV con filtri applicati | No |

### Pesi Rischio

| Metodo | Path | Descrizione | Protetto |
|--------|------|-------------|----------|
| `GET` | `/api/weights` | Pesi correnti | No |
| `POST` | `/api/weights` | Aggiorna pesi + opzionale rescore | Si |

### Triage

| Metodo | Path | Descrizione | Protetto |
|--------|------|-------------|----------|
| `POST` | `/api/triage/list` | Coda triage con filtri stato/priorita/owner/testo | No |
| `PATCH` | `/api/triage/item/{id}` | Aggiorna stato/assegnatario/nota singolo item | Si |
| `POST` | `/api/triage/bulk-update` | Aggiornamento massivo (max 250 item) | Si |
| `POST` | `/api/triage/bootstrap` | Sync coda triage da risultati analisi | Si |

### Alerting

| Metodo | Path | Descrizione | Protetto |
|--------|------|-------------|----------|
| `POST` | `/api/alerts/webhook` | Relay alert a webhook esterno (con HMAC) | Si |

### Filter Preset

| Metodo | Path | Descrizione | Protetto |
|--------|------|-------------|----------|
| `GET` | `/api/filter-presets` | Lista preset salvati | No |
| `POST` | `/api/filter-presets` | Crea/salva preset (max 50) | Si |
| `DELETE` | `/api/filter-presets/{name}` | Elimina preset | Si |

### KPI Timeline

| Metodo | Path | Descrizione | Protetto |
|--------|------|-------------|----------|
| `GET` | `/api/kpi-timeline` | Storico snapshot KPI (max 200) | No |

---

## Formato Input Dati

Formato atteso (`;` come separatore, senza riga header):

```text
utente;testo del messaggio
```

Esempio dal dataset demo (20 utenti italiani realistici, messaggi bilingue IT/EN):

```text
marco.rossi;Buongiorno a tutti, la riunione e' stata spostata alle 15:00 in sala Galileo
giulia.bianchi;Ricordo che le richieste ferie per agosto vanno inserite sul portale HR entro venerdi
alessia.conti;URGENT: Your corporate account has been suspended due to a security breach...
```

Il dataset contiene 115 messaggi con distribuzione realistica: ~87% Low, ~8% Medium, ~5% High risk.

---

## Pesi Rischio (11 Feature)

| Feature | Peso | Tipo | Descrizione |
|---------|------|------|-------------|
| `urgency_score` | 0.18 | Keyword/Regex | Urgenza: urgent, immediately, asap, now, quick |
| `authority_score` | 0.15 | Keyword/Regex | Autorita: manager, director, admin, IT |
| `semantic_signal` | 0.12 | Embedding | Similarita semantica a template di attacco |
| `social_proof_score` | 0.10 | Keyword/Regex | Pressione sociale: everyone, everybody, tutti, already approved |
| `text_length_signal` | 0.08 | Lunghezza | Segnale lunghezza testo (normalizzato) |
| `sentiment_risk_signal` | 0.08 | VADER | Sentiment negativo/manipolativo |
| `reciprocity_score` | 0.08 | Keyword/Regex | Reciprocita: favor, return the favor, ricambia, per favore |
| `commitment_score` | 0.07 | Keyword/Regex | Impegno: as promised, as agreed, come concordato, come promesso |
| `trust_score` | 0.06 | Keyword/Regex | Fiducia: trust, confidential, secure, official, verified |
| `liking_score` | 0.04 | Keyword/Regex | Simpatia: dear friend, caro amico, ti stimo |
| `fear_score` | 0.04 | Keyword/Regex | Paura: account suspended, legal action, penalty, sospeso, bloccato |

La somma dei pesi e esattamente **1.00**. I pesi sono personalizzabili via API (`POST /api/weights`) o modificando `config/risk_weights.json`.

---

## Formula Risk Score

Per feature count-based (conteggi keyword/regex):

$$
f_i' = 1 - e^{-f_i}
$$

> 1 match → 0.632, 2 match → 0.865, 3 match → 0.950

Per feature gia in $[0,1]$ (sentiment, semantic, text_length):

$$
f_i' = \text{clip}(f_i, 0, 1)
$$

Score normalizzato finale:

$$
\text{risk\_score} = \frac{\sum_i w_i \cdot f_i'}{\sum_i w_i}
$$

Bande rischio:

| Banda | Intervallo | Colore |
|-------|-----------|--------|
| Low | [0.0, 0.4) | Blu |
| Medium | [0.4, 0.7) | Arancione |
| High | [0.7, 1.0] | Rosso |

---

## Database SQLite

Persistenza automatica con 4 tabelle (WAL mode, thread-safe):

| Tabella | Contenuto |
|---------|-----------|
| `triage_items` | Coda triage (id, data JSON, updated_at) |
| `filter_presets` | Preset filtri salvati (name, data JSON, created_at) |
| `kpi_timeline` | Snapshot KPI dopo ogni run (data JSON, created_at) |
| `audit_log` | Audit trail azioni (action, details, created_at) |

Il DB viene creato automaticamente al primo avvio in `COGNIX_DB_PATH` (default: `./data/cognix.db`).

---

## Testing

Esegui tutti i 153 test:

```bash
.venv\Scripts\python.exe -m pytest tests/ -v --tb=short
```

Copertura per area:

| Area | Test | File |
|------|------|------|
| Analisi testo | 8 | `test_analyzer.py` |
| Contratti API | 11 | `test_api_contracts.py` |
| Edge case | 22 | `test_edge_cases.py` |
| Feature engineering | 1 | `test_feature_engineering.py` |
| Hardening (DB, auth, XSS, Docker) | 32 | `test_hardening.py` |
| Integrazione pipeline | 2 | `test_integration.py` |
| Loader dati | 1 | `test_loader.py` |
| Casi negativi | 8 | `test_negative.py` |
| NLP engine | 7 | `test_nlp_engine.py` |
| P1 features (paginazione, webhook, preset, KPI) | 58 | `test_p1_features.py` |
| Quick-wins v2 (Swagger, CORS, bulk, rate limit) | 16 | `test_quickwins_v2.py` |
| Risk engine | 2 | `test_risk_engine.py` |
| Triage, alert, pesi, LRU cache | 57 | `test_triage_alert_weights.py` |

---

## Docker

### Build e avvio

```bash
docker compose up --build
```

### Dettagli container

- **Immagine base**: `python:3.12-slim`
- **Porta esposta**: 8000
- **Volume dati**: `cognix-data` → `/app/data` (SQLite DB)
- **Health check**: ogni 30s su `/api/system/status`
- **Env file**: `.env` caricato automaticamente
- **Restart policy**: `unless-stopped`

---

## Troubleshooting Rapido

### 1) Errore JSON frontend (`Unexpected token ... Internal Server Error`)

Un endpoint API ha risposto 500 testuale. Verifica log backend e assicurati di eseguire prima una run (`POST /api/run` o `/api/run/stream`) prima di richiedere risultati.

### 2) Modifiche backend non visibili

Se il server e avviato senza `--reload`, riavvia Uvicorn.

### 3) Webhook test fallito

Controlla che l'URL inizi con `http://` o `https://`, che il target sia raggiungibile e che accetti `POST` JSON. Il sistema ritenta automaticamente 3 volte su errori 5xx.

### 4) Coda triage vuota

Esegui una run e poi usa `POST /api/triage/bootstrap` oppure il pulsante "Sincronizza da risultati" nel tab Triage.

### 5) Errore 401 Unauthorized

Se `COGNIX_API_KEY` e impostata nel `.env`, tutti gli endpoint protetti richiedono l'header `X-API-Key`. Per disabilitare l'autenticazione, lascia la variabile vuota.

### 6) Rate limit superato (429)

Il limite globale e 120 req/min. Gli endpoint pipeline (`/api/run`, `/api/run/stream`) hanno un limite di 3 req/min. Attendi il reset indicato nell'header `X-RateLimit-Reset`.

---

## Limiti Noti

- Scoring lineare pesato (non modello supervisionato/adattivo)
- Nessuna integrazione SIEM nativa out-of-the-box
- SSE endpoint (`/api/run/stream`) non protetto da API Key
- Nessun RBAC (role-based access control)

## Roadmap Tecnica

1. Protezione SSRF sugli endpoint webhook
2. Security headers (CSP, HSTS, X-Frame-Options)
3. Autenticazione su SSE endpoint
4. Integrazione SIEM/SOAR tramite connettori dedicati
5. RBAC e governance avanzata
6. GitHub Actions CI per test automatici

---

## Documentazione Correlata

- Italiano: `docs/technical-stakeholder-security.md`
- Italiano: `docs/executive-one-pager.md`
- English: `README.en.md`
- English: `docs/technical-stakeholder-security.en.md`
- English: `docs/executive-one-pager.en.md`
