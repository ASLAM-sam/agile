"""Validation package for the AgileAgent execution gate.

The QA gate runs real commands against the generated workspace to determine
whether a project actually builds, passes tests, and starts up correctly.

Modules:
  executor.py    — runs commands, captures output, returns results
  classifier.py  — parses command output into structured ValidationFailure objects
  repair_router  — maps failures to the responsible engineering agent
"""
