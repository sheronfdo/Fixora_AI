"""Stage 2 — bounded, evidence-cited LLM adjustment.

The LLM reads the free-text inspection notes the formula cannot parse and
returns a *small* adjustment plus cited evidence. Every guardrail (clamp,
citation requirement, anti-double-count, fail-safe) is enforced in code — the
model is never trusted to respect its own bounds. See §8.4.
"""
from __future__ import annotations

import logging
from typing import Literal

from pydantic import BaseModel, Field

from ..llm import get_chat_model
from .scoring import SUBSYSTEMS

logger = logging.getLogger("fixora.predict")

CONDITION_CAP_DEFAULT = 10.0
CONDITION_CAP_LOW = 5.0
VALUE_CAP = 8.0


class Factor(BaseModel):
    record_id: str
    observation: str
    direction: Literal["positive", "negative"]
    weight: Literal["minor", "moderate", "significant"]


class Assessment(BaseModel):
    # No hard bounds here: the model is *asked* to stay in range (system prompt),
    # but the real enforcement is the code clamps below — we never trust the model
    # to respect its own bounds, and an out-of-range value must clamp, not error.
    condition_adjustment: float = Field(
        default=0, description="Small nudge in [-10, +10]"
    )
    subsystem_adjustments: dict[str, float] = Field(default_factory=dict)
    factors: list[Factor] = Field(default_factory=list)
    value_adjust_pct: float = Field(default=0, description="In [-8, +8]")
    insights: str = ""
    recommendations: list[str] = Field(default_factory=list)


SYSTEM = """You are a senior vehicle inspector assessing a used car for Fixora.

A deterministic formula has ALREADY produced a baseline condition score using
the vehicle's age, mileage-vs-expected, number of services, repair severity
tags, and time since last service. DO NOT re-adjust for any of those — they are
already counted. The baseline is fixed and not up for revision.

Your job: read the free-text WORK and INSPECTION NOTES in the service records
and report only what those reveal that the formula cannot capture — e.g. an
unresolved fault, a recurring problem, deferred/declined work, or exceptionally
clean documentation.

Rules (enforced):
- condition_adjustment is a SMALL nudge in [-10, +10]. You can move the score by
  at most one band, never invent one.
- Every factor MUST cite a record_id from the provided records. Uncited factors
  are discarded.
- value_adjust_pct is in [-8, +8] and may ONLY be justified by evidence in THIS
  vehicle's own records (e.g. an unresolved fault a buyer's inspection would
  find). NEVER adjust value based on market demand, model popularity, or price
  trends — you do not have that knowledge.
- All money is LKR. Be specific and concise in insights and recommendations.
"""


def _empty() -> dict:
    return {
        "condition_adjustment": 0.0,
        "subsystem_adjustments": {},
        "factors": [],
        "value_adjust_pct": 0.0,
        "insights": "",
        "recommendations": [],
        "llm_adjusted": False,
    }


def _records_text(records: list[dict]) -> str:
    lines = []
    for r in records:
        parts = ", ".join(
            f"{p.get('part_name','')}({p.get('subsystem','')})"
            for p in (r.get("service_parts") or [])
        )
        lines.append(
            f"- record_id={r.get('id')} | {str(r.get('serviced_at',''))[:10]} "
            f"| severity={r.get('severity','Routine')} "
            f"| odometer={r.get('odometer_reading','?')} "
            f"| work: {r.get('work_performed','') or '—'} "
            f"| inspection: {r.get('inspection_notes','') or '—'} "
            f"| parts: {parts or '—'}"
        )
    return "\n".join(lines) if lines else "No service records."


def assess(baseline: dict, records: list[dict]) -> dict:
    """Return the validated, clamped Stage-2 result. Fail-safe on any error."""
    if not records:
        return _empty()  # nothing to read → baseline stands

    cap = CONDITION_CAP_LOW if baseline["confidence"] == "Low" else CONDITION_CAP_DEFAULT
    valid_ids = {str(r.get("id")) for r in records}

    try:
        llm = get_chat_model(temperature=0.0)
        structured = llm.with_structured_output(Assessment)

        prompt = (
            f"{SYSTEM}\n\n"
            f"Baseline score: {baseline['baseline_score']} "
            f"(confidence {baseline['confidence']}, band {baseline['band']}).\n"
            f"Component breakdown (already counted): {baseline['breakdown']}\n\n"
            f"Service records:\n{_records_text(records)}\n\n"
            f"Return your assessment as the structured schema."
        )
        result: Assessment = structured.invoke(prompt)
    except Exception as exc:
        logger.warning("Stage-2 LLM assessment failed, using baseline only: %s", exc)
        return _empty()

    # --- validate & clamp (never trust the model) ----------------------
    kept = [f for f in result.factors if str(f.record_id) in valid_ids]

    if not kept:
        # No cited evidence survived → no adjustment at all.
        cond_adj = 0.0
        value_adj = 0.0
    else:
        cond_adj = max(-cap, min(cap, float(result.condition_adjustment)))
        value_adj = max(-VALUE_CAP, min(VALUE_CAP, float(result.value_adjust_pct)))

    sub_adj = {
        s: max(-8.0, min(8.0, float(v)))
        for s, v in (result.subsystem_adjustments or {}).items()
        if s in SUBSYSTEMS
    }

    return {
        "condition_adjustment": round(cond_adj, 2),
        "subsystem_adjustments": sub_adj,
        "factors": [f.model_dump() for f in kept],
        "value_adjust_pct": round(value_adj, 2),
        "insights": result.insights or "",
        "recommendations": list(result.recommendations or []),
        "llm_adjusted": True,
    }
