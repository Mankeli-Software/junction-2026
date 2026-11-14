"""The decision engine. Pure: no database, HTTP, clock reads or randomness.

The stub is replaced piece by piece by the real pipeline (Aku).
"""

from .stub import decide

__all__ = ["decide"]
