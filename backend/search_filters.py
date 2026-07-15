"""Pure helpers for safe Azure AI Search OData filters."""


def escape_filter(value: str) -> str:
    return value.replace("'", "''")


def build_search_filter(ticker: str | None, year: str | None) -> str | None:
    clauses: list[str] = []
    if ticker:
        normalized = ticker.strip().upper()
        escaped = escape_filter(normalized)
        if normalized == "AAPL":
            clauses.append(
                f"(ticker eq '{escaped}' or (ticker eq null and year ne 'upload'))"
            )
        else:
            clauses.append(f"ticker eq '{escaped}'")
    if year:
        escaped_year = escape_filter(year)
        if year == "upload":
            clauses.append("year eq 'upload'")
        else:
            clauses.append(
                f"(fiscal_year eq '{escaped_year}' or "
                f"(fiscal_year eq null and year eq '{escaped_year}'))"
            )
    return " and ".join(clauses) or None
