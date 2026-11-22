"""Core module: same-module and imported calls."""

from pkg.util import helper


def run():
    return 1


def main():
    # Bare-name call with a unique same-module binding: resolves to run().
    return run()


def imported_call():
    # Imported alias: resolved imports are emitted, but the call itself is
    # left unresolved by the conservative bare-name resolver.
    return helper()


class Runner:
    def go(self):
        return run()
