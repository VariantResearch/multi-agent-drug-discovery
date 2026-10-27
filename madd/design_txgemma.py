"""TxGemma property predictions for designed candidates.

TxGemma (Google's open therapeutic-models family, built on
Gemma and released under the Gemma Terms of Use) predicts drug
properties from a SMILES string in a chat format, covering
Therapeutics Data Commons tasks. Unlike ADMET-AI it is not a
local library call: it runs as a served model. This module is
the bridge to an operator-configured endpoint, in the same
shape as the ADMET-AI bridge:

- The endpoint is named by the MADD_TXGEMMA_URL environment
  variable (an HF Inference Endpoint or TGI-style text
  generation URL serving a TxGemma model), with an optional
  MADD_TXGEMMA_TOKEN sent as a bearer token. No endpoint
  configured means the tool reports not_configured and
  predicts nothing: the capability is real when an endpoint
  exists and honestly absent until then.
- Three tasks are asked per SMILES candidate, MADD's phrasing
  of the TDC task questions: Ames mutagenicity (Yes/No), hERG
  inhibition (Yes/No), and aqueous solubility (a number, log
  mol/L). Answers are parsed conservatively (the first
  standalone Yes/No, the first number); an unparseable answer
  is recorded as such and attaches no value.
- Predictions attach to predicted_properties with the basis
  "predicted:TxGemma" and verified False, exactly the grade
  ADMET-AI predictions carry: a named model's output, more
  than a designer's guess, never a measurement, and never
  evidence in the audit's path.
"""
import json
import os
import re
import urllib.request

TOOL_NAME = "TxGemma"
ENV_URL = "MADD_TXGEMMA_URL"
ENV_TOKEN = "MADD_TXGEMMA_TOKEN"
TIMEOUT_SECONDS = 60

TASKS = (
    {"name": "ames_mutagenicity", "kind": "classification",
     "question": ("predict whether this compound is mutagenic in "
                  "the Ames test. Answer with exactly Yes or No.")},
    {"name": "herg_inhibition", "kind": "classification",
     "question": ("predict whether this compound inhibits the "
                  "hERG potassium channel. Answer with exactly "
                  "Yes or No.")},
    {"name": "solubility_logS", "kind": "regression",
     "question": ("predict the aqueous solubility of this "
                  "compound as logS in log mol/L. Answer with "
                  "exactly one number.")},
)

_YES_NO_RE = re.compile(r"\b(yes|no)\b", re.IGNORECASE)
_NUMBER_RE = re.compile(r"-?\d+(?:\.\d+)?")


def endpoint_url() -> str | None:
    """The configured TxGemma endpoint URL, or None."""
    url = os.environ.get(ENV_URL, "").strip()
    return url or None


def _prompt(task: dict, smiles: str) -> str:
    """One task prompt in TxGemma's question-answer style."""
    return ("Question: Given the SMILES string " + smiles + ", "
            + task["question"] + "\nAnswer:")


def _parse_answer(task: dict, text):
    """Parse one generated answer conservatively. Classification
    tasks yield "Yes" or "No"; regression yields a float; an
    answer with neither yields None. Generated text that echoes
    the prompt is read after its final Answer: marker."""
    if not isinstance(text, str):
        return None
    tail = text.rsplit("Answer:", 1)[-1] if "Answer:" in text else text
    if task["kind"] == "classification":
        match = _YES_NO_RE.search(tail)
        if match:
            return "Yes" if match.group(1).lower() == "yes" else "No"
        return None
    match = _NUMBER_RE.search(tail)
    if match:
        try:
            return float(match.group(0))
        except ValueError:
            return None
    return None


def default_transport(url: str, prompt: str) -> tuple:
    """POST one text-generation request to the endpoint,
    returning (status, generated_text_or_body). The HF/TGI
    response shapes ([{"generated_text": ...}] or
    {"generated_text": ...}) are normalized to the text."""
    body = json.dumps({"inputs": prompt,
                       "parameters": {"max_new_tokens": 24,
                                      "do_sample": False}}).encode()
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
        payload = json.loads(raw)
    except Exception:
        return status, raw
    if isinstance(payload, list) and payload \
            and isinstance(payload[0], dict) \
            and "generated_text" in payload[0]:
        return status, str(payload[0]["generated_text"])
    if isinstance(payload, dict) and "generated_text" in payload:
        return status, str(payload["generated_text"])
    return status, raw


def predict_smiles(smiles: str, transport=None, url: str = None) -> dict:
    """Ask every task about one SMILES string. Returns
    {task_name: value_or_None} plus "_raw" answers for the
    record. Transport failures yield all-None values: a dead
    endpoint predicts nothing."""
    send = transport or default_transport
    target = url or endpoint_url()
    out = {}
    raw = {}
    for task in TASKS:
        try:
            status, text = send(target, _prompt(task, smiles))
        except Exception:
            status, text = None, None
        raw[task["name"]] = text if status == 200 else None
        out[task["name"]] = (_parse_answer(task, text)
                             if status == 200 else None)
    out["_raw"] = raw
    return out


def enrich_candidates(candidates: list, use: str = "research",
                      transport=None) -> dict:
    """Attach TxGemma predictions to every SMILES candidate.

    Mutates candidates in place (appends to predicted_properties
    with verified False) and returns the tool-run record.
    Statuses: completed, not_configured (no endpoint named),
    blocked_license, failed (the endpoint answered but nothing
    parseable came back for any candidate)."""
    from .license_registry import check_tool
    record = {"tool": TOOL_NAME, "kind": "predicted_properties",
              "requested": False, "status": "completed",
              "checked": 0, "predicted": 0, "unparseable": 0}
    verdict = check_tool(TOOL_NAME, use)
    record["license"] = verdict
    if not verdict.get("allowed"):
        record["status"] = "blocked_license"
        record["detail"] = verdict.get("reason") or "registry refusal"
        return record
    url = endpoint_url()
    if not url:
        record["status"] = "not_configured"
        record["detail"] = ("no TxGemma endpoint is configured (set "
                            + ENV_URL + " to a text-generation "
                            "endpoint serving TxGemma); no predictions "
                            "were made")
        return record
    record["endpoint"] = url.split("/")[2] if "//" in url else url
    owners = [c for c in candidates
              if (c.get("structure") or {}).get("format") == "smiles"
              and (c.get("structure") or {}).get("value")]
    record["checked"] = len(owners)
    for cand in owners:
        values = predict_smiles(cand["structure"]["value"],
                                transport=transport, url=url)
        props = cand.setdefault("predicted_properties", [])
        for task in TASKS:
            value = values.get(task["name"])
            if value is None:
                record["unparseable"] += 1
                continue
            props.append({"name": "txgemma:" + task["name"],
                          "value": value,
                          "basis": "predicted:TxGemma",
                          "verified": False})
            record["predicted"] += 1
    if owners and record["predicted"] == 0:
        record["status"] = "failed"
        record["detail"] = ("the configured endpoint answered but no "
                            "response could be parsed into a prediction")
    return record
