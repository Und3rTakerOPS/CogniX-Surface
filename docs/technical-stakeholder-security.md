# Technical Brief - Security Stakeholders

## Scopo del Documento

Questo documento descrive il funzionamento tecnico del CogniX Surface per team Security, Risk, GRC e Data/ML engineering, con focus su:

- architettura e flussi dati
- logica di scoring e interpretazione
- requisiti non funzionali (sicurezza, privacy, compliance)
- gap tecnici attuali e piano di hardening

## Contesto e Threat Model

Il sistema affronta attacchi di social engineering che sfruttano pattern cognitivi ricorrenti nelle comunicazioni:

- urgenza artificiale
- leva autoritativa
- richiesta implicita di fiducia
- pressione emotiva/decisionale

### Obiettivo operativo

Ridurre il rischio umano identificando segnali ad alta priorita per:

- formazione mirata
- campagne awareness
- verifica manuale su comunicazioni ad alto rischio

### Non-obiettivo

- non e un sistema di valutazione personale o disciplinare
- non inferisce intenzioni individuali
- non sostituisce analisi umana nei casi critici

## Architettura Tecnica (Current State)

### Moduli principali

- `ingestion/loader.py`
  - carica record testuali con schema `user;text`
  - elimina record con valori null

- `analysis/nlp_engine.py`
  - usa `SentenceTransformer("all-MiniLM-L6-v2")`
  - produce embedding semantici per batch di testi

- `analysis/feature_engineering.py`
  - feature correnti:
    - `text_length`
    - `urgency_score` (regex su keyword urgenti)
    - `authority_score` (regex su ruoli/autorita)
    - `semantic_signal` (media vettore embedding)

- `model/risk_engine.py`
  - calcola `risk_score` lineare pesato
  - normalizza su massimo nel batch
  - ordina risultati per rischio decrescente

- `visualization/report.py`
  - rendering tabellare su console via `rich`

- `utils/logger.py`
  - logging console INFO + file DEBUG (`logs/tool.log`)

### Modulo presente ma non integrato

- `analysis/analyzer.py`
  - sentiment VADER
  - keyword set trust/urgency
  - puo estendere copertura feature nel main flow

## Data Flow

1. Input messaggi da sorgente strutturata (`;` separated)
2. Embedding semantico per ogni testo
3. Feature extraction linguistica + semantica
4. Risk scoring normalizzato
5. Report ordinato per priorita

### Formula correntemente in uso

$$
risk = 0.35 * urgency + 0.30 * authority + 0.20 * semantic\_signal + 0.15 * text\_length
$$

$$
risk\_norm = \frac{risk}{\max(risk)}
$$

## Valutazione Tecnica della Soluzione Attuale

### Punti forti

- pipeline semplice e tracciabile, adatta a PoC operativo
- pesi espliciti e facilmente auditabili
- componentizzazione chiara per evoluzione incrementale
- dipendenze consolidate open-source

### Limiti tecnici

- scoring lineare statico, non contestualizzato per dominio/team
- `semantic_signal` tramite media embedding puo perdere informazione
- regex keyword sensibili a varianti linguistiche
- normalizzazione batch-dependent (comparabilita cross-run limitata)
- explainability a livello per-record non ancora esplicitata
- controllo bias non implementato

## Security & Privacy Requirements

## Data Protection by Design

- minimizzazione: acquisire solo attributi necessari allo scopo
- pseudonimizzazione: sostituire `user` con identificativo tecnico ove possibile
- retention: definire tempi certi per input, output e log
- cifratura: data-at-rest e data-in-transit nei deployment enterprise

## Access Control

- RBAC su output/report per ruolo (SOC, GRC, Admin)
- segregazione ambienti (dev/test/prod)
- secret management esterno (no credenziali hardcoded)

## Auditability

- tracciamento run-id, versione codice, versione modello
- persistenza parametri di scoring usati per ogni run
- logging strutturato per incident response e forensics

## Compliance

- GDPR: finalita, minimizzazione, accountability
- policy HR/Security: divieto uso disciplinare diretto
- DPIA raccomandata in deployment reali ad ampia scala

## Metriche di Qualita e Performance

### Metriche ML/Security

- Precision@K sui casi top-risk
- Recall su benchmark etichettato
- F1-score globale e per segmento organizzativo
- false positive rate per canale/lingua/team

### Metriche operative

- tempo medio di analisi per batch
- throughput (messaggi/min)
- stabilita punteggio su finestre temporali
- tasso di casi ad alto rischio validati manualmente

## Hardening Roadmap (Prioritizzata)

1. Integrare `analysis/analyzer.py` nella pipeline principale.
2. Aggiungere explainability per fattori contributivi (top features per record).
3. Introdurre configurazione esterna per pesi/soglie con versioning.
4. Rendere comparabile il punteggio tra run (scaling globale o baseline storica).
5. Implementare evaluation framework su dataset etichettato.
6. Aggiungere test automatici e quality gates CI/CD.
7. Implementare monitoraggio drift e alert di anomalia.
8. Produrre dashboard persistente con drill-down (utente, team, periodo).

## Raccomandazioni di Deployment

- eseguire in ambiente isolato con accesso dati controllato
- usare file system cifrato o storage gestito con KMS
- separare pipeline analitica da layer di visualizzazione
- adottare release management con rollback e changelog modello

## Open Issues da Chiudere Prima della Produzione

- allineamento path dataset: `app/main.py` punta a `data/communications.txt`
- definizione schema dati ufficiale (campi obbligatori/opzionali)
- policy di retention e cancellazione dati approvata
- benchmark di accuratezza su casi reali validati

## Decisione Go/No-Go (Checklist Minima)

- test unitari e integrazione attivi
- metriche minime accettate da Security Governance
- controls privacy e audit implementati
- processo Human-in-the-loop formalizzato
- runbook incident e fallback documentati
