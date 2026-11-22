"""Module combining duplicate imports and relative imports."""

from pkg_a.helper import helper
from pkg_b.helper import helper as helper_b


def combine():
    """Calls two imported names; imported aliases remain unresolved calls."""
    return helper(), helper_b()
