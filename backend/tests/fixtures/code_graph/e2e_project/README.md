# Code Graph E2E fixture

Committed fixture for the Phase 11.12 end-to-end evaluation. Tests copy this
tree into a temporary directory and never mutate the committed copy.

Coverage:

- multi-module package (`app`, `pkg_a`, `pkg_b`)
- nested classes/methods and nested functions
- module imports and `from ... import` statements
- duplicate bare symbol names and ambiguous imports
- shadowed and unresolved calls
- one intentionally unparseable module (`app/legacy_broken.py`) for partial builds
- an empty module and Unicode source
