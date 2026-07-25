"""Retrieval-augmented historical context for ticket explanations.

Retrieval: query the AS-adjacency knowledge graph (netpath.kg) for segments
of the current AS path with a track record of trouble across other targets.

Generation: optionally phrase those retrieved facts as prose via a
locally-authenticated AI CLI (netpath.llm_cli), grounded strictly in what
retrieval returned — the model is never the source of a fact, only its
wording. Generation is a polish layer, not a dependency: retrieval alone
already produces a correct, deterministic sentence, so a missing or
misbehaving CLI degrades prose quality, never accuracy.
"""

from __future__ import annotations

import json
from typing import Any

from netpath import kg, llm_cli

_NARRATIVE_SCHEMA = {
    "type": "object",
    "properties": {
        "narrative": {"type": "string"},
    },
    "required": ["narrative"],
    "additionalProperties": False,
}

_PROMPT_TEMPLATE = (
    "You are drafting one short sentence of historical context for a network "
    "incident ticket. Using ONLY the facts below — never any outside "
    "knowledge — describe what the knowledge graph has observed about this "
    "path before. Do not invent ASNs, dates, rates, or observation counts "
    "that are not listed. If the facts list is empty, say plainly that no "
    "prior history was found for this path.\n\n"
    "Facts (JSON): {facts}"
)


def retrieve_segment_facts(as_path: list[str], store_path: str | None = None) -> list[dict[str, Any]]:
    """The retrieval step: known-bad AS-to-AS segments this path crosses."""
    graph = kg.build_graph(store_path)
    return kg.flag_known_bad_segments(graph, as_path)


def _deterministic_narrative(facts: list[dict[str, Any]]) -> str:
    if not facts:
        return "No prior history for this path in the knowledge graph."
    parts = [
        f"{fact['upstream']} → {fact['downstream']} showed degraded performance in "
        f"{fact['degraded_rate']:.0%} of {fact['observations']} prior diagnoses of other targets"
        for fact in facts
    ]
    return "; ".join(parts) + "."


def historical_context(
    as_path: list[str],
    *,
    provider: str | None = None,
    store_path: str | None = None,
) -> str:
    """Grounded historical-context sentence for a ticket, from graph facts alone.

    Always returns a correct, deterministic sentence built directly from the
    graph. If `provider` ("claude" or "codex") is given and available, that
    sentence is additionally phrased as prose by the CLI — but the CLI is
    never the source of any fact, only its wording, and any failure falls
    straight back to the deterministic sentence.
    """
    facts = retrieve_segment_facts(as_path, store_path)
    fallback = _deterministic_narrative(facts)
    if not provider:
        return fallback

    prompt = _PROMPT_TEMPLATE.format(facts=json.dumps(facts, sort_keys=True))
    generated = llm_cli.run_schema_constrained(provider, prompt, _NARRATIVE_SCHEMA)
    narrative = generated.get("narrative") if generated else None
    if isinstance(narrative, str) and narrative.strip():
        return narrative.strip()
    return fallback
