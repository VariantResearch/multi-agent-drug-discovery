"""Open Targets Platform as an evidence source.

Open Targets integrates genetic, drug, literature, and other
evidence into target-disease association scores. This module
brings those associations into MADD under the same discipline
as every other source:

- A claim cites an association by one identifier,
  <ensembl target id>:<disease id> (for example
  ENSG00000109919:MONDO_0011122), with identifier_type
  "opentargets". Live resolution (wired into madd/resolve.py)
  re-queries the Platform's GraphQL API for exactly that pair;
  the association either exists there or the claim is struck,
  like any other registry claim.
- At framing time, a target run with a resolvable gene target
  and disease retrieves its association as a supplied evidence
  entry, so the panel cites the record the run itself fetched.

What an association score is and is not: it is the Platform's
own integration of its evidence types, reported here with its
per-datatype breakdown and the Platform named as the source. It
is not a primary measurement, and the evidence entries say so.

The API answers GraphQL over POST only (GET returns errors),
so this module carries its own small POST transport, injectable
for tests like the resolver's fetcher. Responses ride no cache:
association calls are few per run, and scores should be the
Platform's current ones.
"""
import json
import re
import urllib.request

API_URL = "https://api.platform.opentargets.org/api/v4/graphql"
USER_AGENT = "madd-resolver/0.1 (open-source research scaffold)"
TIMEOUT_SECONDS = 30

IDENTIFIER_RE = re.compile(
    r"^ENSG[0-9]{11}:(EFO|MONDO)_[0-9]{7}$")

_SEARCH = ('{ search(queryString: "%s", entityNames: ["%s"]) '
           '{ hits { id name entity } } }')
_ASSOCIATION = ('{ target(ensemblId: "%s") { id approvedSymbol '
                'associatedDiseases(Bs: ["%s"]) { rows { '
                'disease { id name } score '
                'datatypeScores { id score } } } } }')


def default_transport(query: str) -> tuple:
    """POST one GraphQL query to the Open Targets API, returning
    (status_code, body_text). Transport failures raise and are
    handled upstream."""
    body = json.dumps({"query": query}).encode("utf-8")
    req = urllib.request.Request(
        API_URL, data=body,
        headers={"User-Agent": USER_AGENT,
                 "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_SECONDS) as resp:
            return resp.status, resp.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8", "replace")


def graphql(query: str, transport=None):
    """Run one GraphQL query; return its data dict, or None when
    the API errors, the transport fails, or the payload is not
    the expected shape. Never raises."""
    send = transport if transport is not None else default_transport
    try:
        status, body = send(query)
    except Exception:
        return None
    if status != 200:
        return None
    try:
        payload = json.loads(body)
    except Exception:
        return None
    if not isinstance(payload, dict) or payload.get("errors"):
        return None
    data = payload.get("data")
    return data if isinstance(data, dict) else None


def _gql_string(text: str) -> str:
    """Escape one value for a GraphQL string literal."""
    return str(text).replace("\\", "\\\\").replace('"', '\\"')


def search_entity(name: str, entity: str, transport=None):
    """Search the Platform for one target or disease by name.

    Returns the best hit as {id, name}: an exact case-insensitive
    name match wins, else the first hit (the API ranks by
    relevance). None when nothing is found."""
    data = graphql(_SEARCH % (_gql_string(name), entity),
                   transport=transport)
    if not data:
        return None
    hits = (data.get("search") or {}).get("hits") or []
    if not hits:
        return None
    wanted = str(name).strip().lower()
    for hit in hits:
        if str(hit.get("name") or "").strip().lower() == wanted:
            return {"id": hit["id"], "name": hit["name"]}
    first = hits[0]
    return {"id": first["id"], "name": first["name"]}


def association(ensembl_id: str, disease_id: str, transport=None):
    """The Platform's association record for one target-disease
    pair: {ensembl_id, symbol, disease_id, disease_name, score,
    datatype_scores}. None when the pair has no association."""
    data = graphql(_ASSOCIATION % (ensembl_id, disease_id),
                   transport=transport)
    if not data or not data.get("target"):
        return None
    target = data["target"]
    rows = (target.get("associatedDiseases") or {}).get("rows") or []
    if not rows:
        return None
    row = rows[0]
    return {"ensembl_id": target.get("id"),
            "symbol": target.get("approvedSymbol"),
            "disease_id": (row.get("disease") or {}).get("id"),
            "disease_name": (row.get("disease") or {}).get("name"),
            "score": row.get("score"),
            "datatype_scores": {entry["id"]: entry["score"]
                                for entry in row.get("datatypeScores")
                                or [] if entry.get("id")}}


def resolve_association(identifier, transport=None) -> dict:
    """Resolve one opentargets identifier in madd/resolve.py's
    result shape. The identifier either names a live association
    or it does not resolve; there is no softer outcome."""
    base = {"identifier": identifier, "identifier_type": "opentargets",
            "title": None, "registry": "api.platform.opentargets.org",
            "detail": "", "related": {}}
    if not isinstance(identifier, str) or not IDENTIFIER_RE.match(identifier):
        return dict(base, status="format_invalid",
                    detail="identifier is not an Ensembl:disease pair")
    ensembl_id, disease_id = identifier.split(":", 1)
    try:
        record = association(ensembl_id, disease_id, transport=transport)
    except Exception as exc:
        return dict(base, status="lookup_error",
                    detail="Open Targets lookup failed: "
                           + type(exc).__name__ + ": " + str(exc))
    if record is None:
        return dict(base, status="not_found",
                    detail="Open Targets holds no association for this "
                           "target-disease pair")
    title = ((record.get("symbol") or ensembl_id) + " - "
             + (record.get("disease_name") or disease_id)
             + " association (Open Targets)")
    return dict(base, status="resolved", title=title,
                related={"association_score": record.get("score"),
                         "datatype_scores": record.get("datatype_scores"),
                         "symbol": record.get("symbol"),
                         "disease_name": record.get("disease_name")},
                detail="association exists in Open Targets; score and "
                       "datatype breakdown as recorded there")


def evidence_for_frame(frame: dict, transport=None) -> list:
    """Build the Open Targets evidence entry for one frame.

    The frame's gene-like target token and its disease are
    resolved through the Platform's search; when both resolve
    and an association exists, one entry is returned carrying
    the citable identifier and the score breakdown. Any failure
    along the way returns an empty list: missing Open Targets
    evidence is reported as absent, never padded."""
    target_text = str(frame.get("target") or frame.get("target_name")
                      or "").strip()
    disease_text = str(frame.get("disease") or "").strip()
    if not target_text or not disease_text:
        return []
    symbol = target_text.replace("(", " ").replace(")", " ").split()[0]
    target_hit = search_entity(symbol, "target", transport=transport)
    if target_hit is None:
        return []
    disease_hit = search_entity(disease_text, "disease",
                                transport=transport)
    if disease_hit is None:
        return []
    record = association(target_hit["id"], disease_hit["id"],
                         transport=transport)
    if record is None:
        return []
    identifier = str(record["ensembl_id"]) + ":" + str(record["disease_id"])
    if not IDENTIFIER_RE.match(identifier):
        return []
    return [{
        "source_identifier": identifier,
        "identifier_type": "opentargets",
        "title": ((record.get("symbol") or symbol) + " - "
                  + (record.get("disease_name") or disease_text)
                  + " association (Open Targets)"),
        "source_kind": "association_record",
        "registry": "Open Targets",
        "association": {"score": record.get("score"),
                        "datatype_scores": record.get("datatype_scores"),
                        "note": ("association score integrated by the "
                                 "Open Targets Platform from its "
                                 "evidence types; not a primary "
                                 "measurement")},
    }]
