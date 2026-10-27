"""PDF rendering of run reports, through WeasyPrint when installed.

The HTML report (madd/html_report.py) is the canonical rendering of
a run bundle; this bridge prints that same document to PDF for the
places a PDF travels better than a page - an email attachment, a
printed sheet, an archive. WeasyPrint is an optional dependency,
on the same pattern as RDKit: the package core stays standard
library only, the license registry is checked before any use
(WeasyPrint is BSD, allowed for research and commercial use), and
where the package is not installed the render reports
not_installed instead of producing anything lesser under the same
name. The PDF is a rendering of the bundle's report, never a
second source of numbers.
"""
from __future__ import annotations

import importlib.util

from . import license_registry
from .html_report import bundle_to_html

TOOL_NAME = "WeasyPrint"


def available() -> bool:
    """True when the weasyprint package is importable here."""
    return importlib.util.find_spec("weasyprint") is not None


def _weasyprint_writer(html: str) -> bytes:
    """Render one HTML document to PDF bytes with WeasyPrint."""
    from weasyprint import HTML
    return HTML(string=html).write_pdf()


def render_report_pdf(bundle: dict, use: str = "research",
                      writer=None) -> dict:
    """Render a run bundle's report as PDF.

    Returns {status: "completed", pdf: bytes} on success, or
    {status: "blocked_license" | "not_installed", reason} without
    producing a file. writer, when given, is a callable taking the
    report's HTML and returning PDF bytes; it exists so tests can
    exercise this contract without the optional dependency, and
    production callers leave it None to use WeasyPrint itself.
    """
    verdict = license_registry.check_tool(TOOL_NAME, use)
    if not verdict.get("allowed"):
        return {"status": "blocked_license",
                "reason": verdict.get("reason")
                or "registry does not allow this use",
                "license": verdict}
    if writer is None:
        if not available():
            return {"status": "not_installed",
                    "reason": "the weasyprint package is not installed "
                              "in this environment; the HTML report "
                              "remains available"}
        writer = _weasyprint_writer
    pdf = writer(bundle_to_html(bundle))
    return {"status": "completed", "pdf": pdf,
            "bytes": len(pdf), "license": verdict}
