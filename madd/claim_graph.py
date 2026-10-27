"""Claim graph: sources, claims, and the specification as a graph.

Builds the Cytoscape.js element lists the console renders for one
debate record: one node per cited source, one per claim (in the
specification, contested, or struck), and the specification itself;
edges run claim to source (cites) and claim to specification (in
spec / contested). Node data carries what the tap-to-inspect panel
shows: claim text, supporting quote, verification status, and, for
struck claims, the recorded strike reasons.

Honesty limits, kept in the data: strike entries record a claim id,
its dossier, and its reasons, but not the claim's text or source, so
struck nodes carry only what the record carries. Edge labels say
"cites" and "in spec" because that is what the record establishes;
nothing here asserts a claim supports a conclusion. Past the
aggregation threshold, struck claims collapse into one node per
reason signature so a large audit stays readable; surviving and
contested claims are never aggregated.
"""

AGGREGATE_THRESHOLD = 150


def _source_node(identifier, identifier_type):
    """The graph node for one cited source."""
    node_id = f"src:{identifier_type}:{identifier}"
    return {"data": {"id": node_id, "kind": "source",
                     "label": f"{identifier_type} {identifier}",
                     "identifier": identifier,
                     "identifier_type": identifier_type}}


def build_claim_graph(record, aggregate_threshold=AGGREGATE_THRESHOLD):
    """The graph elements of one debate record.

    Returns {"nodes": [...], "edges": [...], "aggregated_struck":
    n} in Cytoscape.js element shape. Struck claims beyond the
    threshold collapse by their sorted reason signature; the count
    of collapsed claims is reported, never hidden.
    """
    spec = record.get("spec") or {}
    nodes = {}
    edges = []

    def add_node(node):
        """Insert a node once, keyed by its id."""
        nodes.setdefault(node["data"]["id"], node)

    spec_id = "spec:" + str(spec.get("spec_id") or "spec")
    add_node({"data": {"id": spec_id, "kind": "spec",
                       "label": "Specification",
                       "outcome": spec.get("outcome")}})

    def add_claim(claim, status):
        """Add one surviving or contested claim, its source, edges."""
        claim_id = str(claim.get("claim_id") or "?")
        node_id = "claim:" + claim_id
        add_node({"data": {
            "id": node_id, "kind": "claim", "status": status,
            "label": claim_id,
            "text": claim.get("text"),
            "quote": claim.get("supporting_quote"),
            "verification": claim.get("verification_status"),
            "load_bearing": claim.get("load_bearing"),
        }})
        identifier = claim.get("source_identifier")
        if identifier:
            source = _source_node(str(identifier),
                                  str(claim.get("identifier_type")
                                      or ""))
            add_node(source)
            edges.append({"data": {
                "id": f"{node_id}->cite",
                "source": node_id, "target": source["data"]["id"],
                "label": "cites"}})
        edges.append({"data": {
            "id": f"{node_id}->spec",
            "source": node_id, "target": spec_id,
            "label": "in spec" if status == "in_spec" else status}})

    for claim in spec.get("claims") or []:
        if isinstance(claim, dict):
            add_claim(claim, "in_spec")
    for claim in spec.get("contested_claims") or []:
        if isinstance(claim, dict):
            add_claim(claim, "contested")

    strikes = [s for s in record.get("strike_list") or []
               if isinstance(s, dict)]
    aggregated = 0
    if len(strikes) > aggregate_threshold:
        by_signature = {}
        for entry in strikes:
            signature = tuple(sorted(entry.get("reasons") or []))
            by_signature.setdefault(signature, 0)
            by_signature[signature] += 1
        for signature, count in sorted(by_signature.items()):
            label = ("struck x" + str(count) + " ("
                     + ", ".join(signature) + ")")
            add_node({"data": {
                "id": "struck-agg:" + "|".join(signature),
                "kind": "claim", "status": "struck",
                "label": label, "count": count,
                "reasons": list(signature),
                "text": (f"{count} struck claims sharing the "
                         "recorded reasons "
                         + ", ".join(signature) + "."),
            }})
            aggregated += count
    else:
        for entry in strikes:
            claim_id = str(entry.get("claim_id") or "?")
            # A strike is per dossier-claim instance: the same claim
            # id struck from two dossiers is two recorded strikes.
            node_id = ("claim:" + str(entry.get("dossier_id") or "?")
                       + ":" + claim_id)
            add_node({"data": {
                "id": node_id, "kind": "claim", "status": "struck",
                "label": claim_id,
                "reasons": entry.get("reasons") or [],
                "dossier": entry.get("dossier_id"),
                "text": ("Struck in the evidence call. The record "
                         "keeps the claim id, its dossier, and the "
                         "strike reasons; it does not carry the "
                         "struck claim's text or source."),
            }})
    return {"nodes": list(nodes.values()), "edges": edges,
            "aggregated_struck": aggregated}


def claim_graph_of_bundle(bundle):
    """The claim graph of a bundle's debate record, or None."""
    from .audit_flow import record_of_bundle
    record = record_of_bundle(bundle)
    if record is None:
        return None
    return build_claim_graph(record)
