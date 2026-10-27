"""Panel presets: named panel shapes over the protocol modes.

A preset is a setup convenience, not a new protocol. Each preset
names exactly one of the protocol modes defined in madd/config.py
(simple, simple_judge, dual, dual_judge), together with the panel
shape that fields it: the topology in plain words, the minimum
panel size, whether a judge is required, and whether the
judge-swap stability experiment can run on it. A run config picks
a preset with its "preset" key; validation resolves the preset to
its mode, and the debate engine runs under exactly the semantics
that mode already has. Nothing here adds a mode, changes a mode,
or relaxes a mode's shape rules.

The topology vocabulary follows the panel-composition reference
recorded in docs/DESIGN-REFERENCES.md (the Swarms entry): who
works in parallel and who reviews whom. The implementation is
native to this package; no orchestration framework is involved
and none of the engine's guarantees (blinded inputs, sealed
outcomes, the mechanical citation audit) are delegated anywhere.
"""
from __future__ import annotations

PRESETS = {
    "solo": {
        "name": "solo",
        "mode": "simple",
        "label": "Solo panel",
        "topology": "single-model panel",
        "summary": "Every research agent runs on one and the same "
                   "model, and there is no judge.",
        "min_agents": 2,
        "judge_required": False,
        "judge_swap_supported": False,
    },
    "solo_judged": {
        "name": "solo_judged",
        "mode": "simple_judge",
        "label": "Solo panel with judge",
        "topology": "judged panel",
        "summary": "Every research agent runs on one model, and a "
                   "judge ranks the dossiers; the judge-swap "
                   "experiment can run.",
        "min_agents": 2,
        "judge_required": True,
        "judge_swap_supported": True,
    },
    "pair": {
        "name": "pair",
        "mode": "dual",
        "label": "Two-model panel",
        "topology": "two-model panel",
        "summary": "The research panel is split across two models, "
                   "and there is no judge.",
        "min_agents": 2,
        "judge_required": False,
        "judge_swap_supported": False,
    },
    "pair_judged": {
        "name": "pair_judged",
        "mode": "dual_judge",
        "label": "Two-model panel with judge",
        "topology": "judged two-model panel",
        "summary": "The research panel is split across two models, "
                   "and a judge ranks the dossiers; the judge-swap "
                   "experiment can run.",
        "min_agents": 2,
        "judge_required": True,
        "judge_swap_supported": True,
    },
}


def list_presets() -> list:
    """Return every preset as a list of dicts, in registry order."""
    return [dict(PRESETS[name]) for name in PRESETS]


def get_preset(name) -> dict:
    """Return the preset registered under name.

    Raises ValueError naming the valid preset names when name is
    not one of them.
    """
    if name not in PRESETS:
        raise ValueError("unknown preset " + repr(name)
                         + "; valid presets: "
                         + ", ".join(sorted(PRESETS)))
    return dict(PRESETS[name])
