"""Python byte string decoder.

Public surface:
    decode          -- turn a Python string *literal* (with its surrounding
                       quotes) into the bytes it represents.
    decode_inner    -- same, but the argument is already stripped of quotes
                       and prefix.
    DecodeError     -- raised on any malformed input.
"""

from .core import decode, decode_inner, DecodeError

__all__ = ["decode", "decode_inner", "DecodeError"]
