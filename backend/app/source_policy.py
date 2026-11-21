from urllib.parse import urlparse

OFFICIAL_SOURCE_DOMAINS = {
    "rbi.org.in", "npci.org.in", "mospi.gov.in", "data.gov.in",
    "imf.org", "worldbank.org", "oecd.org", "fred.stlouisfed.org",
}


def validate_official_source_url(value: str) -> str:
    parsed = urlparse((value or "").strip())
    host = (parsed.hostname or "").lower()
    allowed = any(host == domain or host.endswith("." + domain) for domain in OFFICIAL_SOURCE_DOMAINS)
    if parsed.scheme != "https" or not allowed:
        raise ValueError("Source URL must be HTTPS on an approved official statistics domain")
    return value.strip()
