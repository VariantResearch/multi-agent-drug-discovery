"""Tests for figure/table evidence extraction, on a JATS
fixture modelled on the live spike (2026-10-27): structured
tables extract verbatim, figure captions extract with the
graphic honestly unextracted, and an article without either
yields no entries rather than an error."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from madd.figure_table import (evidence_entries, extract_figures,
                               extract_tables)

JATS = """<article xmlns:xlink="http://www.w3.org/1999/xlink"><body>
<sec><table-wrap id="T1"><label>Table 1</label>
<caption><p>Baseline characteristics.</p></caption>
<table><thead><tr><th>Variable</th><th>Control (n = 30)</th></tr></thead>
<tbody><tr><td>Age (years)</td><td>21.78 \u00b1 1.33</td></tr>
<tr><td>Female, n (%)</td><td>14 (46.7)</td></tr></tbody></table>
</table-wrap></sec>
<sec><fig id="F1"><label>Fig. 1</label>
<caption><p>MTCH2 and BAX are in close proximity during apoptosis.</p></caption>
<graphic xlink:href="fig1.jpg"/></fig></sec>
</body></article>"""

NO_TABLES = "<article><body><sec><p>Text only.</p></sec></body></article>"


def test_tables_extract_verbatim():
    """The grid comes out cell for cell, unicode intact."""
    tables = extract_tables(JATS)
    assert len(tables) == 1
    table = tables[0]
    assert table["label"] == "Table 1"
    assert table["caption"] == "Baseline characteristics."
    assert table["rows"][1] == ["Age (years)", "21.78 \u00b1 1.33"]
    assert table["n_rows"] == 3 and table["n_cols"] == 2


def test_figures_caption_only_graphic_flagged():
    """A figure yields its caption; the graphic is counted,
    and the entry records that it was not extracted."""
    figures = extract_figures(JATS)
    assert figures[0]["has_graphic"] is True
    entries = evidence_entries("PMC999", JATS)
    figure_entry = [e for e in entries if e["kind"] == "figure_caption"][0]
    assert figure_entry["source_id"] == "PMC999:Fig. 1"
    assert figure_entry["graphic_extracted"] is False
    assert "close proximity" in figure_entry["text"]


def test_table_entry_is_quotable():
    """A table entry's text carries the caption and the grid
    as quotable lines under a naming source id."""
    entries = evidence_entries("PMC999", JATS)
    table_entry = [e for e in entries if e["kind"] == "table"][0]
    assert table_entry["source_id"] == "PMC999:Table 1"
    assert "Age (years) | 21.78 \u00b1 1.33" in table_entry["text"]


def test_no_tables_no_entries():
    """An article with neither tables nor captioned figures
    yields an empty list, not an error or a fabrication."""
    assert evidence_entries("PMC0", NO_TABLES) == []
