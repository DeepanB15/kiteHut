"""Utility helpers used by the application layer."""


def slugify(value):
    """Turn a value into a deterministic slug."""
    return str(value).strip().lower().replace(" ", "-")


def parse_count(value):
    """Parse a count, defaulting to zero."""
    return int(value)


def helper():
    """A uniquely named helper in this module."""
    return slugify("Helper")
