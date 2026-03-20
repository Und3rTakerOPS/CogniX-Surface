# FIRMA ELIAD - NON MODIFICABILE
"""CogniX Surface â€” FastAPI Dashboard (v2).

Single-page interactive dashboard backed by a JSON REST API.
Charts are generated server-side with Altair and rendered via Vega-Embed.
"""

from __future__ import annotations

import asyncio
import collections
import hmac
import html as _html
import io
import hashlib
import json
import math
import os
import sqlite3
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
load_dotenv()

import altair as alt
import numpy as np
import pandas as pd
from fastapi import Depends, FastAPI, HTTPException, Request, Security
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import APIKeyHeader
from fastapi.responses import FileResponse, HTMLResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from ingestion.loader import DataLoader
from analysis.nlp_engine import NLPEngine
from analysis.analyzer import TextAnalyzer
from analysis.feature_engineering import FeatureEngineer
from analysis.constants import (
    RISK_BAND_BINS,
    RISK_BAND_LABELS,
    RISK_BAND_COLORS,
)
from model.risk_engine import RiskEngine, DEFAULT_WEIGHTS
from app.database import (
    init_db as _init_db,
    save_triage_item as _db_save_triage_item,
    save_triage_items_bulk as _db_save_triage_items_bulk,
    load_triage_items as _db_load_triage_items,
    save_filter_preset as _db_save_preset,
    load_filter_presets as _db_load_presets,
    delete_filter_preset as _db_delete_preset,
    save_kpi_snapshot as _db_save_kpi_snapshot,
    load_kpi_timeline as _db_load_kpi_timeline,
    save_audit_entry as _db_save_audit,
)

# â”€â”€ Config â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

DEFAULT_DATASET = PROJECT_ROOT / "datacommunications.txt.txt"
DEFAULT_WEIGHTS_PATH = PROJECT_ROOT / "config" / "risk_weights.json"
ALLOWED_DATASET_ROOTS = [PROJECT_ROOT]
ALLOWED_WEIGHTS_ROOTS = [PROJECT_ROOT / "config"]

FEATURE_LABELS: dict[str, str] = {
    "urgency_score": "Urgency",
    "authority_score": "Authority",
    "semantic_signal": "Semantic",
    "text_length_signal": "Text Length",
    "sentiment_risk_signal": "Sentiment",
    "trust_score": "Trust",
    "social_proof_score": "Social Proof",
    "reciprocity_score": "Reciprocity",
    "commitment_score": "Commitment",
    "liking_score": "Liking",
    "fear_score": "Fear",
}

FEATURE_PALETTE = [
    "#4e79a7", "#f28e2b", "#e15759", "#76b7b2", "#59a14f",
    "#edc948", "#b07aa1", "#ff9da7", "#9c755f", "#bab0ac", "#af7aa1",
]

FEATURE_COLUMNS = list(FEATURE_LABELS.keys())

RESULTS_CACHE_MAX_SIZE: int = 128

WEBHOOK_HMAC_SECRET: str = os.environ.get("COGNIX_WEBHOOK_SECRET", "")
COGNIX_API_KEY: str = os.environ.get("COGNIX_API_KEY", "")
COGNIX_DB_PATH: str = os.environ.get("COGNIX_DB_PATH", str(PROJECT_ROOT / "data" / "cognix.db"))
COGNIX_CORS_ORIGINS: list[str] = [
    o.strip() for o in os.environ.get("COGNIX_CORS_ORIGINS", "*").split(",") if o.strip()
]
COGNIX_RATE_LIMIT: str = os.environ.get("COGNIX_RATE_LIMIT", "120/minute")

# ── API Key authentication ───────────────────────────────────────────────────
_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


async def _require_api_key(api_key: str | None = Security(_api_key_header)):
    """Return immediately if no key is configured (dev mode), else verify."""
    if not COGNIX_API_KEY:
        return
    if not api_key or not hmac.compare_digest(api_key, COGNIX_API_KEY):
        raise HTTPException(status_code=401, detail="Invalid or missing API key")


# â”€â”€ App & state â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

limiter = Limiter(key_func=get_remote_address, default_limits=[COGNIX_RATE_LIMIT])

app = FastAPI(
    title="CogniX Surface",
    version="2.0.0",
    description=(
        "Dashboard interattiva per l'analisi del rischio di social engineering. "
        "Pipeline NLP + scoring con triage operativo, webhook alerting e export multi-formato."
    ),
    docs_url="/docs",
    redoc_url="/redoc",
)

app.state.limiter = limiter


@app.exception_handler(RateLimitExceeded)
async def _rate_limit_handler(request: Request, exc: RateLimitExceeded):
    return Response(
        content=json.dumps({"detail": f"Rate limit superato: {exc.detail}"}),
        status_code=429,
        media_type="application/json",
    )


app.add_middleware(
    CORSMiddleware,
    allow_origins=COGNIX_CORS_ORIGINS,
    allow_credentials=False,
    allow_methods=["GET", "POST", "PATCH", "OPTIONS"],
    allow_headers=["*"],
    expose_headers=["X-RateLimit-Limit", "X-RateLimit-Remaining", "X-RateLimit-Reset"],
)

_templates_dir = Path(__file__).resolve().parent / "templates"
_static_dir = Path(__file__).resolve().parent / "static"
_static_dir.mkdir(exist_ok=True)
templates = Jinja2Templates(directory=str(_templates_dir))
app.mount("/static", StaticFiles(directory=str(_static_dir)), name="static")

_lock = threading.Lock()
_nlp_engine: NLPEngine | None = None
_results: pd.DataFrame = pd.DataFrame()
_featured_df: pd.DataFrame = pd.DataFrame()
_dataset_path: str = str(DEFAULT_DATASET)
_weights_path: str = str(DEFAULT_WEIGHTS_PATH)
_loaded_weights: dict[str, float] = {}
_results_cache: collections.OrderedDict[str, dict[str, Any]] = collections.OrderedDict()
_results_version: int = 0
_results_cache_hits: int = 0
_results_cache_misses: int = 0
_triage_items: dict[str, dict[str, Any]] = {}
_triage_version: int = 0
_filter_presets: dict[str, dict[str, Any]] = {}
_kpi_timeline: list[dict[str, Any]] = []
KPI_TIMELINE_MAX_SNAPSHOTS: int = 200

# ── SQLite persistence ──────────────────────────────────────────────────────
_init_db(COGNIX_DB_PATH)
_triage_items = _db_load_triage_items()
_filter_presets = _db_load_presets()
_kpi_timeline = _db_load_kpi_timeline(KPI_TIMELINE_MAX_SNAPSHOTS)

TRIAGE_ALLOWED_STATUSES = {"new", "in_progress", "mitigated", "false_positive"}
TRIAGE_STATUS_ORDER = {"new": 0, "in_progress": 1, "mitigated": 2, "false_positive": 3}
TRIAGE_ALLOWED_PRIORITIES = {"P1", "P2", "P3"}
TRIAGE_RISK_MIN = 0.70
TRIAGE_MAX_ITEMS = 250

TRIAGE_SLA_HOURS = {
    "P1": 4,
    "P2": 12,
    "P3": 24,
}


@app.get("/favicon.ico", include_in_schema=False)
async def favicon() -> Response:
    """Serve favicon if available, otherwise return empty 204 to avoid 404 noise."""
    ico_path = _static_dir / "favicon.ico"
    if ico_path.exists():
        return FileResponse(str(ico_path))
    return Response(status_code=204)


def _get_nlp_engine() -> NLPEngine:
    global _nlp_engine
    if _nlp_engine is None:
        with _lock:
            if _nlp_engine is None:  # double-check after acquiring lock
                _nlp_engine = NLPEngine()
    return _nlp_engine


# â”€â”€ Helpers â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def validate_path_in_allowed_roots(path_str: str, allowed_roots: list) -> Path:
    candidate = Path(path_str).expanduser().resolve(strict=False)
    if not candidate.exists():
        raise ValueError(f"Path does not exist: {candidate}")
    candidate = candidate.resolve(strict=True)
    for root in allowed_roots:
        root_resolved = Path(root).resolve(strict=True)
        try:
            candidate.relative_to(root_resolved)
            return candidate
        except ValueError:
            continue
    allowed_display = ", ".join(str(Path(r).resolve(strict=False)) for r in allowed_roots)
    raise ValueError(f"Path not allowed. Allowed roots: {allowed_display}")


def add_risk_band(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["risk_band"] = pd.cut(
        out["risk_score"],
        bins=RISK_BAND_BINS,
        labels=RISK_BAND_LABELS,
        include_lowest=True,
        right=False,
    )
    return out


def _apply_filters(
    df: pd.DataFrame,
    min_risk: float = 0.0,
    max_risk: float = 1.0,
    bands: list[str] | None = None,
    drivers: list[str] | None = None,
    text_query: str = "",
    users: list[str] | None = None,
) -> pd.DataFrame:
    out = df.copy()
    out = out[(out["risk_score"] >= min_risk) & (out["risk_score"] <= max_risk)]
    if bands:
        out = out[out["risk_band"].isin(bands)]
    if drivers:
        out = out[out["top_risk_driver"].isin(drivers)]
    if users:
        out = out[out["user"].isin(users)]
    if text_query.strip():
        out = out[out["text"].str.contains(text_query, case=False, na=False, regex=False)]
    return out


def _safe_json(chart: alt.TopLevelMixin) -> dict:
    return chart.to_dict()


def _build_detail_card(row: pd.Series, contrib_cols: list[str]) -> dict:
    band = str(row.get("risk_band", "?"))
    contribs = {}
    if contrib_cols:
        contribs = {
            FEATURE_LABELS.get(c.replace("contrib_", ""), c): round(float(row[c]), 4)
            for c in contrib_cols
        }
    return {
        "user": str(row["user"]),
        "text": str(row["text"]),
        "risk_score": round(float(row["risk_score"]), 4),
        "risk_band": band,
        "band_color": RISK_BAND_COLORS.get(band, "#888"),
        "top_driver": FEATURE_LABELS.get(
            str(row.get("top_risk_driver", "")),
            str(row.get("top_risk_driver", "")),
        ),
        "contributions": contribs,
    }


def _triage_message_id(user: str, text: str) -> str:
    raw = f"{user}\n{text}".encode("utf-8", errors="ignore")
    return hashlib.sha1(raw).hexdigest()[:16]


def _sync_triage_from_results(df: pd.DataFrame, min_risk: float = TRIAGE_RISK_MIN, top_n: int = TRIAGE_MAX_ITEMS) -> int:
    global _triage_items, _triage_version

    if df.empty:
        return 0

    now_iso = datetime.now(timezone.utc).isoformat()
    candidates = (
        df[df["risk_score"] >= min_risk]
        .sort_values("risk_score", ascending=False)
        .head(max(1, int(top_n)))
    )

    active_ids: set[str] = set()
    for _, row in candidates.iterrows():
        user = str(row.get("user", ""))
        text = str(row.get("text", ""))
        triage_id = _triage_message_id(user, text)
        active_ids.add(triage_id)

        existing = _triage_items.get(triage_id)
        base = {
            "id": triage_id,
            "user": user,
            "text": text,
            "risk_score": round(float(row.get("risk_score", 0.0)), 4),
            "risk_band": str(row.get("risk_band", "")),
            "top_driver": FEATURE_LABELS.get(str(row.get("top_risk_driver", "")), str(row.get("top_risk_driver", ""))),
            "present_in_latest_run": True,
            "updated_at": now_iso,
        }
        if existing:
            existing.update(base)
        else:
            _triage_items[triage_id] = {
                **base,
                "status": "new",
                "assignee": "",
                "notes": [],
                "activity": [
                    {"time": now_iso, "action": "created", "details": "Inserito automaticamente dal run"}
                ],
                "created_at": now_iso,
            }

    for triage_id, item in _triage_items.items():
        item["present_in_latest_run"] = triage_id in active_ids

    _triage_version += 1
    _db_save_triage_items_bulk(_triage_items)
    return len(active_ids)


def _triage_priority_from_risk(risk_score: float) -> str:
    if risk_score >= 0.90:
        return "P1"
    if risk_score >= 0.80:
        return "P2"
    return "P3"


def _triage_deadline_info(item: dict[str, Any], now_dt: datetime) -> dict[str, Any]:
    status = str(item.get("status", "new"))
    risk = float(item.get("risk_score", 0.0))
    priority = _triage_priority_from_risk(risk)

    if status not in {"new", "in_progress"}:
        return {
            "priority": priority,
            "sla_due_at": None,
            "sla_breached": False,
        }

    start_iso = str(item.get("updated_at") or item.get("created_at") or "")
    try:
        start_dt = datetime.fromisoformat(start_iso.replace("Z", "+00:00"))
    except ValueError:
        start_dt = now_dt
    if start_dt.tzinfo is None:
        start_dt = start_dt.replace(tzinfo=timezone.utc)

    due_dt = start_dt + pd.Timedelta(hours=TRIAGE_SLA_HOURS[priority])
    return {
        "priority": priority,
        "sla_due_at": due_dt.isoformat(),
        "sla_breached": now_dt > due_dt,
    }


# â”€â”€ Pydantic models â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def _sanitize(value: str) -> str:
    """Escape HTML entities to prevent XSS in reflected outputs."""
    return _html.escape(value, quote=True)


class RunRequest(BaseModel):
    dataset_path: str = Field(str(DEFAULT_DATASET), max_length=512)
    weights_path: str = Field(str(DEFAULT_WEIGHTS_PATH), max_length=512)


class FilterParams(BaseModel):
    min_risk: float = Field(0.0, ge=0.0, le=1.0)
    max_risk: float = Field(1.0, ge=0.0, le=1.0)
    bands: list[str] | None = None
    drivers: list[str] | None = None
    users: list[str] | None = None
    text_query: str = Field("", max_length=512)
    top_n: int = Field(25, ge=1, le=1000)
    offset: int = Field(0, ge=0)
    limit: int = Field(100, ge=1, le=500)


class WeightsUpdateRequest(BaseModel):
    weights: dict[str, float]


class AlertWebhookRequest(BaseModel):
    webhook_url: str = Field(..., min_length=8, max_length=2048)
    event: str = Field("high_risk_alert", min_length=1, max_length=128)
    payload: dict[str, Any] = Field(default_factory=dict)


class TriageListParams(BaseModel):
    statuses: list[str] | None = None
    priorities: list[str] | None = None
    assignee: str = Field("", max_length=128)
    text_query: str = Field("", max_length=512)
    min_risk: float = Field(0.0, ge=0.0, le=1.0)
    only_latest: bool = True
    top_n: int = Field(100, ge=1, le=1000)


class TriageUpdateRequest(BaseModel):
    status: str | None = None
    assignee: str | None = Field(default=None, max_length=128)
    note: str | None = Field(default=None, max_length=2000)


class TriageSyncRequest(BaseModel):
    min_risk: float = Field(TRIAGE_RISK_MIN, ge=0.0, le=1.0)
    top_n: int = Field(TRIAGE_MAX_ITEMS, ge=1, le=1000)


def _make_results_cache_key(params: FilterParams, version: int) -> str:
    payload = {
        "version": version,
        "min_risk": round(params.min_risk, 4),
        "max_risk": round(params.max_risk, 4),
        "bands": sorted(params.bands or []),
        "drivers": sorted(params.drivers or []),
        "users": sorted(params.users or []),
        "text_query": params.text_query.strip().lower(),
        "top_n": params.top_n,
    }
    return json.dumps(payload, sort_keys=True)


def _system_status() -> dict[str, Any]:
    open_count = sum(1 for i in _triage_items.values() if i.get("status") in {"new", "in_progress"})
    return {
        "dataset_path": _dataset_path,
        "weights_path": _weights_path,
        "cache_entries": len(_results_cache),
        "cache_hits": _results_cache_hits,
        "cache_misses": _results_cache_misses,
        "results_version": _results_version,
        "triage_items": len(_triage_items),
        "triage_open": open_count,
        "triage_version": _triage_version,
    }


def _save_kpi_snapshot(df: pd.DataFrame, duration_ms: int) -> None:
    """Append a KPI snapshot from the current results to the timeline."""
    if df.empty:
        return
    snapshot = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "run_version": _results_version,
        "duration_ms": duration_ms,
        "messages": int(len(df)),
        "users": int(df["user"].nunique()),
        "avg_risk": round(float(df["risk_score"].mean()), 4),
        "max_risk": round(float(df["risk_score"].max()), 4),
        "median_risk": round(float(df["risk_score"].median()), 4),
        "high": int((df["risk_band"] == "High").sum()),
        "medium": int((df["risk_band"] == "Medium").sum()),
        "low": int((df["risk_band"] == "Low").sum()),
        "high_pct": round((df["risk_band"] == "High").mean() * 100, 1),
    }
    _kpi_timeline.append(snapshot)
    while len(_kpi_timeline) > KPI_TIMELINE_MAX_SNAPSHOTS:
        _kpi_timeline.pop(0)
    _db_save_kpi_snapshot(snapshot)


# â”€â”€ Chart builders â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def _chart_histogram(df: pd.DataFrame) -> dict:
    bars = (
        alt.Chart(df)
        .mark_bar(cornerRadiusTopLeft=6, cornerRadiusTopRight=6, opacity=0.85)
        .encode(
            x=alt.X("risk_score:Q", bin=alt.Bin(maxbins=20), title="Punteggio di Rischio",
                    axis=alt.Axis(format=".1f", grid=False)),
            y=alt.Y("count():Q", title="Messaggi", axis=alt.Axis(grid=True, gridDash=[3, 3], gridOpacity=0.3)),
            color=alt.Color(
                "risk_band:N",
                scale=alt.Scale(
                    domain=list(RISK_BAND_COLORS.keys()),
                    range=list(RISK_BAND_COLORS.values()),
                ),
                legend=alt.Legend(title="Fascia", orient="top-right",
                                  labelFont="Inter", titleFont="Inter"),
            ),
            tooltip=[
                alt.Tooltip("risk_score:Q", bin=alt.Bin(maxbins=20), title="Intervallo"),
                alt.Tooltip("count():Q", title="Conteggio"),
                alt.Tooltip("risk_band:N", title="Fascia"),
            ],
        )
    )

    # KDE density line overlay
    density = (
        alt.Chart(df)
        .transform_density("risk_score", as_=["risk_score", "density"], extent=[0, 1])
        .mark_area(opacity=0.12, color="#4e79a7", line={"color": "#4e79a7", "strokeWidth": 2})
        .encode(
            x=alt.X("risk_score:Q"),
            y=alt.Y("density:Q", title=""),
        )
    )

    # Median rule
    median_val = float(df["risk_score"].median())
    median_rule = (
        alt.Chart(pd.DataFrame({"median": [median_val]}))
        .mark_rule(color="#e15759", strokeDash=[6, 4], strokeWidth=2)
        .encode(
            x="median:Q",
            tooltip=[alt.Tooltip("median:Q", title="Mediana", format=".3f")],
        )
    )

    # Threshold lines at 0.4 (Medium) and 0.7 (High)
    thresholds = pd.DataFrame([
        {"soglia": 0.4, "band": "Med/Low"},
        {"soglia": 0.7, "band": "High/Med"},
    ])
    threshold_rules = (
        alt.Chart(thresholds)
        .mark_rule(strokeDash=[4, 3], strokeWidth=1.5, opacity=0.7)
        .encode(
            x=alt.X("soglia:Q"),
            color=alt.Color(
                "band:N",
                scale=alt.Scale(domain=["Med/Low", "High/Med"], range=["#f28e2b", "#e15759"]),
                legend=alt.Legend(title="Soglie", orient="top-left",
                                  labelFont="Inter", titleFont="Inter"),
            ),
            tooltip=[alt.Tooltip("soglia:Q", title="Soglia"), alt.Tooltip("band:N", title="Fascia")],
        )
    )

    chart = (
        alt.layer(bars, density, median_rule, threshold_rules)
        .resolve_scale(y="independent")
        .properties(width="container", height=340,
                    title=alt.Title("Distribuzione Punteggio di Rischio",
                                    subtitle=f"Mediana: {median_val:.3f}  Â·  Soglie: 0.40 (Medio) | 0.70 (Alto)",
                                    font="Inter", subtitleFont="Inter"))
        .configure_view(strokeWidth=0)
    )
    return _safe_json(chart)


def _chart_donut(df: pd.DataFrame) -> dict:
    band_counts = (
        df.groupby("risk_band", as_index=False, observed=False)
        .size()
        .rename(columns={"size": "count"})
    )
    total = int(band_counts["count"].sum())
    band_counts["pct"] = (band_counts["count"] / max(total, 1) * 100).round(1)
    band_counts["label"] = band_counts.apply(
        lambda r: f"{r['risk_band']}  {r['pct']}%", axis=1
    )

    arcs = (
        alt.Chart(band_counts)
        .mark_arc(innerRadius=65, outerRadius=115, stroke="#fff", strokeWidth=2.5,
                  cornerRadius=4)
        .encode(
            theta=alt.Theta("count:Q", stack=True),
            color=alt.Color(
                "risk_band:N",
                scale=alt.Scale(
                    domain=list(RISK_BAND_COLORS.keys()),
                    range=list(RISK_BAND_COLORS.values()),
                ),
                legend=alt.Legend(title="Band", labelFont="Inter", titleFont="Inter",
                                  orient="right", direction="vertical"),
            ),
            tooltip=[
                alt.Tooltip("risk_band:N", title="Band"),
                alt.Tooltip("count:Q", title="Count"),
                alt.Tooltip("pct:Q", title="%", format=".1f"),
            ],
        )
    )

    # Percentage labels on arcs
    text = (
        alt.Chart(band_counts)
        .mark_text(radiusOffset=20, font="Inter", fontSize=12, fontWeight="bold")
        .encode(
            theta=alt.Theta("count:Q", stack=True),
            radius=alt.value(90),
            text=alt.Text("label:N"),
            color=alt.value("#333"),
        )
    )

    # Center total text
    center = (
        alt.Chart(pd.DataFrame({"text": [str(total)]}))
        .mark_text(font="Inter", fontSize=28, fontWeight=800, color="#4e79a7")
        .encode(text="text:N")
    )
    center_sub = (
        alt.Chart(pd.DataFrame({"text": ["messages"]}))
        .mark_text(font="Inter", fontSize=11, color="#999", dy=22)
        .encode(text="text:N")
    )

    chart = (
        alt.layer(arcs, text, center, center_sub)
        .properties(width="container", height=340,
                    title=alt.Title("Risk Band Breakdown", font="Inter"))
        .configure_view(strokeWidth=0)
    )
    return _safe_json(chart)


def _chart_driver_bar(df: pd.DataFrame) -> dict:
    data = (
        df.groupby("top_risk_driver", as_index=False)
        .size()
        .rename(columns={"size": "count"})
        .sort_values("count", ascending=False)
    )
    data["label"] = data["top_risk_driver"].map(FEATURE_LABELS).fillna(data["top_risk_driver"])
    total = int(data["count"].sum())
    data["pct"] = (data["count"] / max(total, 1) * 100).round(1)

    bars = (
        alt.Chart(data)
        .mark_bar(cornerRadiusTopLeft=6, cornerRadiusTopRight=6, opacity=0.88)
        .encode(
            x=alt.X("label:N", sort="-y", title=None, axis=alt.Axis(labelAngle=-35, labelFont="Inter")),
            y=alt.Y("count:Q", title="Messaggi", axis=alt.Axis(grid=True, gridDash=[3, 3], gridOpacity=0.3)),
            color=alt.Color("label:N", scale=alt.Scale(range=FEATURE_PALETTE), legend=None),
            tooltip=[alt.Tooltip("label:N", title="Driver"),
                     alt.Tooltip("count:Q", title="Conteggio"),
                     alt.Tooltip("pct:Q", title="%", format=".1f")],
        )
    )

    # Value labels on top of bars
    text = (
        alt.Chart(data)
        .mark_text(dy=-10, font="Inter", fontSize=11, fontWeight="bold", color="#555")
        .encode(
            x=alt.X("label:N", sort="-y"),
            y=alt.Y("count:Q"),
            text=alt.Text("count:Q"),
        )
    )

    chart = (
        alt.layer(bars, text)
        .properties(width="container", height=320,
                    title=alt.Title("Principali Driver di Rischio per Messaggio", font="Inter"))
        .configure_view(strokeWidth=0)
    )
    return _safe_json(chart)


def _chart_heatmap(df: pd.DataFrame) -> dict | None:
    contrib_cols = [c for c in df.columns if c.startswith("contrib_")]
    if not contrib_cols:
        return None
    top_rows = df.sort_values("risk_score", ascending=False).head(15)
    heat_data = top_rows[["user"] + contrib_cols].copy()
    heat_data = heat_data.set_index("user")
    heat_data.columns = [FEATURE_LABELS.get(c.replace("contrib_", ""), c) for c in heat_data.columns]
    melted = heat_data.reset_index().melt(id_vars="user", var_name="Feature", value_name="Contribution")
    chart = (
        alt.Chart(melted)
        .mark_rect(cornerRadius=4, stroke="#fff", strokeWidth=0.5)
        .encode(
            x=alt.X("Feature:N", title=None, axis=alt.Axis(labelAngle=-45, labelFont="Inter")),
            y=alt.Y("user:N", title=None, sort=top_rows["user"].tolist(),
                    axis=alt.Axis(labelFont="Inter")),
            color=alt.Color("Contribution:Q",
                            scale=alt.Scale(scheme="orangered", domainMin=0),
                            legend=alt.Legend(title="Contrib", gradientLength=140,
                                              labelFont="Inter", titleFont="Inter")),
            tooltip=[
                alt.Tooltip("user:N", title="Utente"),
                alt.Tooltip("Feature:N", title="Feature"),
                alt.Tooltip("Contribution:Q", title="Contributo", format=".4f"),
            ],
        )
        .properties(width="container", height=max(260, 24 * min(len(top_rows), 15)),
                     title=alt.Title("Contributi Feature â€” Top 15 Messaggi piÃ¹ Rischiosi", font="Inter",
                                     subtitle="Saturazione elevata = contributo maggiore",
                                     subtitleFont="Inter"))
        .configure_view(strokeWidth=0)
    )
    return _safe_json(chart)


def _chart_user_scatter(df: pd.DataFrame) -> dict:
    by_user = df.groupby("user", as_index=False).agg(
        avg_risk=("risk_score", "mean"),
        messages=("risk_score", "count"),
        max_risk=("risk_score", "max"),
    )

    # Threshold bands as background
    bands_df = pd.DataFrame([
        {"y": 0.0, "y2": 0.4, "band": "Low"},
        {"y": 0.4, "y2": 0.7, "band": "Medium"},
        {"y": 0.7, "y2": 1.0, "band": "High"},
    ])
    bg = (
        alt.Chart(bands_df)
        .mark_rect(opacity=0.06)
        .encode(
            y=alt.Y("y:Q"), y2=alt.Y2("y2:Q"),
            color=alt.Color("band:N",
                            scale=alt.Scale(domain=["Low", "Medium", "High"],
                                            range=["#59a14f", "#f28e2b", "#e15759"]),
                            legend=None),
        )
    )

    circles = (
        alt.Chart(by_user)
        .mark_circle(opacity=0.8, stroke="#fff", strokeWidth=1)
        .encode(
            x=alt.X("messages:Q", title="Numero di Messaggi",
                    axis=alt.Axis(grid=True, gridDash=[3, 3], gridOpacity=0.3)),
            y=alt.Y("avg_risk:Q", title="Rischio Medio",
                    scale=alt.Scale(domain=[0, 1]),
                    axis=alt.Axis(grid=True, gridDash=[3, 3], gridOpacity=0.3)),
            size=alt.Size("max_risk:Q", title="Rischio Max", scale=alt.Scale(range=[50, 600]),
                          legend=alt.Legend(labelFont="Inter", titleFont="Inter")),
            color=alt.Color("avg_risk:Q", scale=alt.Scale(scheme="redyellowgreen", reverse=True),
                            legend=alt.Legend(title="Rischio Medio", labelFont="Inter", titleFont="Inter")),
            tooltip=[
                alt.Tooltip("user:N", title="Utente"),
                alt.Tooltip("avg_risk:Q", title="Rischio Medio", format=".3f"),
                alt.Tooltip("max_risk:Q", title="Rischio Max", format=".3f"),
                alt.Tooltip("messages:Q", title="Messaggi"),
            ],
        )
    )

    # User name labels for high-risk users
    labels = (
        alt.Chart(by_user[by_user["avg_risk"] >= 0.5])
        .mark_text(dy=-12, font="Inter", fontSize=10, fontWeight=600, color="#444")
        .encode(
            x=alt.X("messages:Q"),
            y=alt.Y("avg_risk:Q"),
            text="user:N",
        )
    )

    chart = (
        alt.layer(bg, circles, labels)
        .properties(width="container", height=370,
                    title=alt.Title("Panoramica Rischio Utenti", font="Inter",
                                    subtitle="Volume vs. rischio â€” bolla piÃ¹ grande = rischio max maggiore",
                                    subtitleFont="Inter"))
        .configure_view(strokeWidth=0)
    )
    return _safe_json(chart)


def _chart_correlation(df: pd.DataFrame) -> dict | None:
    feat_cols = [c for c in FEATURE_COLUMNS if c in df.columns]
    if len(feat_cols) < 2:
        return None
    corr = df[feat_cols].corr()
    renamed = {c: FEATURE_LABELS.get(c, c) for c in feat_cols}
    corr = corr.rename(columns=renamed, index=renamed)
    melted = corr.reset_index().melt(id_vars="index", var_name="Feature B", value_name="Correlation")
    melted = melted.rename(columns={"index": "Feature A"})
    melted["abs_corr"] = melted["Correlation"].abs()

    rects = (
        alt.Chart(melted)
        .mark_rect(cornerRadius=4, stroke="#fff", strokeWidth=0.5)
        .encode(
            x=alt.X("Feature A:N", title=None, axis=alt.Axis(labelAngle=-45, labelFont="Inter")),
            y=alt.Y("Feature B:N", title=None, axis=alt.Axis(labelFont="Inter")),
            color=alt.Color("Correlation:Q", scale=alt.Scale(scheme="redblue", domain=[-1, 1]),
                            legend=alt.Legend(title="r", labelFont="Inter", titleFont="Inter",
                                              gradientLength=160)),
            tooltip=[alt.Tooltip("Feature A:N"), alt.Tooltip("Feature B:N"),
                     alt.Tooltip("Correlation:Q", title="Correlazione", format=".3f")],
        )
    )

    # Correlation value text for significant values
    text = (
        alt.Chart(melted[melted["abs_corr"] >= 0.3])
        .mark_text(font="Inter", fontSize=9, fontWeight=600)
        .encode(
            x=alt.X("Feature A:N"),
            y=alt.Y("Feature B:N"),
            text=alt.Text("Correlation:Q", format=".2f"),
            color=alt.condition(
                alt.datum.abs_corr > 0.6,
                alt.value("#fff"),
                alt.value("#333")
            ),
        )
    )

    chart = (
        alt.layer(rects, text)
        .properties(width="container", height=400,
                    title=alt.Title("Matrice di Correlazione Feature", font="Inter",
                                    subtitle="Valori mostrati per |r| \u2265 0.30",
                                    subtitleFont="Inter"))
        .configure_view(strokeWidth=0)
    )
    return _safe_json(chart)


def _chart_boxplot(df: pd.DataFrame) -> dict | None:
    if "user" not in df.columns:
        return None
    top_users = df.groupby("user")["risk_score"].mean().nlargest(12).index.tolist()
    subset = df[df["user"].isin(top_users)]

    # Mean markers
    means = subset.groupby("user", as_index=False)["risk_score"].mean()

    box = (
        alt.Chart(subset)
        .mark_boxplot(extent="min-max", size=24, outliers={"size": 8})
        .encode(
            x=alt.X("user:N", sort=top_users, title=None,
                    axis=alt.Axis(labelAngle=-35, labelFont="Inter")),
            y=alt.Y("risk_score:Q", title="Punteggio di Rischio",
                    scale=alt.Scale(domain=[0, 1]),
                    axis=alt.Axis(grid=True, gridDash=[3, 3], gridOpacity=0.3)),
            color=alt.Color("user:N", legend=None,
                            scale=alt.Scale(range=FEATURE_PALETTE)),
        )
    )

    mean_pts = (
        alt.Chart(means)
        .mark_point(shape="diamond", size=60, filled=True, color="#e15759", opacity=0.9)
        .encode(
            x=alt.X("user:N", sort=top_users),
            y=alt.Y("risk_score:Q"),
            tooltip=[alt.Tooltip("user:N", title="Utente"),
                     alt.Tooltip("risk_score:Q", title="Media", format=".3f")],
        )
    )

    chart = (
        alt.layer(box, mean_pts)
        .properties(width="container", height=340,
                    title=alt.Title("Distribuzione Rischio â€” Top 12 Utenti", font="Inter",
                                    subtitle="Box = IQR \u00b7 Diamante = media", subtitleFont="Inter"))
        .configure_view(strokeWidth=0)
    )
    return _safe_json(chart)


def _chart_weights() -> dict | None:
    weights = _loaded_weights or DEFAULT_WEIGHTS
    sorted_items = sorted(weights.items(), key=lambda x: x[1], reverse=True)
    data = pd.DataFrame([
        {"feature": FEATURE_LABELS.get(k, k), "weight": v,
         "pct": round(v / max(sum(weights.values()), 1e-9) * 100, 1)}
        for k, v in sorted_items
    ])

    # Horizontal lollipop chart
    bars = (
        alt.Chart(data)
        .mark_bar(height=8, cornerRadiusEnd=4, opacity=0.7, color="#4e79a7")
        .encode(
            y=alt.Y("feature:N", sort=[FEATURE_LABELS.get(k, k) for k, _ in sorted_items],
                    title=None, axis=alt.Axis(labelFont="Inter", labelFontSize=11)),
            x=alt.X("weight:Q", title="Peso",
                    scale=alt.Scale(domain=[0, max(0.25, data["weight"].max() * 1.2)]),
                    axis=alt.Axis(grid=True, gridDash=[3, 3], gridOpacity=0.3)),
            tooltip=[alt.Tooltip("feature:N", title="Feature"),
                     alt.Tooltip("weight:Q", title="Peso", format=".3f"),
                     alt.Tooltip("pct:Q", title="% del totale", format=".1f")],
        )
    )

    points = (
        alt.Chart(data)
        .mark_circle(size=65, color="#4e79a7", opacity=0.95)
        .encode(
            y=alt.Y("feature:N", sort=[FEATURE_LABELS.get(k, k) for k, _ in sorted_items]),
            x=alt.X("weight:Q"),
        )
    )

    text = (
        alt.Chart(data)
        .mark_text(dx=18, font="Inter", fontSize=10, fontWeight=600, color="#555")
        .encode(
            y=alt.Y("feature:N", sort=[FEATURE_LABELS.get(k, k) for k, _ in sorted_items]),
            x=alt.X("weight:Q"),
            text=alt.Text("weight:Q", format=".3f"),
        )
    )

    chart = (
        alt.layer(bars, points, text)
        .properties(width="container", height=320,
                    title=alt.Title("Configurazione Pesi di Rischio", font="Inter",
                                    subtitle="Lollipop â€” ordinato per peso", subtitleFont="Inter"))
        .configure_view(strokeWidth=0)
    )
    return _safe_json(chart)


def _chart_feature_avg(df: pd.DataFrame) -> dict | None:
    feat_cols = [c for c in FEATURE_COLUMNS if c in df.columns]
    if not feat_cols:
        return None
    means = pd.DataFrame([
        {"feature": FEATURE_LABELS.get(c, c), "mean_score": round(float(df[c].mean()), 4)}
        for c in feat_cols
    ]).sort_values("mean_score", ascending=False)

    bars = (
        alt.Chart(means)
        .mark_bar(cornerRadiusTopLeft=6, cornerRadiusTopRight=6, opacity=0.85)
        .encode(
            x=alt.X("feature:N", sort="-y", title=None, axis=alt.Axis(labelAngle=-35, labelFont="Inter")),
            y=alt.Y("mean_score:Q", title="Punteggio Medio",
                    axis=alt.Axis(grid=True, gridDash=[3, 3], gridOpacity=0.3)),
            color=alt.Color("feature:N", scale=alt.Scale(range=FEATURE_PALETTE), legend=None),
            tooltip=[alt.Tooltip("feature:N", title="Feature"),
                     alt.Tooltip("mean_score:Q", title="Media", format=".4f")],
        )
    )

    text = (
        alt.Chart(means)
        .mark_text(dy=-10, font="Inter", fontSize=10, fontWeight=600, color="#555")
        .encode(
            x=alt.X("feature:N", sort="-y"),
            y=alt.Y("mean_score:Q"),
            text=alt.Text("mean_score:Q", format=".3f"),
        )
    )

    chart = (
        alt.layer(bars, text)
        .properties(width="container", height=300,
                    title=alt.Title("Punteggi Medi delle Feature", font="Inter",
                                    subtitle="Media su tutti i messaggi analizzati", subtitleFont="Inter"))
        .configure_view(strokeWidth=0)
    )
    return _safe_json(chart)


# â”€â”€ Routes â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "default_dataset": str(DEFAULT_DATASET),
        "default_weights": str(DEFAULT_WEIGHTS_PATH),
    })


@app.get("/api/run/stream", tags=["Pipeline"], summary="Pipeline SSE con progressione step-by-step")
@limiter.limit("3/minute")
async def api_run_stream(
    request: Request,
    dataset_path: str = str(DEFAULT_DATASET),
    weights_path: str = str(DEFAULT_WEIGHTS_PATH),
):
    """SSE endpoint: runs the analysis pipeline and streams step-by-step progress."""
    def _emit(pct: int, label: str, evt_type: str = "progress", **extra) -> str:
        payload = {"pct": pct, "label": label, **extra}
        return f"event: {evt_type}\ndata: {json.dumps(payload)}\n\n"

    async def event_stream():
        loop = asyncio.get_running_loop()
        try:
            # Step 1 â€” validate paths
            yield _emit(5, "Validazione percorsiâ€¦")
            try:
                dp = validate_path_in_allowed_roots(dataset_path, ALLOWED_DATASET_ROOTS)
                wp = validate_path_in_allowed_roots(weights_path, ALLOWED_WEIGHTS_ROOTS)
            except ValueError as exc:
                yield _emit(0, str(exc), "fatal"); return
            if not dp.is_file():
                yield _emit(0, f"Dataset non trovato: {dp}", "fatal"); return
            if not wp.is_file():
                yield _emit(0, f"File pesi non trovato: {wp}", "fatal"); return

            # Step 2 â€” load dataset
            yield _emit(15, "Caricamento datasetâ€¦")
            try:
                df = await loop.run_in_executor(None, lambda: DataLoader(str(dp)).load())
            except Exception as exc:
                yield _emit(0, f"Errore caricamento dataset: {exc}", "fatal"); return

            yield _emit(25, f"Dataset caricato â€” {len(df)} messaggi. Inizializzazione NLPâ€¦")

            # Step 3 â€” NLP engine init
            try:
                nlp = await loop.run_in_executor(None, _get_nlp_engine)
            except Exception as exc:
                yield _emit(0, f"Errore NLP engine: {exc}", "fatal"); return

            # Step 4 â€” NLP encoding
            yield _emit(38, "Codifica NLP dei messaggiâ€¦")
            try:
                texts = df["text"].tolist()
                embeddings = await loop.run_in_executor(None, lambda: nlp.encode(texts))
            except Exception as exc:
                yield _emit(0, f"Errore NLP encoding: {exc}", "fatal"); return

            # Step 5 â€” feature engineering
            yield _emit(58, "Estrazione feature di rischioâ€¦")
            try:
                def _features():
                    analyzer = TextAnalyzer()
                    af = analyzer.extract_features(df)
                    fe = FeatureEngineer()
                    return fe.build_features(df, embeddings, analyzer_features=af)
                featured = await loop.run_in_executor(None, _features)
            except Exception as exc:
                yield _emit(0, f"Errore feature engineering: {exc}", "fatal"); return

            # Step 6 â€” risk scoring
            yield _emit(76, "Calcolo punteggi di rischioâ€¦")
            try:
                def _score():
                    engine = RiskEngine(weights_path=str(wp))
                    return engine, engine.calculate(featured, include_explanations=True)
                risk_engine, results = await loop.run_in_executor(None, _score)
            except Exception as exc:
                yield _emit(0, f"Errore calcolo rischio: {exc}", "fatal"); return

            # Step 7 â€” save state
            yield _emit(91, "Finalizzazione e salvataggio risultatiâ€¦")

            def _finalize():
                global _results, _featured_df, _dataset_path, _weights_path, _loaded_weights
                global _results_cache, _results_version, _results_cache_hits, _results_cache_misses
                with _lock:
                    final = add_risk_band(results.reset_index(drop=True))
                    _results = final
                    _featured_df = featured.copy()
                    _dataset_path = str(dp)
                    _weights_path = str(wp)
                    _loaded_weights = risk_engine.weights.copy()
                    _results_version += 1
                    _results_cache.clear()
                    _results_cache_hits = 0
                    _results_cache_misses = 0
                    _sync_triage_from_results(final)
                    return len(final)

            t0 = datetime.now(timezone.utc)
            total = await loop.run_in_executor(None, _finalize)
            elapsed_ms = int((datetime.now(timezone.utc) - t0).total_seconds() * 1000)
            _save_kpi_snapshot(_results, elapsed_ms)

            yield _emit(100, f"Analisi completata â€” {total} messaggi elaborati!", "done",
                        total=total,
                        generated_at=datetime.now(timezone.utc).isoformat(),
                        dataset_path=str(dp),
                        weights_path=str(wp),
                        duration_ms=elapsed_ms,
                        system=_system_status())

        except Exception as exc:
            yield _emit(0, f"Errore imprevisto: {exc}", "fatal")

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-store",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


@app.post("/api/run", tags=["Pipeline"], summary="Esegui pipeline di analisi", dependencies=[Depends(_require_api_key)])
@limiter.limit("3/minute")
async def api_run(request: Request, body: RunRequest):
    global _results, _featured_df, _dataset_path, _weights_path, _loaded_weights
    global _results_cache, _results_version, _results_cache_hits, _results_cache_misses
    t0 = datetime.now(timezone.utc)

    try:
        dataset_path = validate_path_in_allowed_roots(body.dataset_path, ALLOWED_DATASET_ROOTS)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    try:
        w_path = validate_path_in_allowed_roots(body.weights_path, ALLOWED_WEIGHTS_ROOTS)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    if not dataset_path.is_file():
        raise HTTPException(status_code=400, detail=f"Dataset is not a file: {dataset_path}")
    if not w_path.is_file():
        raise HTTPException(status_code=400, detail=f"Weights is not a file: {w_path}")

    try:
        nlp = _get_nlp_engine()
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"NLP engine initialisation failed: {exc}")

    with _lock:
        loader = DataLoader(str(dataset_path))
        df = loader.load()

        embeddings = nlp.encode(df["text"].tolist())

        analyzer = TextAnalyzer()
        analyzer_features = analyzer.extract_features(df)

        fe = FeatureEngineer()
        featured = fe.build_features(df, embeddings, analyzer_features=analyzer_features)

        risk_engine = RiskEngine(weights_path=str(w_path))
        results = risk_engine.calculate(featured, include_explanations=True)

        _results = add_risk_band(results.reset_index(drop=True))
        _featured_df = featured.copy()
        _dataset_path = str(dataset_path)
        _weights_path = str(w_path)
        _loaded_weights = risk_engine.weights.copy()
        _results_version += 1
        _results_cache.clear()
        _results_cache_hits = 0
        _results_cache_misses = 0
        _sync_triage_from_results(_results)

    elapsed_ms = int((datetime.now(timezone.utc) - t0).total_seconds() * 1000)
    _save_kpi_snapshot(_results, elapsed_ms)
    return {
        "status": "ok",
        "total": len(_results),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "duration_ms": elapsed_ms,
        "dataset_path": _dataset_path,
        "weights_path": _weights_path,
        "system": _system_status(),
    }


@app.post("/api/results", tags=["Risultati"], summary="Filtra e pagina i risultati di analisi")
async def api_results(params: FilterParams):
    global _results_cache_hits, _results_cache_misses
    if _results.empty:
        raise HTTPException(status_code=404, detail="No analysis results yet. Run the pipeline first.")

    cache_key = _make_results_cache_key(params, _results_version)
    cached = _results_cache.get(cache_key)
    if cached is not None:
        _results_cache.move_to_end(cache_key)
        _results_cache_hits += 1
        return {**cached, "system": _system_status()}

    _results_cache_misses += 1

    filtered = _apply_filters(
        _results, params.min_risk, params.max_risk,
        params.bands, params.drivers, params.text_query, params.users,
    )
    if filtered.empty:
        return {
            "kpis": {},
            "charts": {},
            "tables": {},
            "drivers": [],
            "all_users": [],
            "total": len(_results),
            "executive_summary": {},
            "system": _system_status(),
        }

    # KPIs
    kpis = {
        "messages": int(filtered.shape[0]),
        "total": int(len(_results)),
        "users": int(filtered["user"].nunique()),
        "avg_risk": round(float(filtered["risk_score"].mean()), 4),
        "max_risk": round(float(filtered["risk_score"].max()), 4),
        "median_risk": round(float(filtered["risk_score"].median()), 4),
        "std_risk": round(float(filtered["risk_score"].std()), 4) if len(filtered) > 1 else 0.0,
        "high": int((filtered["risk_band"] == "High").sum()),
        "medium": int((filtered["risk_band"] == "Medium").sum()),
        "low": int((filtered["risk_band"] == "Low").sum()),
        "high_pct": round((filtered["risk_band"] == "High").mean() * 100, 1),
    }

    # Charts (Vega-Lite specs)
    charts: dict[str, Any] = {
        "histogram": _chart_histogram(filtered),
        "donut": _chart_donut(filtered),
        "driver_bar": _chart_driver_bar(filtered),
        "heatmap": _chart_heatmap(filtered),
        "user_scatter": _chart_user_scatter(filtered),
        "correlation": _chart_correlation(filtered),
        "boxplot": _chart_boxplot(filtered),
        "weights": _chart_weights(),
        "feature_avg": _chart_feature_avg(filtered),
    }

    # User ranking table
    by_user = (
        filtered.groupby("user", as_index=False)
        .agg(
            avg_risk=("risk_score", "mean"),
            max_risk=("risk_score", "max"),
            messages=("risk_score", "count"),
            high_count=("risk_band", lambda x: int((x == "High").sum())),
        )
        .sort_values("avg_risk", ascending=False)
    )
    by_user["avg_risk"] = by_user["avg_risk"].round(4)
    by_user["max_risk"] = by_user["max_risk"].round(4)

    # Top messages table (paginated)
    display_cols = ["user", "text", "risk_score", "risk_band", "top_risk_driver"] + FEATURE_COLUMNS
    available = [c for c in display_cols if c in filtered.columns]
    sorted_msgs = filtered.sort_values("risk_score", ascending=False).head(params.top_n)
    total_filtered = len(sorted_msgs)
    top_msgs = sorted_msgs.iloc[params.offset : params.offset + params.limit]

    # Top 5 message detail cards
    contrib_cols = [c for c in filtered.columns if c.startswith("contrib_")]
    top5 = filtered.sort_values("risk_score", ascending=False).head(5)
    detail_cards = [_build_detail_card(row, contrib_cols) for _, row in top5.iterrows()]

    drivers = sorted(filtered["top_risk_driver"].dropna().unique().tolist())
    all_users = sorted(_results["user"].dropna().unique().tolist())

    # Executive Summary
    _exec_top_driver = "\u2014"
    _exec_top_user = "\u2014"
    _exec_top_user_risk = 0.0
    if "top_risk_driver" in filtered.columns:
        _driver_counts = filtered["top_risk_driver"].value_counts()
        if not _driver_counts.empty:
            _raw_driver = str(_driver_counts.index[0])
            _exec_top_driver = FEATURE_LABELS.get(_raw_driver, _raw_driver)
    _user_avg = filtered.groupby("user")["risk_score"].mean().sort_values(ascending=False)
    if not _user_avg.empty:
        _exec_top_user = str(_user_avg.index[0])
        _exec_top_user_risk = round(float(_user_avg.iloc[0]), 3)
    executive_summary = {
        "high_count": kpis["high"],
        "high_pct": kpis["high_pct"],
        "top_driver": _exec_top_driver,
        "top_user": _exec_top_user,
        "top_user_risk": _exec_top_user_risk,
        "avg_risk": kpis["avg_risk"],
        "total_messages": kpis["messages"],
    }

    response_payload = {
        "kpis": kpis,
        "charts": charts,
        "tables": {
            "users": by_user.to_dict(orient="records"),
            "messages": top_msgs[available].round(4).to_dict(orient="records"),
            "detail_cards": detail_cards,
        },
        "drivers": drivers,
        "all_users": all_users,
        "total": len(_results),
        "feature_labels": FEATURE_LABELS,
        "executive_summary": executive_summary,
        "pagination": {
            "offset": params.offset,
            "limit": params.limit,
            "total_filtered": total_filtered,
            "returned": len(top_msgs),
            "has_more": (params.offset + params.limit) < total_filtered,
        },
    }

    _results_cache[cache_key] = response_payload
    while len(_results_cache) > RESULTS_CACHE_MAX_SIZE:
        _results_cache.popitem(last=False)
    return {**response_payload, "system": _system_status()}


@app.get("/api/user/{username}", tags=["Risultati"], summary="Dettaglio profilo utente")
async def api_user_detail(username: str):
    if _results.empty:
        raise HTTPException(status_code=404, detail="No results.")
    user_df = _results[_results["user"] == username]
    if user_df.empty:
        raise HTTPException(status_code=404, detail=f"User not found: {username}")

    contrib_cols = [c for c in user_df.columns if c.startswith("contrib_")]
    detail_cards = [
        _build_detail_card(row, contrib_cols)
        for _, row in user_df.sort_values("risk_score", ascending=False).head(10).iterrows()
    ]

    # Average feature scores for this user
    feat_profile = {}
    for c in FEATURE_COLUMNS:
        if c in user_df.columns:
            feat_profile[FEATURE_LABELS.get(c, c)] = round(float(user_df[c].mean()), 4)

    return {
        "user": username,
        "messages": int(len(user_df)),
        "avg_risk": round(float(user_df["risk_score"].mean()), 4),
        "max_risk": round(float(user_df["risk_score"].max()), 4),
        "high_count": int((user_df["risk_band"] == "High").sum()),
        "med_count": int((user_df["risk_band"] == "Medium").sum()),
        "low_count": int((user_df["risk_band"] == "Low").sum()),
        "feature_profile": feat_profile,
        "detail_cards": detail_cards,
    }


@app.get("/api/export/csv", tags=["Export"], summary="Esporta CSV completo")
async def api_export_csv():
    if _results.empty:
        raise HTTPException(status_code=404, detail="No results to export.")
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    header = (
        f"# CogniX Surface â€” Export\n"
        f"# Generated: {timestamp}\n"
        f"# Records: {len(_results)}\n"
        f"# Weights: {_weights_path}\n"
    )
    csv_data = header + _results.to_csv(index=False)
    buf = io.BytesIO(csv_data.encode("utf-8"))
    filename = f"cognitive_risk_export_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.csv"
    return StreamingResponse(
        buf,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.get("/api/export/users", tags=["Export"], summary="Esporta riepilogo utenti")
async def api_export_users():
    if _results.empty:
        raise HTTPException(status_code=404, detail="No results to export.")
    summary = (
        _results.groupby("user", as_index=False)
        .agg(avg_risk=("risk_score", "mean"), max_risk=("risk_score", "max"),
             messages=("risk_score", "count"))
        .sort_values("avg_risk", ascending=False)
    )
    buf = io.BytesIO(summary.to_csv(index=False).encode("utf-8"))
    filename = f"cognitive_risk_users_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.csv"
    return StreamingResponse(
        buf,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.post("/api/export/filtered", tags=["Export"], summary="Esporta CSV filtrato")
async def api_export_filtered(params: FilterParams):
    if _results.empty:
        raise HTTPException(status_code=404, detail="No results to export.")
    filtered = _apply_filters(
        _results, params.min_risk, params.max_risk,
        params.bands, params.drivers, params.text_query, params.users,
    )
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    header = (
        f"# CogniX Surface \u2014 Filtered Export\n"
        f"# Generated: {timestamp}\n"
        f"# Records: {len(filtered)} of {len(_results)}\n"
        f"# Filters: min_risk={params.min_risk}, max_risk={params.max_risk}\n"
    )
    csv_data = header + filtered.to_csv(index=False)
    buf = io.BytesIO(csv_data.encode("utf-8"))
    filename = f"cognitive_risk_filtered_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.csv"
    return StreamingResponse(
        buf,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.get("/api/weights", tags=["Pesi"], summary="Ottieni pesi correnti")
async def api_get_weights():
    """Return the currently loaded risk weights."""
    current = dict(_loaded_weights) if _loaded_weights else dict(DEFAULT_WEIGHTS)
    return {"weights": current, "is_custom": bool(_loaded_weights and _loaded_weights != DEFAULT_WEIGHTS)}


@app.post("/api/weights", tags=["Pesi"], summary="Aggiorna pesi e ricalcola rischio", dependencies=[Depends(_require_api_key)])
async def api_update_weights(body: WeightsUpdateRequest):
    """Update risk weights and optionally re-score if featured data is available."""
    global _loaded_weights, _results, _results_cache, _results_version

    if not body.weights:
        raise HTTPException(status_code=400, detail="Weights dict cannot be empty")

    for key, val in body.weights.items():
        if key not in DEFAULT_WEIGHTS:
            raise HTTPException(status_code=400, detail=f"Unknown weight key: {key}")
        if not isinstance(val, (int, float)) or val < 0 or not np.isfinite(float(val)):
            raise HTTPException(status_code=400, detail=f"Weight '{key}' must be a non-negative finite number")

    if sum(body.weights.values()) <= 0:
        raise HTTPException(status_code=400, detail="Sum of weights must be positive")

    rescored = False
    with _lock:
        _loaded_weights = {k: float(v) for k, v in body.weights.items()}

        if not _featured_df.empty:
            risk_engine = RiskEngine()
            risk_engine.weights = _loaded_weights.copy()
            rescored_df = risk_engine.calculate(_featured_df.copy(), include_explanations=True)
            _results = add_risk_band(rescored_df.reset_index(drop=True))
            _results_version += 1
            _results_cache.clear()
            rescored = True

    return {"status": "ok", "weights": _loaded_weights, "rescored": rescored}


@app.post("/api/alerts/webhook", tags=["Alert"], summary="Invia notifica a webhook esterno", dependencies=[Depends(_require_api_key)])
async def api_alert_webhook(body: AlertWebhookRequest):
    """Relays alert events to an external webhook endpoint."""
    url = body.webhook_url.strip()
    if not (url.startswith("http://") or url.startswith("https://")):
        raise HTTPException(status_code=400, detail="Webhook URL must start with http:// or https://")

    payload = {
        "event": body.event,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "system": _system_status(),
        "payload": body.payload,
    }

    def _send() -> tuple[int, str]:
        data = json.dumps(payload).encode("utf-8")
        headers = {"Content-Type": "application/json", "User-Agent": "CogniX-Surface/2.0"}
        if WEBHOOK_HMAC_SECRET:
            sig = hmac.new(
                WEBHOOK_HMAC_SECRET.encode("utf-8"),
                data,
                hashlib.sha256,
            ).hexdigest()
            headers["X-CogniX-Signature"] = f"sha256={sig}"
        req = urllib.request.Request(
            url=url,
            data=data,
            headers=headers,
            method="POST",
        )
        max_attempts = 3
        last_code, last_body = 0, ""
        for attempt in range(max_attempts):
            try:
                with urllib.request.urlopen(req, timeout=8) as resp:
                    code = int(resp.getcode() or 0)
                    body_text = resp.read(4096).decode("utf-8", errors="ignore")
                    if 200 <= code < 300:
                        return code, body_text
                    last_code, last_body = code, body_text
            except urllib.error.HTTPError as exc:
                body_text = exc.read(4096).decode("utf-8", errors="ignore") if exc.fp else ""
                last_code, last_body = int(exc.code or 0), body_text
                if 400 <= last_code < 500:
                    return last_code, last_body
            except urllib.error.URLError as exc:
                last_code, last_body = 0, str(exc.reason)
            if attempt < max_attempts - 1:
                time.sleep(min(2 ** attempt, 4))
        return last_code, last_body

    loop = asyncio.get_running_loop()
    status_code, response_excerpt = await loop.run_in_executor(None, _send)
    if status_code < 200 or status_code >= 300:
        raise HTTPException(
            status_code=502,
            detail=f"Webhook target returned HTTP {status_code}: {response_excerpt[:120]}",
        )

    return {
        "status": "ok",
        "target_status": status_code,
        "target_body": response_excerpt,
    }


@app.post("/api/triage/list", tags=["Triage"], summary="Lista e filtra coda triage")
async def api_triage_list(params: TriageListParams):
    if params.statuses:
        bad = [s for s in params.statuses if s not in TRIAGE_ALLOWED_STATUSES]
        if bad:
            raise HTTPException(status_code=400, detail=f"Invalid triage status: {', '.join(bad)}")
    if params.priorities:
        bad_p = [p for p in params.priorities if p not in TRIAGE_ALLOWED_PRIORITIES]
        if bad_p:
            raise HTTPException(status_code=400, detail=f"Invalid triage priority: {', '.join(bad_p)}")

    now_dt = datetime.now(timezone.utc)
    with _lock:
        items = []
        for item in _triage_items.values():
            enriched = dict(item)
            enriched.update(_triage_deadline_info(enriched, now_dt))
            items.append(enriched)

    if params.only_latest:
        items = [i for i in items if bool(i.get("present_in_latest_run"))]

    if params.statuses:
        wanted = set(params.statuses)
        items = [i for i in items if i.get("status") in wanted]

    if params.priorities:
        wanted_p = set(params.priorities)
        items = [i for i in items if i.get("priority") in wanted_p]

    assignee_q = params.assignee.strip().lower()
    if assignee_q:
        items = [i for i in items if assignee_q in str(i.get("assignee", "")).lower()]

    text_q = params.text_query.strip().lower()
    if text_q:
        items = [
            i for i in items
            if text_q in str(i.get("text", "")).lower()
            or text_q in str(i.get("user", "")).lower()
            or text_q in str(i.get("top_driver", "")).lower()
        ]

    items = [i for i in items if float(i.get("risk_score", 0.0)) >= params.min_risk]
    items.sort(
        key=lambda x: (
            0 if bool(x.get("sla_breached")) else 1,
            TRIAGE_STATUS_ORDER.get(str(x.get("status")), 99),
            {"P1": 0, "P2": 1, "P3": 2}.get(str(x.get("priority")), 9),
            -float(x.get("risk_score", 0.0)),
        )
    )
    items = items[: params.top_n]

    counts = {status: 0 for status in TRIAGE_ALLOWED_STATUSES}
    p_counts = {p: 0 for p in TRIAGE_ALLOWED_PRIORITIES}
    open_overdue = 0
    for item in _triage_items.values():
        status = str(item.get("status", "new"))
        if status in counts:
            counts[status] += 1
        enriched = dict(item)
        enriched.update(_triage_deadline_info(enriched, now_dt))
        p = str(enriched.get("priority", ""))
        if p in p_counts:
            p_counts[p] += 1
        if status in {"new", "in_progress"} and bool(enriched.get("sla_breached")):
            open_overdue += 1

    return {
        "items": items,
        "summary": {
            "total": len(_triage_items),
            "open": counts["new"] + counts["in_progress"],
            "overdue_open": open_overdue,
            "status_counts": counts,
            "priority_counts": p_counts,
            "latest_only": params.only_latest,
        },
        "system": _system_status(),
    }


@app.patch("/api/triage/item/{item_id}", tags=["Triage"], summary="Aggiorna singolo item triage", dependencies=[Depends(_require_api_key)])
async def api_triage_update(item_id: str, body: TriageUpdateRequest):
    now_iso = datetime.now(timezone.utc).isoformat()

    with _lock:
        item = _triage_items.get(item_id)
        if not item:
            raise HTTPException(status_code=404, detail=f"Triage item not found: {item_id}")

        changes: list[dict[str, str]] = []

        if body.status is not None:
            new_status = body.status.strip()
            if new_status not in TRIAGE_ALLOWED_STATUSES:
                raise HTTPException(status_code=400, detail=f"Invalid triage status: {new_status}")
            if new_status != item.get("status"):
                changes.append({"action": "status", "details": f"{item.get('status')} -> {new_status}"})
                item["status"] = new_status

        if body.assignee is not None:
            new_assignee = _sanitize(body.assignee.strip())
            if new_assignee != str(item.get("assignee", "")):
                changes.append({"action": "assignee", "details": f"{item.get('assignee', '')} -> {new_assignee}"})
                item["assignee"] = new_assignee

        note = _sanitize((body.note or "").strip())
        if note:
            notes = item.get("notes") or []
            notes.append({"time": now_iso, "text": note})
            item["notes"] = notes[-25:]
            changes.append({"action": "note", "details": note[:120]})

        if changes:
            activity = item.get("activity") or []
            for change in changes:
                activity.append({"time": now_iso, **change})
            item["activity"] = activity[-50:]
            item["updated_at"] = now_iso

        _db_save_triage_item(item_id, item)
        updated = dict(item)

    return {"status": "ok", "item": updated, "system": _system_status()}


@app.post("/api/triage/bootstrap", tags=["Triage"], summary="Sincronizza triage dai risultati", dependencies=[Depends(_require_api_key)])
async def api_triage_bootstrap(body: TriageSyncRequest):
    if _results.empty:
        raise HTTPException(status_code=404, detail="No analysis results yet. Run the pipeline first.")

    with _lock:
        created_count = _sync_triage_from_results(_results, min_risk=body.min_risk, top_n=body.top_n)

    return {
        "status": "ok",
        "triage_candidates": created_count,
        "triage_total": len(_triage_items),
        "system": _system_status(),
    }


# ── Bulk triage ───────────────────────────────────────────────────────────

class BulkTriageRequest(BaseModel):
    item_ids: list[str] = Field(..., min_length=1, max_length=250)
    status: str | None = None
    assignee: str | None = Field(default=None, max_length=128)
    note: str | None = Field(default=None, max_length=2000)


@app.post("/api/triage/bulk-update", tags=["Triage"], summary="Aggiornamento massivo di più item triage", dependencies=[Depends(_require_api_key)])
async def api_triage_bulk_update(body: BulkTriageRequest):
    if body.status is not None and body.status.strip() not in TRIAGE_ALLOWED_STATUSES:
        raise HTTPException(status_code=400, detail=f"Invalid triage status: {body.status}")

    now_iso = datetime.now(timezone.utc).isoformat()
    updated_ids: list[str] = []
    not_found: list[str] = []

    with _lock:
        for item_id in body.item_ids:
            item = _triage_items.get(item_id)
            if not item:
                not_found.append(item_id)
                continue

            changes: list[dict[str, str]] = []

            if body.status is not None:
                new_status = body.status.strip()
                if new_status != item.get("status"):
                    changes.append({"action": "status", "details": f"{item.get('status')} -> {new_status}"})
                    item["status"] = new_status

            if body.assignee is not None:
                new_assignee = _sanitize(body.assignee.strip())
                if new_assignee != str(item.get("assignee", "")):
                    changes.append({"action": "assignee", "details": f"{item.get('assignee', '')} -> {new_assignee}"})
                    item["assignee"] = new_assignee

            note_text = _sanitize((body.note or "").strip())
            if note_text:
                notes = item.get("notes") or []
                notes.append({"time": now_iso, "text": note_text})
                item["notes"] = notes[-25:]
                changes.append({"action": "note", "details": note_text[:120]})

            if changes:
                activity = item.get("activity") or []
                for change in changes:
                    activity.append({"time": now_iso, **change})
                item["activity"] = activity[-50:]
                item["updated_at"] = now_iso
                updated_ids.append(item_id)
                _db_save_triage_item(item_id, item)

    return {
        "status": "ok",
        "updated": len(updated_ids),
        "not_found": not_found,
        "system": _system_status(),
    }


# ── Filter Presets ────────────────────────────────────────────────────────

class FilterPresetCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=64)
    min_risk: float = Field(0.0, ge=0.0, le=1.0)
    max_risk: float = Field(1.0, ge=0.0, le=1.0)
    bands: list[str] | None = None
    drivers: list[str] | None = None
    users: list[str] | None = None
    text_query: str = Field("", max_length=512)
    top_n: int = Field(25, ge=1, le=1000)


@app.get("/api/filter-presets", tags=["Filtri"], summary="Lista preset filtri salvati")
async def api_filter_presets_list():
    return {"presets": list(_filter_presets.values())}


@app.post("/api/filter-presets", tags=["Filtri"], summary="Salva un nuovo preset filtri", dependencies=[Depends(_require_api_key)])
async def api_filter_presets_create(body: FilterPresetCreate):
    name = _sanitize(body.name.strip())
    if not name:
        raise HTTPException(status_code=400, detail="Preset name cannot be empty")
    if len(_filter_presets) >= 50 and name not in _filter_presets:
        raise HTTPException(status_code=400, detail="Maximum 50 presets reached")
    preset = {
        "name": name,
        "min_risk": body.min_risk,
        "max_risk": body.max_risk,
        "bands": body.bands,
        "drivers": body.drivers,
        "users": body.users,
        "text_query": _sanitize(body.text_query),
        "top_n": body.top_n,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    _filter_presets[name] = preset
    _db_save_preset(name, preset)
    return {"status": "ok", "preset": preset}


@app.delete("/api/filter-presets/{name}", tags=["Filtri"], summary="Elimina un preset filtri", dependencies=[Depends(_require_api_key)])
async def api_filter_presets_delete(name: str):
    if name not in _filter_presets:
        raise HTTPException(status_code=404, detail=f"Preset not found: {name}")
    del _filter_presets[name]
    _db_delete_preset(name)
    return {"status": "ok", "deleted": name}


# ── KPI Timeline ─────────────────────────────────────────────────────────

@app.get("/api/kpi-timeline", tags=["Risultati"], summary="Storico snapshot KPI per ogni run")
async def api_kpi_timeline():
    return {"snapshots": _kpi_timeline, "count": len(_kpi_timeline)}


@app.get("/api/health", tags=["System"], summary="Health check")
async def health():
    return {"status": "ok", "has_results": not _results.empty, "result_count": len(_results)}

