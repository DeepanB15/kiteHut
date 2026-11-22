"""Service layer exercising nested scopes, shadowing and duplicates."""

from app.models import Record, Registry
from app.util import parse_count, slugify


def build_registry():
    """Create a registry and populate it from a record."""
    registry = Registry()
    record = Record("Primary")
    registry.add(record)
    return registry


def nested_computation(value):
    """Nested functions with a unique, resolvable call chain."""

    def step_one(raw):
        return parse_count(raw) + 1

    def step_two(raw):
        return step_one(raw) * 2

    return step_two(value)


def shadowed(helper):
    """Calling a shadowed parameter must not resolve to an outer function."""
    return helper()


def unresolved():
    """Call an undefined name: leave it unresolved rather than guessing."""
    return missing_external_call()


def duplicate():
    """First definition of a duplicated top-level name."""
    return "first"


def duplicate():
    """Second definition of a duplicated top-level name."""
    return "second"


def calls_duplicate():
    """An ambiguous duplicate must not produce a CALLS edge."""
    return duplicate()


class Service:
    """A class with methods, nested helpers and attribute calls."""

    def __init__(self, registry):
        self.registry = registry

    def describe(self):
        return slugify("Service Description")

    def process(self):
        def normalize():
            return parse_count("7")

        return normalize()

    def call_method(self):
        return self.describe()
