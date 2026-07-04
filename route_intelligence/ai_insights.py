"""
AI insights — turn the deterministic metric blobs into natural-language
paragraphs and recommendation cards.

Three backends behind one ``generate_insight(...)`` function, chosen in this
priority order by ``get_backend()``:

1. ``CloudLLMBackend``    — a free-tier cloud LLM (Google Gemini) driven via
   LangChain. Active when ``INSIGHTS_PROVIDER=gemini`` and ``GEMINI_API_KEY``
   are set (paste them on the Settings page). This is the "real, dynamic AI".

2. ``LlamaCppBackend``    — loads any GGUF file from ``models/insights/``.
   The user drops a Phi-3-mini / Qwen2.5-1.5B-Instruct / TinyLlama
   ``*.gguf`` into that folder and we pick it up automatically. Requires
   ``pip install llama-cpp-python`` and uses CPU by default (fine for
   short generations).

3. ``RuleBasedBackend``   — deterministic fallback that writes good-quality
   English from the same metric blobs using f-strings. Always available
   and used when no cloud key / GGUF is present, or when the cloud call
   fails or runs out of free-tier quota — so insights NEVER break.

Whichever backend is active, every insight is persisted to ``ri_ai_insights``
by ``route_intelligence.pipeline`` so downstream MCP/UI calls are cached.
"""

from __future__ import annotations

import json
import logging
import os
import textwrap
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


# Where the user drops the .gguf file
MODELS_DIR = Path(os.environ.get(
    "RI_MODELS_DIR",
    str(Path(__file__).resolve().parent.parent / "models" / "insights"),
))


# ============================================================================
# Backend protocol
# ============================================================================
class _Backend:
    name: str = "stub"
    def generate(self, prompt: str, max_tokens: int = 256) -> Tuple[str, Optional[int], Optional[int]]:
        """Return (text, prompt_tokens, completion_tokens)."""
        raise NotImplementedError


# ============================================================================
# llama-cpp-python backend (GGUF)
# ============================================================================
class LlamaCppBackend(_Backend):
    def __init__(self, model_path: Path, n_ctx: int = 4096, n_threads: int = 4):
        from llama_cpp import Llama  # local import so it's optional
        logger.info("ai_insights: loading GGUF %s", model_path)
        self.llm = Llama(
            model_path=str(model_path),
            n_ctx=n_ctx,
            n_threads=n_threads,
            verbose=False,
        )
        self.name = f"llama-cpp:{model_path.name}"

    def generate(self, prompt: str, max_tokens: int = 256):
        out = self.llm.create_completion(
            prompt=prompt,
            max_tokens=max_tokens,
            temperature=0.4,
            top_p=0.9,
            stop=["</answer>", "\n\n\n"],
        )
        text = out["choices"][0]["text"].strip()
        usage = out.get("usage", {}) or {}
        return text, usage.get("prompt_tokens"), usage.get("completion_tokens")


# ============================================================================
# Cloud LLM backend — Google Gemini via LangChain (free tier)
# ============================================================================
class CloudLLMBackend(_Backend):
    """Real, dynamic insights from a cloud LLM. Uses LangChain's chat model so
    swapping providers later is a one-line change. Any failure (bad key, quota,
    network) is caught by ``_generate`` and falls back to the rule-based text."""

    def __init__(self, api_key: str, model: str = "gemini-2.5-flash",
                 temperature: float = 0.4):
        # Local imports so LangChain stays an OPTIONAL dependency — the app
        # runs fine on rule-based templates if these packages aren't installed.
        from langchain_google_genai import ChatGoogleGenerativeAI

        self.model = model
        kwargs: Dict[str, Any] = dict(
            model=model,
            google_api_key=api_key,
            temperature=temperature,
            # 2.5-class models silently burn output budget on hidden "thinking"
            # tokens and then truncate the visible answer mid-sentence. A large
            # cap + thinking_budget=0 keeps the whole paragraph.
            max_output_tokens=1024,
            timeout=int(os.environ.get("INSIGHTS_TIMEOUT", "20")),
        )
        try:
            self.llm = ChatGoogleGenerativeAI(thinking_budget=0, **kwargs)
        except TypeError:  # older langchain-google-genai without thinking_budget
            self.llm = ChatGoogleGenerativeAI(**kwargs)
        self.name = f"gemini:{model}"
        logger.info("ai_insights: cloud LLM backend ready (%s)", self.name)

    def generate_insight(self, role: str, payload: Dict[str, Any]) -> str:
        """Send system rules + the metric facts as proper chat messages and
        return the generated paragraph."""
        from langchain_core.messages import HumanMessage, SystemMessage

        body = json.dumps(payload, indent=2, default=str)
        user = f"Task: {role}\nFacts (use ONLY these numbers):\n{body}\n\nWrite the insight now."
        resp = self.llm.invoke([SystemMessage(content=_SYS_PROMPT),
                                HumanMessage(content=user)])
        return (getattr(resp, "content", "") or "").strip()

    def generate(self, prompt: str, max_tokens: int = 256):
        # Protocol compliance — insights use generate_insight() above.
        from langchain_core.messages import HumanMessage
        resp = self.llm.invoke([HumanMessage(content=prompt)])
        return (getattr(resp, "content", "") or "").strip(), None, None


# ============================================================================
# Rule-based backend — always available
# ============================================================================
class RuleBasedBackend(_Backend):
    name = "rule-based-v1"

    def generate(self, prompt: str, max_tokens: int = 256):
        # Not used directly — for rule-based we bypass the prompt path and
        # call dedicated formatters below.
        return prompt, None, None


# ============================================================================
# Backend selection
# ============================================================================
_BACKEND: Optional[_Backend] = None


def _find_gguf() -> Optional[Path]:
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    cands = sorted(MODELS_DIR.glob("*.gguf"))
    return cands[0] if cands else None


def get_backend() -> _Backend:
    global _BACKEND
    if _BACKEND is not None:
        return _BACKEND

    # 1) Cloud LLM (Gemini) — active when explicitly selected + a key is present.
    provider = os.environ.get("INSIGHTS_PROVIDER", "rule-based").strip().lower()
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if provider in ("gemini", "google") and api_key:
        try:
            model = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash").strip() or "gemini-2.5-flash"
            temp = float(os.environ.get("INSIGHTS_TEMPERATURE", "0.4"))
            _BACKEND = CloudLLMBackend(api_key, model=model, temperature=temp)
            return _BACKEND
        except Exception as exc:  # noqa: BLE001
            logger.warning("ai_insights: cloud LLM init failed (%s) — trying local/rules", exc)

    # 2) Local GGUF model, if the user dropped one in models/insights/.
    gguf = _find_gguf()
    if gguf is not None:
        try:
            _BACKEND = LlamaCppBackend(gguf)
            return _BACKEND
        except Exception as exc:
            logger.warning("ai_insights: GGUF load failed (%s) — falling back to rules", exc)

    # 3) Deterministic templates — always works.
    _BACKEND = RuleBasedBackend()
    return _BACKEND


def reset_backend() -> None:
    """Drop the cached backend so the next call re-selects based on current env.
    Called by the Settings API after a config save so a freshly-pasted Gemini
    key takes effect without a backend restart."""
    global _BACKEND
    _BACKEND = None


def backend_name() -> str:
    return get_backend().name


def is_llm_label(model: Optional[str]) -> bool:
    """True when a model label names text a REAL LLM wrote — used by the
    pipeline to decide whether an insight is worth persisting, and by the
    feeds to hide template output. 'rule-based-v1' and any '…→rule-fallback'
    label mean the deterministic templates produced the text."""
    m = (model or "").strip().lower()
    if not m or m.startswith("rule-based") or "rule-fallback" in m:
        return False
    return m.startswith("gemini") or m.startswith("llama-cpp")


# ============================================================================
# Prompt templates (used when a real LLM is loaded)
# ============================================================================
_SYS_PROMPT = (
    "You are a senior fleet operations analyst. Write a 2-4 sentence paragraph in "
    "professional, plain English using ONLY the figures provided. Currency is INR "
    "(₹). Distances are km. Do not invent numbers. End on a clear takeaway."
)


def _build_prompt(role: str, payload: Dict[str, Any]) -> str:
    body = json.dumps(payload, indent=2, default=str)
    return (
        f"<|system|>\n{_SYS_PROMPT}\n"
        f"<|user|>\nTask: {role}\nFacts:\n{body}\n"
        f"Write the paragraph now.\n<|assistant|>\n"
    )


# ============================================================================
# Public generators — one per insight type
# ============================================================================
def trip_summary(trip: Dict, costs: Dict, efficiency: Dict, traffic: Dict, zones: Dict) -> Dict:
    """High-level paragraph for the JourneyDetail banner."""
    payload = {
        "trip_label": f"{trip.get('from_waypoint','?')} → {trip.get('to_waypoint','?')}",
        "vehicle_id": trip.get("vehicle_id"),
        "distance_km": costs.get("total_distance_km"),
        "duration_hours": costs.get("total_hours"),
        "moving_hours": costs.get("moving_hours"),
        "stopped_hours": costs.get("stopped_hours"),
        "total_cost_inr": costs.get("total_cost_inr"),
        "cost_per_km": costs.get("cost_per_km"),
        "idle_waste_inr": costs.get("idle_fuel_waste_inr"),
        "route_efficiency": efficiency.get("route_efficiency"),
        "excess_pct": efficiency.get("excess_percentage"),
        "traffic_min": traffic.get("time_lost_minutes"),
        "max_speed": zones.get("max_speed_kmph"),
        "avg_speed": zones.get("avg_speed_kmph"),
    }
    text, model = _generate("trip_summary", payload, _rule_trip_summary)
    return _wrap(text, "trip_summary", model)


def cost_advice(costs: Dict, opportunities: List[Dict]) -> Dict:
    payload = {
        "total_cost_inr": costs.get("total_cost_inr"),
        "fuel_cost_inr": costs.get("fuel_cost_inr"),
        "driver_cost_inr": costs.get("driver_cost_inr"),
        "idle_waste_inr": costs.get("idle_fuel_waste_inr"),
        "cost_per_km": costs.get("cost_per_km"),
        "opportunities": opportunities,
    }
    text, model = _generate("cost_advice", payload, _rule_cost_advice)
    return _wrap(text, "cost_advice", model)


def route_quality(efficiency: Dict, backtracks: List[Dict], zones: Dict) -> Dict:
    payload = {
        "efficiency": efficiency,
        "backtrack_count": len(backtracks),
        "speed_zones": zones,
    }
    text, model = _generate("route_quality", payload, _rule_route_quality)
    return _wrap(text, "route_quality", model)


def traffic_callout(traffic: Dict) -> Dict:
    text, model = _generate("traffic_callout", traffic, _rule_traffic_callout)
    return _wrap(text, "traffic_callout", model)


def recommendations_list(opportunities: List[Dict]) -> Dict:
    """Bullet list (one sentence per opp) — designed to render as cards."""
    payload = {"opportunities": opportunities}
    text, model = _generate("recommendations_list", payload, _rule_recommendations)
    return _wrap(text, "recommendations_list", model)


def comparison_verdict(comparison_rows: List[Dict]) -> Dict:
    payload = {"rows": comparison_rows}
    text, model = _generate("comparison_verdict", payload, _rule_comparison_verdict)
    return _wrap(text, "comparison_verdict", model)


# ============================================================================
# Internals
# ============================================================================
def _generate(role: str, payload: Dict, rule_fn) -> Tuple[str, str]:
    """Return (text, model_label). The label names what ACTUALLY produced the
    text, so a fallback reads e.g. 'gemini:...→rule-fallback' rather than
    falsely claiming the LLM wrote it."""
    be = get_backend()
    if isinstance(be, RuleBasedBackend):
        return rule_fn(payload).strip(), be.name
    try:
        if isinstance(be, CloudLLMBackend):
            text = be.generate_insight(role, payload)
        else:
            prompt = _build_prompt(role, payload)
            text, _, _ = be.generate(prompt, max_tokens=320)
        text = (text or "").strip()
        if text:
            return text, be.name
        return rule_fn(payload).strip(), f"{be.name}→rule-fallback"
    except Exception as exc:
        logger.warning("ai_insights: backend '%s' failed (%s) — using rule fallback",
                       getattr(be, "name", "?"), exc)
        return rule_fn(payload).strip(), f"{getattr(be, 'name', '?')}→rule-fallback"


def _wrap(text: str, kind: str, model: Optional[str] = None) -> Dict:
    return {"insight_type": kind, "text": text, "model": model or backend_name()}


# ----------------------------------------------------------------------------
# Rule-based templates (the always-available fallback)
# ----------------------------------------------------------------------------
def _rule_trip_summary(p: Dict) -> str:
    label = p.get("trip_label", "this trip")
    dist = p.get("distance_km") or 0
    dur = p.get("duration_hours") or 0
    cost = p.get("total_cost_inr") or 0
    cpk = p.get("cost_per_km") or 0
    idle = p.get("idle_waste_inr") or 0
    eff = p.get("route_efficiency") or 0
    excess = p.get("excess_pct") or 0
    traffic = p.get("traffic_min") or 0
    avg = p.get("avg_speed") or 0
    eff_word = "very direct" if eff >= 0.9 else "good" if eff >= 0.75 else "indirect"
    s1 = (f"This {dist:.1f} km run ({label}) took {dur:.1f} hrs at an effective "
          f"{avg:.0f} km/h, costing ₹{cost:,.0f} (₹{cpk:.1f}/km).")
    s2 = (f"The route was {eff_word} — {excess:.0f}% longer than the straight line "
          f"— and the vehicle idled for ₹{idle:,.0f} of wasted fuel.")
    s3 = (f"Traffic-grade slow segments cost about {traffic:.0f} minutes." if traffic > 1
          else "No significant traffic loss was detected.")
    return " ".join([s1, s2, s3])


def _rule_cost_advice(p: Dict) -> str:
    tc = p.get("total_cost_inr") or 0
    fc = p.get("fuel_cost_inr") or 0
    dc = p.get("driver_cost_inr") or 0
    iw = p.get("idle_waste_inr") or 0
    cpk = p.get("cost_per_km") or 0
    opps = p.get("opportunities") or []
    parts = [f"Total trip cost was ₹{tc:,.0f} — ₹{fc:,.0f} fuel + ₹{dc:,.0f} driver "
             f"(₹{cpk:.1f}/km), of which ₹{iw:,.0f} was burned while idle."]
    if opps:
        top = opps[0]
        parts.append(f"Biggest lever: {top['category'].lower()} — {top['recommendation']} "
                     f"Potential monthly saving ≈ ₹{top['monthly_savings_inr']:,.0f}.")
    else:
        parts.append("No major savings opportunity flagged on this trip.")
    return " ".join(parts)


def _rule_route_quality(p: Dict) -> str:
    eff = p.get("efficiency") or {}
    zones = p.get("speed_zones") or {}
    bt = p.get("backtrack_count") or 0
    eff_pct = (eff.get("route_efficiency") or 0) * 100
    interp = eff.get("interpretation") or "Unknown"
    slow = zones.get("slow_zone_pct") or 0
    high = zones.get("high_zone_pct") or 0
    cons = zones.get("speed_consistency") or "Moderate"
    s1 = f"Route efficiency was {eff_pct:.0f}% ({interp.lower()})."
    s2 = (f"Speed profile spent {slow:.0f}% in the slow zone (<20 km/h) and "
          f"{high:.0f}% in the high zone (≥80 km/h); consistency rated {cons}.")
    s3 = (f"{bt} backtracking events suggest reroute opportunities." if bt > 0
          else "No backtracking events were detected.")
    return " ".join([s1, s2, s3])


def _rule_traffic_callout(p: Dict) -> str:
    lost = p.get("time_lost_minutes") or 0
    dist = p.get("distance_in_traffic_km") or 0
    avg = p.get("avg_traffic_speed_kmph") or 0
    saved = p.get("time_saved_if_no_traffic_minutes") or 0
    if lost < 1:
        return "No significant traffic congestion was detected on this trip."
    return (f"The truck spent {lost:.0f} min covering {dist:.1f} km at congestion-level "
            f"speeds (avg {avg:.0f} km/h). Roughly {saved:.0f} min could have been saved "
            f"at free-flow speeds.")


def _rule_recommendations(p: Dict) -> str:
    opps = p.get("opportunities") or []
    if not opps:
        return "Operation is running clean — no high-impact recommendations for this trip."
    lines = []
    for o in opps:
        lines.append(
            f"• [{o['priority']}] {o['category']}: {o['recommendation']} "
            f"≈ ₹{o['monthly_savings_inr']:,.0f}/month."
        )
    return "\n".join(lines)


def _rule_comparison_verdict(p: Dict) -> str:
    rows = p.get("rows") or []
    if not rows:
        return "Not enough data to compare."
    by_overall = sorted(rows, key=lambda r: r.get("Overall Score", 0), reverse=True)
    best = by_overall[0]
    worst = by_overall[-1]
    cheap = min(rows, key=lambda r: r.get("Total Cost (₹)", 1e18))
    fast = min(rows, key=lambda r: r.get("Duration (hrs)", 1e18))
    return (
        f"Across {len(rows)} routes compared, '{best['Route']}' wins on the weighted "
        f"score (cost-40/time-30/eff-30). '{cheap['Route']}' is cheapest at "
        f"₹{cheap['Total Cost (₹)']:,.0f}; '{fast['Route']}' is fastest at "
        f"{fast['Duration (hrs)']:.1f} hrs. '{worst['Route']}' ranks last — "
        f"investigate idle time and detours."
    )
