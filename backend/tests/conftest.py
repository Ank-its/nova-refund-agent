"""Shared test configuration.

DB-isolation fixtures live in test_agent_integration.py so the pure-unit rule
tests (test_rules.py) run with no database and no async event loop at all.
"""
