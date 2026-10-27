"""Proposal clustering: which dossiers are arguing the same
proposal?

A panel can fill with near-duplicate proposals: three agents
argue the same focus, in the same direction, on mostly the same
sources, and a per-dossier ranking then reads that as three
independent endorsements. Google's AI co-scientist clusters
hypotheses before its tournament for exactly this reason. This
module does it deterministically, with no model calls and no
tunable embeddings:

- Two dossiers merge when they propose the same focus in the
  same direction (the same proposal stated twice), or when
  their surviving load-bearing claims rest on substantially
  overlapping sources (Jaccard similarity of cited identifiers
  at or above 0.5) in the same direction: differently labelled
  proposals standing on the same evidence are near-duplicates.
- Direction is never merged across: advancing and killing the
  same focus are opposing proposals, not one cluster.
- Merging is union-find over those pairwise rules, so clusters
  are the connected components of the merge graph.

Each cluster records its member dossiers in ranking order, its
representative (the top-ranked member), the focus and direction
it argues, and the merge evidence: which rules fired and which
source identifiers at least two members share. Clusters feed
the tournament ratings (the tournament rates clusters, so
copies cannot outvote a distinct proposal merely by being
copies) and are recorded on the debate record whether or not
the tournament runs.
"""

OVERLAP_THRESHOLD = 0.5


def _sources(audited: dict) -> set:
    """The (identifier_type, identifier) pairs one audited
    dossier's surviving load-bearing claims cite."""
    pairs = set()
    for claim in audited.get("surviving_claims") or []:
        if not claim.get("load_bearing"):
            continue
        ident = claim.get("source_identifier")
        itype = claim.get("identifier_type")
        if ident and itype:
            pairs.add((str(itype).strip().lower(), str(ident).strip()))
    return pairs


def _jaccard(a: set, b: set) -> float:
    """Jaccard similarity of two sets; two empty sets are 0.0
    here, because sharing no evidence is not overlap."""
    union = a | b
    if not union:
        return 0.0
    return len(a & b) / len(union)


def cluster_dossiers(audited_dossiers: list, ranking: list = None) -> list:
    """Group audited dossiers into proposal clusters.

    ranking, when given, is debate.rank_dossiers' output and
    fixes member order and each cluster's representative; without
    it, dossiers keep their input order. Returns cluster dicts
    ordered by their representative's rank: cluster_id,
    focus_id, direction (the representative's), dossier_ids and
    agent_ids in rank order, size, near_duplicate (size above
    one), merge_basis (the rules that fired inside the cluster),
    and shared_sources (identifiers at least two members cite,
    as "type:id" strings)."""
    order = {a["dossier_id"]: index
             for index, a in enumerate(audited_dossiers)}
    if ranking:
        for index, summary in enumerate(ranking):
            if summary.get("dossier_id") in order:
                order[summary["dossier_id"]] = index
    members = sorted(audited_dossiers,
                     key=lambda a: order.get(a["dossier_id"], 0))
    sources = {a["dossier_id"]: _sources(a) for a in members}
    parent = {a["dossier_id"]: a["dossier_id"] for a in members}
    basis = {}

    def find(x):
        """Union-find root of one dossier id, with compression."""
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(x, y, rule):
        """Merge two dossiers' clusters, recording the rule."""
        rx, ry = find(x), find(y)
        if rx != ry:
            parent[ry] = rx
            basis.setdefault(rx, set()).update(basis.pop(ry, set()))
        basis.setdefault(rx, set()).add(rule)

    for i, a in enumerate(members):
        for b in members[i + 1:]:
            if a.get("direction") != b.get("direction"):
                continue
            if (a.get("proposed_focus_id") is not None
                    and a.get("proposed_focus_id")
                    == b.get("proposed_focus_id")):
                union(a["dossier_id"], b["dossier_id"], "same_focus")
            elif _jaccard(sources[a["dossier_id"]],
                          sources[b["dossier_id"]]) >= OVERLAP_THRESHOLD:
                union(a["dossier_id"], b["dossier_id"], "source_overlap")

    groups = {}
    for a in members:
        groups.setdefault(find(a["dossier_id"]), []).append(a)
    clusters = []
    for root, group in groups.items():
        group.sort(key=lambda a: order.get(a["dossier_id"], 0))
        representative = group[0]
        shared = set()
        for i, a in enumerate(group):
            for b in group[i + 1:]:
                shared |= (sources[a["dossier_id"]]
                           & sources[b["dossier_id"]])
        clusters.append({
            "cluster_id": None,
            "focus_id": representative.get("proposed_focus_id"),
            "direction": representative.get("direction"),
            "representative_dossier_id": representative["dossier_id"],
            "dossier_ids": [a["dossier_id"] for a in group],
            "agent_ids": [a.get("agent_id") for a in group],
            "size": len(group),
            "near_duplicate": len(group) > 1,
            "merge_basis": sorted(basis.get(root, set())),
            "shared_sources": sorted(t + ":" + i for t, i in shared),
        })
    clusters.sort(key=lambda c: order.get(c["representative_dossier_id"], 0))
    for index, cluster in enumerate(clusters, start=1):
        cluster["cluster_id"] = "CL-" + str(index)
    return clusters


def cluster_id_by_dossier(clusters: list) -> dict:
    """Map each clustered dossier id to its cluster id, for
    cross-referencing ranking entries and other records."""
    mapping = {}
    for cluster in clusters:
        for dossier_id in cluster["dossier_ids"]:
            mapping[dossier_id] = cluster["cluster_id"]
    return mapping
