"""Shared metadata contract for SEC filing chunks stored in Azure AI Search."""

from dataclasses import dataclass


@dataclass(frozen=True)
class FilingMetadata:
    """Identity and provenance carried by every chunk from one SEC filing."""

    ticker: str
    company_name: str
    cik: str
    form_type: str
    fiscal_year: str
    filing_date: str
    accession_number: str
    sec_url: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "ticker", self.ticker.strip().upper())
        object.__setattr__(self, "cik", self.cik.strip().zfill(10))
        object.__setattr__(self, "form_type", self.form_type.strip().upper())

        required = {
            "ticker": self.ticker,
            "company_name": self.company_name,
            "cik": self.cik,
            "form_type": self.form_type,
            "fiscal_year": self.fiscal_year,
            "filing_date": self.filing_date,
            "accession_number": self.accession_number,
            "sec_url": self.sec_url,
        }
        missing = [name for name, value in required.items() if not value.strip()]
        if missing:
            raise ValueError(f"Missing filing metadata: {', '.join(missing)}")

    def as_search_fields(self) -> dict[str, str]:
        """Return field names exactly as stored on each Azure Search chunk."""
        return {
            "ticker": self.ticker,
            "company_name": self.company_name.strip(),
            "cik": self.cik,
            "form_type": self.form_type,
            "fiscal_year": self.fiscal_year.strip(),
            "filing_date": self.filing_date.strip(),
            "accession_number": self.accession_number.strip(),
            "sec_url": self.sec_url.strip(),
        }
