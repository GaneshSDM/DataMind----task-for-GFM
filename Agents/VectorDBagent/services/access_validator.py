"""
Domain access validation for RAVEN.

Two-layer access control:
  Layer 1 (in-memory): domain name match against security_profile.domains
  Layer 2 (DB):        file existence + category-to-domain authorization
                       via tracopp.rag_files → rag_sub_category → rag_category

Both layers must pass for an unstructured intent to proceed to embedding.
"""
import logging
import re

from services.db import verify_file_authorized

logger = logging.getLogger("raven.access_validator")


def is_domain_allowed(intent_domain: str, security_profile: dict) -> bool:
    """
    Return True if intent_domain matches any domain in security_profile.domains.
    Case-insensitive name match.
    If security_profile carries no domains list, allow all (no restriction configured).
    """
    domains = security_profile.get("domains", [])
    if not domains:
        return True  # no domain restriction — allow all
    intent_lower = intent_domain.lower()
    for d in domains:
        if d.get("name", "").lower() == intent_lower:
            return True
    logger.debug("Domain '%s' not in allowed domains: %s", intent_domain, [d.get("name") for d in domains])
    return False


def extract_document_filter(unstructured_source: str | None) -> str | None:
    """
    Extract filename from ARIA's unstructured_source field.
    ARIA format: "filename.pdf — description text"
                 "filename.docx - some description"
    Returns the filename portion only, or None if not parseable / no extension found.
    """
    if not unstructured_source:
        return None
    # Split on em-dash, en-dash, or hyphen surrounded by spaces
    parts = re.split(r'\s+[—–\-]\s+', unstructured_source, maxsplit=1)
    filename = parts[0].strip()
    # Validate it looks like a real file (has a recognised extension)
    if re.search(r'\.\w{2,5}$', filename):
        return filename
    return None


def check_file_access(filename: str | None, domain_name: str) -> tuple[bool, str]:
    """
    Run Layer 2 DB authorization for a specific file.
    Returns (authorized: bool, reason: str).

    If filename is None (no document filter), allow — search is domain-scoped
    via ARIA's allowed_domain_ids already applied at retrieval time.
    """
    if not filename:
        return True, "no document filter — domain-scoped search allowed"

    authorized = verify_file_authorized(filename, domain_name)
    if authorized:
        return True, f"file '{filename}' authorized for domain '{domain_name}'"
    return False, f"file '{filename}' not found or not in domain '{domain_name}'"
