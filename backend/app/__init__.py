"""Application package for the Tribe Cockpit backend.

This marks ``backend/app`` as an importable Python package. It intentionally
stays empty (no import side effects) so that submodules such as ``config``,
``database``, ``models`` and ``security`` can be imported in any order without
triggering circular imports at package-load time.
"""
