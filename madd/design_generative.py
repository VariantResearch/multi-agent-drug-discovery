"""The generative designer seat: a generative chemistry model
filling one seat in the design panel.

The design panel's other seats are language models proposing
structures in text. Generative chemistry models (REINVENT-style
samplers and their successors) are the other species of
designer the field fields: they sample molecules directly.
This module seats one in the panel through an
operator-configured endpoint, under the same discipline as
every other seat:

- The endpoint is named by MADD_GENERATIVE_URL. It accepts a
  JSON sampling request ({"n": samples, "brief": {...}}) and
  answers {"smiles": [...]} (a "samples" key or a bare list is
  also accepted). MADD_GENERATIVE_MODEL names the model for
  provenance (default "generative-endpoint"),
  MADD_GENERATIVE_TOKEN optionally supplies a bearer token,
  and MADD_GENERATIVE_N sets the sample count (default 16).
- No endpoint configured: the seat contributes no candidates
  and records that fact in the designer notes carried into the
  bundle. It never invents samples to fill the seat.
- Sampled molecules enter as ordinary candidates with
  design_tool "generative:<model>" and no claims: a sampler
  asserts nothing, so there is nothing to audit but the
  structures themselves, which pass through the same RDKit
  validation, candidate audit, and design gate as any
  model-proposed candidate. There is no softer path for them.
- Endpoint calls are metered by the operator's endpoint, not
  priced per call like provider completions, so they sit
  outside the run budget; the seat's note in the bundle says
  a call was made, and the sample count is recorded.

CompositeDesigner composes the seat with the model panel: it
is the designer run_design receives when a seat is configured.
"""
import json
import os
import urllib.request

ENV_URL = "MADD_GENERATIVE_URL"
ENV_MODEL = "MADD_GENERATIVE_MODEL"
ENV_TOKEN = "MADD_GENERATIVE_TOKEN"
ENV_N = "MADD_GENERATIVE_N"
DEFAULT_SAMPLES = 16
TIMEOUT_SECONDS = 120


def seat_configured() -> bool:
    """True when a generative endpoint is named in the
    environment."""
    return bool(os.environ.get(ENV_URL, "").strip())


def default_transport(url: str, payload: dict) -> tuple:
    """POST one sampling request, returning (status, parsed_or_
    text). Response JSON is returned parsed when it parses."""
    body = json.dumps(payload).encode()
    headers = {"Content-Type": "application/json"}
    token = os.environ.get(ENV_TOKEN, "").strip()
    if token:
        headers["Authorization"] = "Bearer " + token
    req = urllib.request.Request(url, data=body, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_SECONDS) as resp:
            raw = resp.read().decode("utf-8", "replace")
            status = resp.status
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8", "replace")
    try:
        return status, json.loads(raw)
    except Exception:
        return status, raw


def _samples_from(payload) -> list:
    """Extract the SMILES list from an endpoint answer in any of
    the accepted shapes; anything else yields no samples."""
    if isinstance(payload, dict):
        for key in ("smiles", "samples", "molecules"):
            value = payload.get(key)
            if isinstance(value, list):
                return [str(v) for v in value
                        if isinstance(v, str) and v.strip()]
        return []
    if isinstance(payload, list):
        return [str(v) for v in payload
                if isinstance(v, str) and v.strip()]
    return []


class GenerativeDesigner:
    """One design-panel seat filled by a generative endpoint."""

    def __init__(self, transport=None, url: str = None,
                 model: str = None, samples: int = None):
        """Bind the endpoint; defaults read the environment."""
        self.url = url if url is not None else os.environ.get(
            ENV_URL, "").strip()
        self.model = model or os.environ.get(
            ENV_MODEL, "").strip() or "generative-endpoint"
        if samples is None:
            try:
                samples = int(os.environ.get(ENV_N, "") or DEFAULT_SAMPLES)
            except ValueError:
                samples = DEFAULT_SAMPLES
        self.samples = samples
        self.transport = transport or default_transport
        self.name = "generative:" + self.model
        self.notes = []

    def design(self, brief: dict) -> list:
        """Sample candidates for one design brief. Returns
        candidate dicts in the design contract's normalized
        shape; an unconfigured or failing endpoint contributes
        none and records why in the notes."""
        if not self.url:
            self.notes.append(
                "generative seat: no endpoint configured (set "
                + ENV_URL + "); the seat contributed no candidates")
            return []
        payload = {"n": self.samples,
                   "brief": {"spec_id": brief.get("spec_id"),
                             "target": brief.get("target"),
                             "disease": brief.get("disease"),
                             "constraints": brief.get("constraints")}}
        try:
            status, answer = self.transport(self.url, payload)
        except Exception as exc:
            self.notes.append(
                "generative seat: sampling call failed: "
                + type(exc).__name__ + ": " + str(exc))
            return []
        if status != 200:
            self.notes.append(
                "generative seat: endpoint answered HTTP "
                + str(status) + "; the seat contributed no candidates")
            return []
        smiles = _samples_from(answer)
        self.notes.append(
            "generative seat: sampled " + str(len(smiles))
            + " molecule(s) from " + self.model
            + " (endpoint call metered outside the run budget)")
        out = []
        for i, value in enumerate(smiles):
            out.append({
                "artifact_type": "candidate",
                "schema_version": "0.1.0",
                "candidate_id": "generative-cand-" + str(i + 1),
                "spec_id": brief.get("spec_id"),
                "modality": "small_molecule",
                "design_tool": "generative:" + self.model,
                "description": ("sampled by " + self.model
                                + " from the configured generative "
                                "endpoint"),
                "structure": {"format": "smiles", "value": value},
                "claims": [],
                "predicted_properties": [],
                "constraint_results": [],
                "production_notes": {},
            })
        return out


class CompositeDesigner:
    """A designer composed of several designers: the union of
    their candidates, with names and notes combined. This is
    how the generative seat joins the model panel."""

    def __init__(self, designers):
        """Store the member designers."""
        self.designers = list(designers)
        self.name = "+".join(str(getattr(d, "name", "?"))
                             for d in self.designers)

    @property
    def notes(self):
        """The members' notes, concatenated in seat order."""
        out = []
        for designer in self.designers:
            out.extend(getattr(designer, "notes", []) or [])
        return out

    def design(self, brief: dict) -> list:
        """Ask every member for candidates and return the union."""
        out = []
        for designer in self.designers:
            out.extend(designer.design(brief) or [])
        return out


def with_generative_seat(designer, transport=None):
    """Return the designer joined with a generative seat when
    one is configured, else the designer unchanged."""
    if not seat_configured():
        return designer
    return CompositeDesigner([designer, GenerativeDesigner(
        transport=transport)])
