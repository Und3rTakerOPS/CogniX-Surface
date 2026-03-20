# Technical Brief - Security Stakeholders

## Document Purpose

This document provides a technical view of CogniX Surface for Security, Risk, GRC, and Data/ML stakeholders, with focus on:

- architecture and data flows
- scoring logic and interpretation
- non-functional requirements (security, privacy, compliance)
- current technical gaps and hardening roadmap

## Context and Threat Model

The system addresses social engineering patterns that exploit cognitive triggers in communications:

- artificial urgency
- authority pressure
- implicit trust requests
- emotional or decision pressure

### Operational objective

Reduce human-factor exposure by detecting high-priority signals for:

- targeted security training
- awareness campaign planning
- manual review of high-risk communications

### Non-objectives

- no disciplinary or personal evaluation use
- no intent inference at individual level
- no replacement of analyst judgment in critical cases

## Technical Architecture (Current State)

### Core modules

- `ingestion/loader.py`
  - loads text records with `user;text` schema
  - drops null records

- `analysis/nlp_engine.py`
  - uses `SentenceTransformer("all-MiniLM-L6-v2")`
  - generates semantic embeddings for text batches

- `analysis/feature_engineering.py`
  - current features:
    - `text_length`
    - `urgency_score` (regex over urgency keywords)
    - `authority_score` (regex over authority-role keywords)
    - `semantic_signal` (embedding mean)

- `model/risk_engine.py`
  - computes weighted linear `risk_score`
  - normalizes by batch maximum
  - sorts output in descending risk order

- `visualization/report.py`
  - console table rendering through `rich`

- `app/dashboard.py`
  - Streamlit interactive dashboard for metrics, top-risk table, and user-level view

- `utils/logger.py`
  - INFO console logging + DEBUG file logging (`logs/tool.log`)

### Available but not integrated yet

- `analysis/analyzer.py`
  - VADER sentiment analysis
  - trust/urgency keyword scoring
  - can enrich feature coverage in the main flow

## Data Flow

1. Input messages from structured source (`;` separated)
2. Semantic embedding generation
3. Linguistic and semantic feature extraction
4. Normalized risk scoring
5. Ranked reporting and dashboard visualization

### Current score formula

$$
risk = 0.35 * urgency + 0.30 * authority + 0.20 * semantic\_signal + 0.15 * text\_length
$$

$$
risk\_norm = \frac{risk}{\max(risk)}
$$

## Technical Assessment

### Strengths

- simple, traceable architecture suitable for controlled PoC
- explicit and auditable weighting logic
- clear modular decomposition for incremental improvement
- mature open-source dependency stack

### Current limitations

- static linear scoring not context-adaptive
- embedding mean can lose semantic granularity
- regex-based indicators are sensitive to linguistic variation
- batch-dependent normalization limits cross-run comparability
- limited per-record explainability
- no implemented bias-control workflow yet

## Security and Privacy Requirements

## Data Protection by Design

- minimization: ingest only purpose-required attributes
- pseudonymization: replace direct user IDs where possible
- retention: define strict retention/deletion windows for raw data, output, and logs
- encryption: protect data at rest and in transit in enterprise deployments

## Access Control

- RBAC for reports and dashboards by role (SOC, GRC, Admin)
- environment segregation (dev/test/prod)
- external secret management (no hardcoded credentials)

## Auditability

- track run-id, code version, and model version
- persist scoring parameters for each execution
- structured logging for incident response and forensics

## Compliance

- GDPR principles: purpose limitation, minimization, accountability
- HR/Security governance: no direct disciplinary usage
- DPIA recommended for broad production deployment

## Quality and Performance Metrics

### ML/Security metrics

- Precision@K on top-risk reviewed cases
- Recall on labeled benchmark datasets
- F1-score globally and by organizational segment
- false positive rate by channel/language/team

### Operational metrics

- average analysis latency per batch
- throughput (messages/min)
- score stability across time windows
- fraction of high-risk cases confirmed by human review

## Hardening Roadmap (Prioritized)

1. Integrate `analysis/analyzer.py` into the main pipeline.
2. Add per-record explainability (top feature contributions).
3. Externalize weights and thresholds with config versioning.
4. Improve cross-run score comparability (global scaling or historical baseline).
5. Implement evaluation framework with labeled datasets.
6. Add automated tests and CI/CD quality gates.
7. Implement drift monitoring and anomaly alerts.
8. Extend dashboard with trend and segment drill-down.

## Deployment Recommendations

- run in an isolated environment with controlled data access
- use encrypted storage or managed KMS-backed volumes
- separate analytics pipeline from visualization layer
- apply release management with rollback and model changelog

## Production Readiness Open Items

- dataset path and input contract must remain explicitly versioned
- formal data schema definition (required vs optional fields)
- approved retention and deletion policy
- validated accuracy benchmark on representative real cases

## Go/No-Go Checklist

- unit and integration tests active
- minimum target metrics approved by Security Governance
- privacy and audit controls implemented
- formal Human-in-the-loop process in place
- incident runbook and fallback strategy documented
