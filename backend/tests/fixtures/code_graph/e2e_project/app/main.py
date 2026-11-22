"""Application entry point tying modules together."""

import app.models
from app.service import Service, build_registry, nested_computation

DEFAULT_COUNT = 3


def main():
    """Run the fixture application pipeline."""
    registry = build_registry()
    service = Service(registry)
    total = nested_computation(DEFAULT_COUNT)
    return service.process(), total


if __name__ == "__main__":
    main()
