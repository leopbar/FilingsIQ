"""Fast, offline regression tests for Stage 9 multi-company behavior."""

import unittest
from unittest.mock import patch

from edgar_download import EdgarError, build_filing_manifest, normalize_ticker, strip_html
from filing_metadata import FilingMetadata
from search_filters import build_search_filter


class Stage9Tests(unittest.TestCase):
    def test_metadata_normalizes_sec_identity(self):
        metadata = FilingMetadata(
            " msft ",
            "Microsoft Corp",
            "789019",
            "10-k",
            "FY2025",
            "2025-07-30",
            "0000950170-25-100235",
            "https://www.sec.gov/example",
        )
        self.assertEqual(metadata.ticker, "MSFT")
        self.assertEqual(metadata.cik, "0000789019")
        self.assertEqual(metadata.form_type, "10-K")

    def test_ticker_validation(self):
        self.assertEqual(normalize_ticker(" brk.b "), "BRK.B")
        with self.assertRaises(EdgarError):
            normalize_ticker("bad ticker!")

    @patch("edgar_download.resolve_ticker")
    @patch("edgar_download._get_json")
    def test_manifest_has_filing_provenance(self, get_json, resolve_ticker):
        resolve_ticker.return_value = {
            "ticker": "MSFT",
            "company_name": "MICROSOFT CORP",
            "cik": "0000789019",
        }
        get_json.return_value = {
            "name": "MICROSOFT CORP",
            "filings": {
                "recent": {
                    "form": ["10-K", "8-K"],
                    "reportDate": ["2025-06-30", "2025-07-01"],
                    "filingDate": ["2025-07-30", "2025-07-31"],
                    "accessionNumber": ["0000950170-25-100235", "other"],
                    "primaryDocument": ["msft-20250630.htm", "other.htm"],
                }
            },
        }
        rows = build_filing_manifest("MSFT", 5)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["fiscal_year"], "FY2025")
        self.assertIn("000095017025100235", rows[0]["sec_url"])

    def test_company_and_year_filters_are_combined(self):
        self.assertEqual(
            build_search_filter("MSFT", "FY2025"),
            "ticker eq 'MSFT' and (fiscal_year eq 'FY2025' or "
            "(fiscal_year eq null and year eq 'FY2025'))",
        )
        self.assertIn("ticker eq null", build_search_filter("AAPL", None))

    def test_html_is_readable(self):
        text = strip_html("<p>Revenue &amp; income</p><script>ignore()</script><p>Next</p>")
        self.assertIn("Revenue & income", text)
        self.assertIn("Next", text)
        self.assertNotIn("ignore", text)


if __name__ == "__main__":
    unittest.main()
