"""
Conversational assistant for the route-intel section.

Architecture:

    user query (free text)
        ↓
    classify_intent()   — regex + keyword heuristics, NO LLM call
        ↓
    fetch_for_intent()  — pulls the relevant rows from MySQL (trips,
                          segments, insights, cost metrics, etc.)
        ↓
    answer_with_facts() — sends a task-specific prompt + facts to the
                          existing ai_insights backend (GGUF / rule-based).
                          Always grounded in real numbers — model never
                          invents because the facts ARE the prompt.
        ↓
    {answer, intent, sources, suggested_followups}

The intent layer is deliberately small and inspectable. Adding a new
intent is a 5-line patch: regex → fetcher → prompt template.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

from sqlalchemy import text

from route_intelligence import ai_insights as ai
from route_intelligence import db

logger = logging.getLogger(__name__)


# ============================================================================
# Intent registry
# ============================================================================
@dataclass
class Intent:
    name: str
    description: str
    patterns: List[re.Pattern]      # any match → this intent fires
    fetch: Callable[[str, Dict[str, Any]], Dict[str, Any]]
    prompt_task: str                # passed to the LLM as `Task: ...`


def _re(*pats: str) -> List[re.Pattern]:
    return [re.compile(p, re.IGNORECASE) for p in pats]


# ----------------------------------------------------------------------------
# Helpers — pull entities (trip number, segment number, vehicle id) from text
# ----------------------------------------------------------------------------
_RX_TRIP_ID = re.compile(r"\btrip\s*#?\s*(\d+)\b", re.IGNORECASE)
_RX_SEG_ID  = re.compile(r"\b(?:segment|seg)\s*#?\s*(\d+)\b", re.IGNORECASE)
_RX_VEHICLE = re.compile(r"\b([A-Z]{2}\d{2}[A-Z]{1,2}\d{3,4})\b")


def _extract_trip_id(q: str) -> Optional[int]:
    m = _RX_TRIP_ID.search(q)
    return int(m.group(1)) if m else None


def _extract_segment_id(q: str) -> Optional[int]:
    m = _RX_SEG_ID.search(q)
    return int(m.group(1)) if m else None


def _extract_vehicle(q: str) -> Optional[str]:
    m = _RX_VEHICLE.search(q)
    return m.group(1) if m else None


# ============================================================================
# Per-intent fetchers — each returns {facts, sources}
# ============================================================================
def _fetch_fleet_overview(q: str, ctx: Dict[str, Any]) -> Dict[str, Any]:
    """Aggregate metrics across every upload's trip + the most recent insights."""
    with db.get_engine().connect() as c:
        trips = c.execute(text("""
            SELECT t.id, t.vehicle_id, t.from_waypoint, t.to_waypoint,
                   t.distance_km, t.duration_min, t.n_segments, t.start_ts,
                   cm.total_cost_inr, cm.cost_per_km, cm.idle_fuel_waste_inr,
                   cm.efficiency_pct
            FROM ri_trips t
            LEFT JOIN ri_analysis_runs r
              ON r.trip_id = t.id AND r.status = 'done'
              AND r.params_json NOT LIKE '%"scope": "segment"%'
              AND r.id = (
                  SELECT MAX(r2.id) FROM ri_analysis_runs r2
                  WHERE r2.trip_id = t.id AND r2.status='done'
                    AND r2.params_json NOT LIKE '%"scope": "segment"%'
              )
            LEFT JOIN ri_cost_metrics cm ON cm.run_id = r.id
            ORDER BY t.start_ts DESC
            LIMIT 50
        """)).mappings().all()
        n_trips = len(trips)
        total_dist = sum((t["distance_km"] or 0) for t in trips)
        total_cost = sum((t["total_cost_inr"] or 0) for t in trips)
        total_idle_waste = sum((t["idle_fuel_waste_inr"] or 0) for t in trips)
        analysed = [t for t in trips if t["total_cost_inr"]]
        avg_eff = (sum((t["efficiency_pct"] or 0) for t in analysed) / len(analysed)) if analysed else 0
    return {
        "facts": {
            "trip_count": n_trips,
            "analysed_count": len(analysed),
            "total_distance_km": round(total_dist, 1),
            "total_cost_inr": round(total_cost, 0),
            "total_idle_waste_inr": round(total_idle_waste, 0),
            "avg_efficiency_pct": round(avg_eff, 1),
            "trip_samples": [
                {"id": t["id"], "vehicle": t["vehicle_id"],
                 "route": f"{t['from_waypoint']} → {t['to_waypoint']}",
                 "distance_km": t["distance_km"], "cost_inr": t["total_cost_inr"]}
                for t in trips[:5]
            ],
        },
        "sources": [{"kind": "trip", "id": t["id"]} for t in trips],
    }


def _fetch_summarize_trip(q: str, ctx: Dict[str, Any]) -> Dict[str, Any]:
    tid = _extract_trip_id(q) or ctx.get("trip_id")
    if not tid:
        return {"facts": {"error": "no trip id mentioned"}, "sources": []}
    trip = db.get_trip(tid)
    if not trip:
        return {"facts": {"error": f"trip {tid} not found"}, "sources": []}
    run = db.get_latest_done_run_for_trip(tid)
    if not run:
        return {"facts": {"error": f"trip {tid} hasn't been analyzed yet"},
                "sources": [{"kind": "trip", "id": tid}]}
    bundle = db.fetch_full_analysis(run["id"])
    return {
        "facts": {
            "trip_id": tid,
            "vehicle": trip["vehicle_id"],
            "route": f"{trip['from_waypoint']} → {trip['to_waypoint']}",
            "distance_km": trip["distance_km"],
            "duration_min": trip["duration_min"],
            "n_segments": trip["n_segments"],
            "costs": (bundle["cost_metrics"] or {}).get("breakdown"),
            "efficiency": (bundle["route_metrics"] or {}).get("efficiency"),
            "traffic": (bundle["route_metrics"] or {}).get("traffic"),
        },
        "sources": [{"kind": "trip", "id": tid}],
    }


def _fetch_worst_idle(q: str, ctx: Dict[str, Any]) -> Dict[str, Any]:
    """Trip with the highest idle-fuel waste across the fleet."""
    with db.get_engine().connect() as c:
        rows = c.execute(text("""
            SELECT t.id, t.vehicle_id, t.from_waypoint, t.to_waypoint,
                   cm.idle_fuel_waste_inr, cm.total_cost_inr, cm.cost_per_km
            FROM ri_trips t
            JOIN ri_analysis_runs r ON r.trip_id = t.id AND r.status='done'
              AND r.params_json NOT LIKE '%"scope": "segment"%'
            JOIN ri_cost_metrics cm ON cm.run_id = r.id
            ORDER BY cm.idle_fuel_waste_inr DESC
            LIMIT 5
        """)).mappings().all()
    if not rows:
        return {"facts": {"error": "no analysed trips yet"}, "sources": []}
    top = rows[0]
    return {
        "facts": {
            "winner": {
                "trip_id": top["id"], "vehicle": top["vehicle_id"],
                "route": f"{top['from_waypoint']} → {top['to_waypoint']}",
                "idle_waste_inr": top["idle_fuel_waste_inr"],
                "total_cost_inr": top["total_cost_inr"],
                "cost_per_km": top["cost_per_km"],
            },
            "runners_up": [
                {"trip_id": r["id"], "vehicle": r["vehicle_id"],
                 "route": f"{r['from_waypoint']} → {r['to_waypoint']}",
                 "idle_waste_inr": r["idle_fuel_waste_inr"]}
                for r in rows[1:]
            ],
        },
        "sources": [{"kind": "trip", "id": r["id"]} for r in rows],
    }


def _fetch_best_efficiency(q: str, ctx: Dict[str, Any]) -> Dict[str, Any]:
    """Trip with the best (highest) route efficiency."""
    with db.get_engine().connect() as c:
        rows = c.execute(text("""
            SELECT t.id, t.vehicle_id, t.from_waypoint, t.to_waypoint,
                   cm.efficiency_pct, cm.total_cost_inr, cm.cost_per_km
            FROM ri_trips t
            JOIN ri_analysis_runs r ON r.trip_id = t.id AND r.status='done'
              AND r.params_json NOT LIKE '%"scope": "segment"%'
            JOIN ri_cost_metrics cm ON cm.run_id = r.id
            ORDER BY cm.efficiency_pct DESC
            LIMIT 5
        """)).mappings().all()
    if not rows:
        return {"facts": {"error": "no analysed trips yet"}, "sources": []}
    return {
        "facts": {
            "best": [
                {"trip_id": r["id"], "vehicle": r["vehicle_id"],
                 "route": f"{r['from_waypoint']} → {r['to_waypoint']}",
                 "efficiency_pct": r["efficiency_pct"],
                 "cost_per_km": r["cost_per_km"]}
                for r in rows
            ],
        },
        "sources": [{"kind": "trip", "id": r["id"]} for r in rows],
    }


def _fetch_explain_segment(q: str, ctx: Dict[str, Any]) -> Dict[str, Any]:
    sid = _extract_segment_id(q) or ctx.get("segment_id")
    if not sid:
        return {"facts": {"error": "no segment id mentioned"}, "sources": []}
    seg = db.get_segment(sid)
    if not seg:
        return {"facts": {"error": f"segment {sid} not found"}, "sources": []}
    return {
        "facts": {
            "segment_id": sid,
            "seq": seg["seq"],
            "route": f"{seg['from_waypoint']} → {seg['to_waypoint']}",
            "distance_km": seg["distance_km"],
            "duration_min": seg["duration_min"],
            "avg_speed_kmph": seg["avg_speed_kmph"],
            "max_speed_kmph": seg["max_speed_kmph"],
            "moving_min": seg["moving_min"],
            "stopped_min": seg["stopped_min"],
        },
        "sources": [{"kind": "segment", "id": sid}],
    }


def _fetch_recent_insights(q: str, ctx: Dict[str, Any]) -> Dict[str, Any]:
    """Fallback for free-form queries — surface the most recent AI insights."""
    with db.get_engine().connect() as c:
        rows = c.execute(text("""
            SELECT ai.insight_type, ai.text, t.id AS trip_id,
                   t.vehicle_id, t.from_waypoint, t.to_waypoint, ai.created_at
            FROM ri_ai_insights ai
            LEFT JOIN ri_analysis_runs r ON r.id = ai.run_id
            LEFT JOIN ri_trips t ON t.id = r.trip_id
            WHERE t.id IS NOT NULL
            ORDER BY ai.created_at DESC LIMIT 8
        """)).mappings().all()
    return {
        "facts": {
            "user_query": q,
            "recent_insights": [
                {"type": r["insight_type"], "trip_id": r["trip_id"],
                 "vehicle": r["vehicle_id"],
                 "route": f"{r['from_waypoint']} → {r['to_waypoint']}",
                 "text": r["text"]}
                for r in rows
            ],
        },
        "sources": list({(r["trip_id"]) for r in rows if r["trip_id"]}),
    }


# ============================================================================
# Registry — patterns + fetchers + prompt task lines
# ============================================================================
INTENTS: List[Intent] = [
    Intent(
        name="fleet_overview",
        description="Summarise everything across uploaded trips.",
        patterns=_re(
            r"\b(fleet|overall|all\s+trips?|how\s+many|summary|overview|how\s+is\s+the\s+fleet|recap)\b",
        ),
        fetch=_fetch_fleet_overview,
        prompt_task=("Write a 3-sentence fleet-level summary: how many trips, "
                     "total distance, total spend, average efficiency, and the "
                     "single biggest concern."),
    ),
    Intent(
        name="worst_idle",
        description="Find the trip wasting the most fuel on idling.",
        patterns=_re(
            r"\b(idle|wast(ed|ing)|worst.*idle|most.*idle|fuel\s+wast|burn|burning)\b",
        ),
        fetch=_fetch_worst_idle,
        prompt_task=("State which trip wasted the most idle fuel, by how much, "
                     "and what could have been done. Mention runners-up only "
                     "if their figures are close to the winner."),
    ),
    Intent(
        name="best_efficiency",
        description="Top trips by route efficiency.",
        patterns=_re(
            r"\b(best|cleanest|most\s+efficient|highest\s+efficiency|top\s+route)\b",
        ),
        fetch=_fetch_best_efficiency,
        prompt_task=("Name the top-efficiency trip(s) and explain in one "
                     "sentence what makes them stand out."),
    ),
    Intent(
        name="summarize_trip",
        description="Deep-dive on a single trip the user named.",
        patterns=_re(
            r"\btrip\s*#?\s*\d+\b",
            r"\b(summarize|summary|analy[sz]e|explain|tell\s+me\s+about|recap|describe).+\btrip\b",
            r"\b(this|current|the)\s+trip\b",
            r"\bwhy.+trip\b",
        ),
        fetch=_fetch_summarize_trip,
        prompt_task=("Write a 3-4 sentence executive summary of the named trip "
                     "covering: route + distance, cost + cost/km, efficiency, "
                     "and the single most important issue (idle, traffic, or "
                     "detour). Do NOT invent numbers."),
    ),
    Intent(
        name="explain_segment",
        description="Drill into one segment of a trip.",
        patterns=_re(
            r"\b(seg(ment)?)\s*#?\s*\d+\b",
            r"\bwhy.+segment\b",
        ),
        fetch=_fetch_explain_segment,
        prompt_task=("Describe this single segment of a trip in 2 sentences: "
                     "where it went, how long, how fast, how much idle time."),
    ),
]

# Generic fallback if no pattern matches.
_FALLBACK = Intent(
    name="general",
    description="Free-form question with no recognised intent.",
    patterns=[],
    fetch=_fetch_recent_insights,
    prompt_task=("The user asked a free-form question. Use the recent AI "
                 "insights provided as context to answer in 2-3 sentences. "
                 "If the data does not cover the question, say so honestly "
                 "and suggest a specific question the user could ask."),
)


# ============================================================================
# Public API
# ============================================================================
def classify_intent(query: str) -> Intent:
    for it in INTENTS:
        if any(p.search(query) for p in it.patterns):
            return it
    return _FALLBACK


def ask(query: str, ctx: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Main entry — natural-language query → grounded answer."""
    ctx = ctx or {}
    intent = classify_intent(query)
    pulled = intent.fetch(query, ctx)
    facts = pulled.get("facts") or {}

    # Build the prompt — the metric blob IS the source of truth
    payload = {"task": intent.prompt_task, "user_query": query, "facts": facts}
    text_answer = ai._generate(intent.name, payload, _rule_answer_for(intent))

    return {
        "answer": text_answer.strip(),
        "intent": intent.name,
        "intent_description": intent.description,
        "model": ai.backend_name(),
        "sources": pulled.get("sources", []),
        "facts": facts,
        "suggested_followups": _followups_for(intent.name, facts),
    }


def suggestions() -> List[Dict[str, str]]:
    """Default suggestion chips for the UI."""
    return [
        {"label": "Fleet overview",     "query": "Give me a fleet overview"},
        {"label": "Worst idle waste",   "query": "Which trip wasted the most fuel on idling?"},
        {"label": "Best efficiency",    "query": "Which routes had the best efficiency?"},
        {"label": "Summarize trip 1",   "query": "Summarize trip 1"},
        {"label": "Explain segment 3",  "query": "Tell me about segment 3"},
    ]


# ============================================================================
# Rule-based fallbacks per intent (used when no GGUF is loaded)
# ============================================================================
def _rule_answer_for(intent: Intent) -> Callable[[Dict], str]:
    mapping = {
        "fleet_overview":  _rule_fleet_overview,
        "summarize_trip":  _rule_summarize_trip,
        "worst_idle":      _rule_worst_idle,
        "best_efficiency": _rule_best_efficiency,
        "explain_segment": _rule_explain_segment,
        "general":         _rule_general,
    }
    return mapping.get(intent.name, _rule_general)


def _rule_fleet_overview(p: Dict) -> str:
    f = p["facts"]
    if not f.get("trip_count"):
        return "No trips have been uploaded yet. Upload an Excel from the Route Intelligence page to get started."
    return (
        f"Across {f['trip_count']} uploaded trip(s) ({f['analysed_count']} analysed), "
        f"the fleet has covered {f['total_distance_km']} km at a total cost of "
        f"₹{f['total_cost_inr']:,.0f}, of which ₹{f['total_idle_waste_inr']:,.0f} was wasted on idling. "
        f"Average route efficiency is {f['avg_efficiency_pct']}% — "
        f"{'healthy' if f['avg_efficiency_pct'] >= 70 else 'there is real room to tighten detours and idle time'}."
    )


def _rule_summarize_trip(p: Dict) -> str:
    f = p["facts"]
    if f.get("error"):
        return f.get("error")
    c = f.get("costs") or {}
    eff = f.get("efficiency") or {}
    return (
        f"Trip #{f['trip_id']} ({f['route']}) on vehicle {f['vehicle']}: "
        f"{f['distance_km']} km in {round(f['duration_min']/60, 1)} hrs across {f['n_segments']} segments, "
        f"costing ₹{(c.get('total_cost_inr') or 0):,.0f} (₹{c.get('cost_per_km', 0)}/km). "
        f"Route efficiency was {round((eff.get('route_efficiency') or 0) * 100)}% — "
        f"{eff.get('interpretation', 'no efficiency interpretation available')}."
    )


def _rule_worst_idle(p: Dict) -> str:
    f = p["facts"]
    if f.get("error"):
        return f["error"]
    w = f["winner"]
    return (
        f"Trip #{w['trip_id']} ({w['vehicle']}, {w['route']}) wasted the most fuel idling — "
        f"₹{(w['idle_waste_inr'] or 0):,.0f} burned while parked, on a total cost of "
        f"₹{(w['total_cost_inr'] or 0):,.0f} (₹{w['cost_per_km']}/km). "
        f"Cutting idle by 30% on this run alone would save roughly "
        f"₹{(w['idle_waste_inr'] or 0) * 0.3:,.0f}."
    )


def _rule_best_efficiency(p: Dict) -> str:
    f = p["facts"]
    if f.get("error"):
        return f["error"]
    top = (f.get("best") or [{}])[0]
    return (
        f"Trip #{top.get('trip_id')} ({top.get('vehicle')}, {top.get('route')}) leads on route efficiency "
        f"at {top.get('efficiency_pct')}%, costing ₹{top.get('cost_per_km')}/km. "
        f"That's the closest your fleet came to a straight-line run — worth studying as a baseline."
    )


def _rule_explain_segment(p: Dict) -> str:
    f = p["facts"]
    if f.get("error"):
        return f["error"]
    return (
        f"Segment #{f['seq']} ({f['route']}) covered {f['distance_km']} km in "
        f"{round(f['duration_min'] / 60, 1)} hrs at an average moving speed of "
        f"{f['avg_speed_kmph']} km/h (max {f['max_speed_kmph']}). "
        f"The vehicle was moving for {round(f['moving_min'])} min and idle for "
        f"{round(f['stopped_min'])} min."
    )


def _rule_general(p: Dict) -> str:
    f = p["facts"]
    insights = f.get("recent_insights") or []
    if not insights:
        return ("I don't have analysed trips yet to answer that. "
                "Try uploading an Excel from the Route Intelligence page, "
                "then ask me 'summarize trip 1' or 'fleet overview'.")
    top = insights[0]
    return (
        f"Most recently, the analyzer noted on trip {top['trip_id']} "
        f"({top['route']}): \"{top['text']}\" "
        f"Try asking me more specifically — e.g. \"summarize trip 1\" or "
        "\"which trip wasted the most fuel?\""
    )


# ============================================================================
# Suggested follow-ups
# ============================================================================
def _followups_for(intent: str, facts: Dict[str, Any]) -> List[str]:
    if intent == "fleet_overview":
        tid = (facts.get("trip_samples") or [{}])[0].get("id")
        return [
            "Which trip wasted the most fuel on idling?",
            "Which routes had the best efficiency?",
            f"Summarize trip {tid}" if tid else "Summarize trip 1",
        ]
    if intent == "summarize_trip":
        tid = facts.get("trip_id")
        return [
            f"Why was trip {tid} slow?" if tid else "Why was that trip slow?",
            "Compare with the most efficient trip",
        ]
    if intent == "worst_idle":
        tid = (facts.get("winner") or {}).get("trip_id")
        return [
            f"Summarize trip {tid}" if tid else "Summarize the worst trip",
            "How much would a 30% idle cut save monthly?",
        ]
    return [
        "Give me a fleet overview",
        "Which trip wasted the most fuel?",
        "Summarize trip 1",
    ]
