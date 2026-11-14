"""The decision engine. Pure: no database, HTTP, clock reads or randomness.

Everything comes in through EngineInput, so the same input always gives the same output.
"""

from .pipeline import decide

__all__ = ["decide"]
