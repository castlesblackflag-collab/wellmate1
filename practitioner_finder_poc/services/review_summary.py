"""
Conservative review summarization.

Summarizes review text briefly without fabrication.
"""

import re


def summarize_reviews(review_texts: list[str], max_length: int = 200) -> str | None:
    """Create a brief, conservative summary of review texts.

    Returns None if no reviews are available.
    Does not fabricate content.
    """
    if not review_texts:
        return None

    # Take up to 3 reviews, pick the most substantive ones
    sorted_reviews = sorted(review_texts, key=len, reverse=True)
    top_reviews = sorted_reviews[:3]

    snippets = []
    for review in top_reviews:
        snippet = _extract_snippet(review)
        if snippet:
            snippets.append(snippet)

    if not snippets:
        return None

    combined = " | ".join(snippets)
    if len(combined) > max_length:
        combined = combined[:max_length - 3] + "..."

    return combined


def _extract_snippet(review_text: str, max_snippet: int = 80) -> str:
    """Extract a meaningful snippet from a single review."""
    text = review_text.strip()
    if not text:
        return ""

    # Clean up excessive whitespace
    text = re.sub(r"\s+", " ", text)

    if len(text) <= max_snippet:
        return text

    # Try to cut at a sentence boundary
    sentences = re.split(r"[.!?]+", text)
    if sentences and len(sentences[0].strip()) > 10:
        snippet = sentences[0].strip()
        if len(snippet) <= max_snippet:
            return snippet

    # Otherwise truncate at word boundary
    truncated = text[:max_snippet]
    last_space = truncated.rfind(" ")
    if last_space > max_snippet // 2:
        truncated = truncated[:last_space]
    return truncated + "..."
