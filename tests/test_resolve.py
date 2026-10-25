"""Live citation resolver tests, run offline against a fake transport.

The response bodies are invented fixtures shaped like the real registry
responses. They test the resolver plumbing only. The live endpoints
themselves are exercised separately by a manual probe, not by this
suite, so the suite never depends on a network.
"""
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from madd.resolve import resolve_document, resolve_identifier

PMID_BODY = json.dumps({"result": {"uids": ["28304224"],
                                   "28304224": {"title": "Invented Article Title."}}})
DOI_BODY = json.dumps({"message": {"title": ["Invented DOI Title"]}})
NCT_BODY = json.dumps({"protocolSection": {"identificationModule":
                                           {"briefTitle": "Invented Trial Title"}}})


class FakeFetcher:
    """Fake registry fetcher returning canned responses."""
    def __init__(self, routes):
        """Initialize the test double."""
        self.routes = routes
        self.urls = []

    def __call__(self, url):
        """Act as the callable test double."""
        self.urls.append(url)
        for needle, response in self.routes:
            if needle in url:
                if isinstance(response, Exception):
                    raise response
                return response
        return 404, ""


class TestResolveIdentifier(unittest.TestCase):
    """Tests for resolve identifier."""
    def test_pmid_resolved(self):
        """Pmid resolved."""
        fetch = FakeFetcher([("esummary", (200, PMID_BODY))])
        result = resolve_identifier("28304224", "pmid", fetcher=fetch)
        self.assertEqual(result["status"], "resolved")
        self.assertEqual(result["title"], "Invented Article Title.")
        self.assertEqual(result["registry"], "eutils.ncbi.nlm.nih.gov")

    def test_pmid_not_found(self):
        """Pmid not found."""
        fetch = FakeFetcher([("esummary", (200, json.dumps({"result": {"uids": []}})))])
        result = resolve_identifier("99999999", "pmid", fetcher=fetch)
        self.assertEqual(result["status"], "not_found")

    def test_doi_resolved_and_404(self):
        """Doi resolved and 404."""
        fetch = FakeFetcher([("crossref", (200, DOI_BODY))])
        result = resolve_identifier("10.1000/invented.1", "doi", fetcher=fetch)
        self.assertEqual(result["status"], "resolved")
        self.assertEqual(result["title"], "Invented DOI Title")
        fetch404 = FakeFetcher([("crossref", (404, ""))])
        result404 = resolve_identifier("10.1000/invented.2", "doi", fetcher=fetch404)
        self.assertEqual(result404["status"], "not_found")

    def test_nct_resolved(self):
        """Nct resolved."""
        fetch = FakeFetcher([("clinicaltrials", (200, NCT_BODY))])
        result = resolve_identifier("NCT01764633", "nct", fetcher=fetch)
        self.assertEqual(result["status"], "resolved")
        self.assertEqual(result["title"], "Invented Trial Title")

    def test_format_invalid_never_touches_network(self):
        """Format invalid never touches network."""
        def boom(url):
            """Raise, simulating a transport failure."""
            raise AssertionError("network must not be called for a bad format")
        result = resolve_identifier("not-a-pmid", "pmid", fetcher=boom)
        self.assertEqual(result["status"], "format_invalid")
        result = resolve_identifier("123", "isbn", fetcher=boom)
        self.assertEqual(result["status"], "unknown_type")

    def test_transport_failure_is_lookup_error_not_not_found(self):
        """Transport failure is lookup error not not found."""
        fetch = FakeFetcher([("esummary", ConnectionError("no route"))])
        result = resolve_identifier("28304224", "pmid", fetcher=fetch)
        self.assertEqual(result["status"], "lookup_error")

    def test_http_500_is_lookup_error(self):
        """Http 500 is lookup error."""
        fetch = FakeFetcher([("esummary", (500, "server error"))])
        result = resolve_identifier("28304224", "pmid", fetcher=fetch)
        self.assertEqual(result["status"], "lookup_error")

    def test_resolve_document_counts(self):
        """Resolve document counts."""
        fetch = FakeFetcher([("esummary", (200, PMID_BODY)),
                             ("crossref", (404, ""))])
        doc = {"claims": [
            {"claim_id": "C1", "source_identifier": "28304224", "identifier_type": "pmid"},
            {"claim_id": "C2", "source_identifier": "10.1000/invented.9",
             "identifier_type": "doi"},
            {"claim_id": "C3", "source_identifier": "bad", "identifier_type": "pmid"},
        ]}
        report = resolve_document(doc, fetcher=fetch)
        self.assertEqual(report["claim_count"], 3)
        self.assertEqual(report["status_counts"],
                         {"resolved": 1, "not_found": 1, "format_invalid": 1})


if __name__ == "__main__":
    unittest.main()
