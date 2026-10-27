"""Full-text retrieval tiers: evidence that carries the text
itself, in chunks agents can quote.

The base retrieval tier supplies identifiers and titles: an
agent may cite a source but can only quote what it separately
remembers, and the quote checker then does the grounding
alone. These tiers grow the evidence set itself to open-access
full texts, chunked, so a supporting quote can come from the
supplied text and be checked against a named chunk's source:

- abstract (the default, unchanged): identifiers and titles
  from the Europe PMC search, exactly as retrieval has always
  supplied them.
- concise: the search's top articles, up to 3 with open full
  text fetched and chunked (at most 8 chunks each).
- deep: up to 10 articles with full text, at most 40 chunks
  each, from a wider search.

The tiers are selectable per run (the retrieval_tier config
key or the target-run flag) and priced by preflight: the
estimate names the tier's fetch caps before a run spends
anything. An article with no open full text at Europe PMC is
recorded abstract_only: the tier never fabricates text, and
paywalled is a statement about availability, not quality.
Chunk text is the deposited article text with markup removed;
it is supplied for quoting, and the quote checker still
verifies every quote against the source independently.
"""
import html as _html
import re

from .resolve import fetch_full_text
from .retrieval import (evidence_from_records, frame_query,
                        retrieve_evidence, search_europepmc)

TIERS = {
    "abstract": {"search_limit": 10, "articles": 0, "chunks": 0},
    "concise": {"search_limit": 10, "articles": 3, "chunks": 8},
    "deep": {"search_limit": 25, "articles": 10, "chunks": 40},
}
CHUNK_CHARS = 1200
CHUNK_OVERLAP = 200


def tier_caps(tier: str) -> dict:
    """The fetch caps of one tier; unknown tiers raise."""
    if tier not in TIERS:
        raise ValueError("unknown retrieval tier " + repr(tier)
                         + "; expected one of "
                         + ", ".join(sorted(TIERS)))
    return TIERS[tier]


def xml_to_text(xml: str) -> str:
    """Reduce JATS XML to readable plain text: tags out,
    entities decoded, whitespace collapsed. Case is preserved,
    unlike the quote checker's comparison form."""
    text = re.sub(r"<[^>]+>", " ", xml or "")
    return " ".join(_html.unescape(text).split())


def chunk_text(text: str, size: int = CHUNK_CHARS,
               overlap: int = CHUNK_OVERLAP) -> list:
    """Split text into overlapping chunks, breaking at spaces
    where possible. Returns the chunk strings in order."""
    text = text or ""
    chunks = []
    start = 0
    while start < len(text):
        end = min(len(text), start + size)
        if end < len(text):
            space = text.rfind(" ", start + size // 2, end)
            if space > start:
                end = space
        chunks.append(text[start:end].strip())
        if end >= len(text):
            break
        start = max(start + 1, end - overlap)
    return [chunk for chunk in chunks if chunk]


def _entry_for(record: dict):
    """The evidence entry for one search record, mirroring
    retrieval's identifier choice and additionally carrying
    the record's PMCID and abstract for the tiers' use."""
    entries = evidence_from_records([record])
    if not entries:
        return None
    entry = entries[0]
    if record.get("pmcid"):
        entry["pmcid"] = str(record["pmcid"])
    if record.get("abstractText"):
        entry["abstract"] = str(record["abstractText"])
    return entry


def retrieve_tiered_evidence(frame: dict, tier: str = "abstract",
                             fetcher=None) -> list:
    """The evidence set for one frame at one retrieval tier.

    Abstract tier returns the base retrieval unchanged. The
    full-text tiers search, then fetch and chunk open full
    texts for up to the tier's article cap (in search order),
    recording each entry's full_text block or its
    abstract_only status.
    """
    caps = tier_caps(tier)
    if tier == "abstract" or caps["articles"] == 0:
        return retrieve_evidence(frame, fetcher=fetcher,
                                 limit=caps["search_limit"])
    query = frame_query(frame)
    if not query:
        return []
    records = search_europepmc(query, fetcher=fetcher,
                                limit=caps["search_limit"])
    entries = []
    fetched = 0
    for record in records:
        entry = _entry_for(record)
        if entry is None:
            continue
        if fetched < caps["articles"] and entry.get("pmcid"):
            xml = fetch_full_text(entry["pmcid"], fetcher=fetcher)
            if xml:
                chunks = chunk_text(xml_to_text(xml))
                kept = chunks[:caps["chunks"]]
                entry["full_text"] = {
                    "pmcid": entry["pmcid"],
                    "chunks": [{"chunk": i + 1, "text": chunk}
                               for i, chunk in enumerate(kept)],
                    "chunks_total": len(chunks),
                    "chunks_supplied": len(kept),
                    "truncated": len(kept) < len(chunks),
                }
                fetched += 1
            else:
                entry["full_text_status"] = "abstract_only"
        elif entry.get("pmcid"):
            entry["full_text_status"] = "not_attempted_tier_cap"
        else:
            entry["full_text_status"] = "abstract_only"
        entries.append(entry)
    return entries
