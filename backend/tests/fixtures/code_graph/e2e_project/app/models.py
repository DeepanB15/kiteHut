"""Data models for the E2E fixture application."""


class Record:
    """A simple record container."""

    class Meta:
        """Nested class exercising qualified-name nesting."""

        def describe(self):
            return "meta"

    def __init__(self, name):
        self.name = name

    def label(self):
        return self.name.upper()


class Registry:
    """Holds records and resolves them by name."""

    def __init__(self):
        self.records = {}

    def add(self, record):
        self.records[record.name] = record
        return record

    def resolve(self, name):
        return self.records.get(name)
