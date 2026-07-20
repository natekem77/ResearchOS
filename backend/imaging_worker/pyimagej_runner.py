"""Future PyImageJ runner entry point.

The MVP executes server-allowlisted workflow facades and records Fiji discovery.
This module reserves the boundary where PyImageJ/Fiji calls can be added without
exposing arbitrary macros to Flutter.
"""

from __future__ import annotations


class PyImageJRunnerUnavailable(RuntimeError):
    pass

