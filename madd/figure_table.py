"""Figure and table evidence extraction from full-text XML.

The spike behind this module (2026-10-27) checked the JATS
full texts Europe PMC serves: clinical articles carried
structured table-wrap elements whose cell grids extract
mechanically and verbatim with the standard library (5 of 6
sampled articles, 12 tables), and figures carried rich
captions, while the figure graphics themselves are images.
So the extraction built here is exactly the part that holds:

- tables: label, caption, and the full cell grid, verbatim;
- figures: label and caption text, verbatim. The graphic is
  an image; its data is NOT extracted, and nothing here
  pretends otherwise. Reading values off a chart image
  would take vision tooling this system does not have.

Each table and each figure caption becomes an evidence
entry whose source id names it (PMCID:Table 1, PMCID:Fig.
2), rendered as plain lines a claim can quote and the quote
checker can verify against the same extraction. Nothing is
interpreted, summarised, or computed: a table with merged
or empty cells keeps them, empty where the source is empty.
"""
import xml.etree.ElementTree as ET


def _text_of(element) -> str:
    """All text under an element, whitespace-normalised."""
    if element is None:
        return ""
    return " ".join("".join(element.itertext()).split())


def extract_tables(xml_text: str) -> list:
    """Every table-wrap in a JATS document: label, caption,
    and rows of cell strings, in document order."""
    root = ET.fromstring(xml_text)
    tables = []
    for wrap in root.findall(".//table-wrap"):
        rows = []
        for tr in wrap.findall(".//tr"):
            row = [_text_of(cell) for cell in list(tr)
                   if cell.tag in ("td", "th")]
            if row:
                rows.append(row)
        tables.append({
            "label": _text_of(wrap.find("label")) or "Table",
            "caption": _text_of(wrap.find("caption")),
            "rows": rows,
            "n_rows": len(rows),
            "n_cols": max((len(r) for r in rows), default=0),
        })
    return tables


def extract_figures(xml_text: str) -> list:
    """Every fig in a JATS document: label and caption text.
    Graphics are images and are counted, never read."""
    root = ET.fromstring(xml_text)
    figures = []
    for fig in root.findall(".//fig"):
        figures.append({
            "label": _text_of(fig.find("label")) or "Figure",
            "caption": _text_of(fig.find("caption")),
            "has_graphic": fig.find(".//graphic") is not None,
        })
    return figures


def evidence_entries(pmcid: str, xml_text: str) -> list:
    """Evidence entries for one article's tables and figure
    captions, in the shape the retrieval layer carries: a
    source id naming the exact table or figure, and the
    verbatim text a claim may quote."""
    entries = []
    for table in extract_tables(xml_text):
        lines = []
        if table["caption"]:
            lines.append(table["caption"])
        lines.extend(" | ".join(row) for row in table["rows"])
        entries.append({
            "source_id": str(pmcid) + ":" + table["label"],
            "kind": "table",
            "label": table["label"],
            "text": "\n".join(lines),
            "n_rows": table["n_rows"],
            "n_cols": table["n_cols"],
        })
    for figure in extract_figures(xml_text):
        if not figure["caption"]:
            continue
        entries.append({
            "source_id": str(pmcid) + ":" + figure["label"],
            "kind": "figure_caption",
            "label": figure["label"],
            "text": figure["caption"],
            "graphic_extracted": False,
        })
    return entries
