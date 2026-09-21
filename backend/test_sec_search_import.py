"""Fast, offline tests for SEC company search and year-scoped imports."""

import unittest
from unittest.mock import patch

import edgar_download
from company_ingest import _company_filter
from edgar_download import EdgarError, build_filing_manifest, search_companies
from import_jobs import _validate_years

COMPANIES = [
    {"ticker": "AAPL", "company_name": "Apple Inc.", "cik": "0000320193"},
    {"ticker": "AAP", "company_name": "Advance Auto Parts, Inc.", "cik": "0001158449"},
    {"ticker": "MSFT", "company_name": "MICROSOFT CORP", "cik": "0000789019"},
    {"ticker": "PINE", "company_name": "Alpine Income Property Trust", "cik": "0001728205"},
]


class SearchTests(unittest.TestCase):
    def setUp(self):
        patcher = patch.object(edgar_download, "_company_rows", return_value=COMPANIES)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_exact_ticker_ranks_first(self):
        self.assertEqual(search_companies("aap")[0]["ticker"], "AAP")

    def test_name_prefix_beats_substring(self):
        tickers = [row["ticker"] for row in search_companies("a")]
        self.assertEqual(set(tickers[:2]), {"AAP", "AAPL"})
        self.assertLess(tickers.index("AAPL"), tickers.index("PINE"))

    def test_name_search_and_empty_query(self):
        self.assertEqual(search_companies("microsoft")[0]["ticker"], "MSFT")
        self.assertEqual(search_companies("   "), [])


class YearScopedImportTests(unittest.TestCase):
    def test_year_limit_is_two(self):
        self.assertEqual(_validate_years(["fy2024", "FY2025"]), ["FY2025", "FY2024"])
        with self.assertRaises(EdgarError):
            _validate_years(["FY2023", "FY2024", "FY2025"])
        with self.assertRaises(EdgarError):
            _validate_years([])

    def test_delete_filter_is_limited_to_selected_years(self):
        scoped = _company_filter("MSFT", ["FY2024"])
        self.assertIn("fiscal_year eq 'FY2024'", scoped)
        self.assertNotIn("FY2023", scoped)
        self.assertNotIn("fiscal_year", _company_filter("MSFT"))

    def test_apple_legacy_chunks_are_scoped_by_year(self):
        scoped = _company_filter("AAPL", ["FY2024"])
        self.assertIn("year eq 'FY2024'", scoped)

    def test_manifest_returns_only_requested_years(self):
        submissions = {
            "name": "Example Corp",
            "filings": {
                "recent": {
                    "form": ["10-K", "10-Q", "10-K", "10-K"],
                    "reportDate": ["2025-12-31", "2025-09-30", "2024-12-31", "2023-12-31"],
                    "accessionNumber": ["a-25", "q-25", "a-24", "a-23"],
                    "primaryDocument": ["a.htm", "q.htm", "b.htm", "c.htm"],
                    "filingDate": ["2026-02-01", "2025-11-01", "2025-02-01", "2024-02-01"],
                }
            },
        }
        company = {"ticker": "EXM", "company_name": "Example", "cik": "0000000001"}
        with patch.object(edgar_download, "resolve_ticker", return_value=company), patch.object(
            edgar_download, "_get_json", return_value=submissions
        ):
            manifest = build_filing_manifest("EXM", fiscal_years=["FY2025", "FY2023"])
            self.assertEqual([m["fiscal_year"] for m in manifest], ["FY2025", "FY2023"])
            with self.assertRaises(EdgarError):
                build_filing_manifest("EXM", fiscal_years=["FY2019"])


if __name__ == "__main__":
    unittest.main()
