"""Decode a Python bytes literal into the bytes it represents.

Supported input shape
---------------------
    decode(s) accepts a Python bytes literal exactly as you would type it in
    source code, e.g.

        b"hello\\n"
        b'\\x41'
        rb'\\\\'         # raw bytes: backslash is literal
        \"\\u0041\"        # a *str* literal also works; see below

The leading prefix may be any combination of ``b``/``r``/``u`` in either
order and either case, plus the standalone forms ``'...'`` and ``\"...\"``
(which we treat as str literals).  Triple-quoted forms are supported.

Escapes handled
---------------
    \\\\  \\'  \\"  \\a  \\b  \\f  \\n  \\r  \\t  \\v  \\0..\\377 (1-3 octal
    digits, capped at 0o377 per CPython)  \\xXX (exactly two hex digits)
    \\uXXXX (exactly four hex digits, low byte kept)  \\UXXXXXXXX (exactly
    eight hex digits, low byte kept)  \\N{NAME} (named unicode, low byte kept)

For str literals (no ``b`` prefix) the full code point is decoded to its
UTF-8 bytes, so ``\"\\u00e9\"`` gives ``b'\\xc3\\xa9'``.

Design choices
--------------
* Octal and hex are capped at one byte as CPython does for bytes literals.
  For ``\\u``/``\\U``/``\\N{}`` we intentionally diverge: bytes literals in
  real CPython raise ``ValueError`` for these, but users of this library
  almost always want to turn a str literal into bytes, so we take the low
  byte for ``b``-prefixed input and the UTF-8 of the full code point
  otherwise.  This is the one documented deviation; see README.
* We hand-roll the scanner instead of shelling out to ``ast.literal_eval``.
  ``literal_eval`` would reject ``\\N{...}`` on bytes literals and would
  evaluate real Python object syntax (tuple/list/dict), which is more power
  than this library promises and a footgun for callers feeding untrusted
  text.
"""

from __future__ import annotations

import unicodedata

__all__ = ["decode", "decode_inner", "DecodeError"]


class DecodeError(ValueError):
    """Raised when a bytes literal cannot be parsed.

    Subclasses ValueError so existing ``except ValueError`` handlers keep
    working, while still letting callers catch this specifically.
    """


# Single-char named escapes, mapping escape letter -> byte value.
_SIMPLE_ESCAPES = {
    "\\": 0x5C,
    "'": 0x27,
    '"': 0x22,
    "a": 0x07,
    "b": 0x08,
    "f": 0x0C,
    "n": 0x0A,
    "r": 0x0D,
    "t": 0x09,
    "v": 0x0B,
}


def _is_octal_digit(ch: str) -> bool:
    return "0" <= ch <= "7"


def _hex_value(ch: str) -> int:
    # Used only after we know ch is a hex digit, so ValueError is impossible.
    if "0" <= ch <= "9":
        return ord(ch) - ord("0")
    return 10 + (ord(ch.lower()) - ord("a"))


def _is_hex_digit(ch: str) -> bool:
    return (
        "0" <= ch <= "9"
        or "a" <= ch <= "f"
        or "A" <= ch <= "F"
    )


def _codepoint_to_utf8(cp: int) -> bytes:
    # chr() handles 0..0x10FFFF; below 0x80 it returns a single ASCII char so
    # we naturally get the "low byte" behaviour for small code points.
    return chr(cp).encode("utf-8")


def _parse_prefix_and_strip(s: str) -> tuple[bool, str]:
    """Pull off the optional prefix (b/r/u, any order, any case) and quotes.

    Returns (is_raw, inner).  Raises DecodeError on malformed quoting.
    """
    if not isinstance(s, str):
        raise DecodeError("input must be a str, got %r" % type(s).__name__)

    i = 0
    n = len(s)
    prefix_chars: list[str] = []
    while i < n and s[i] in "bBrRuU":
        prefix_chars.append(s[i].lower())
        i += 1

    # A prefix is only a prefix if immediately followed by a quote; otherwise
    # the whole thing is bare text ("abc") and we treat it as a str literal.
    if i >= n or s[i] not in "'\"":
        prefix_chars = []
        i = 0

    seen = set(prefix_chars)
    if len(seen) != len(prefix_chars):
        raise DecodeError("duplicated prefix character in %r" % s[:i])
    if "u" in seen and "b" in seen:
        # ``ub"..."`` is not a real Python literal; pick a clear error.
        raise DecodeError("conflicting 'u' and 'b' prefixes")

    is_raw = "r" in seen

    quote = s[i]
    # Triple-quoted forms: three identical quote chars.
    triple = s[i:i + 3] == quote * 3
    if triple:
        end_quote = quote * 3
        body_start = i + 3
    else:
        end_quote = quote
        body_start = i + 1

    if body_start > n:
        raise DecodeError("string ends immediately after opening quote")

    # Find the closing quote.  For triple-quoted strings we accept any
    # single-quote characters inside (CPython does too).
    if triple:
        end = s.find(end_quote, body_start)
        if end == -1:
            raise DecodeError("unterminated triple-quoted string")
        body = s[body_start:end]
        tail = s[end + 3:]
    else:
        # Scan char by char so backslash-escaped quotes don't terminate.
        j = body_start
        body_chars: list[str] = []
        closed = False
        while j < n:
            ch = s[j]
            if ch == "\\":
                # Keep the escape sequence verbatim in the body; the main
                # pass will interpret it (or, for raw strings, leave it).
                if j + 1 < n:
                    body_chars.append(s[j])
                    body_chars.append(s[j + 1])
                    j += 2
                    continue
                raise DecodeError("trailing backslash in literal")
            if ch == quote:
                closed = True
                break
            body_chars.append(ch)
            j += 1
        if not closed:
            raise DecodeError("unterminated string literal")
        body = "".join(body_chars)
        tail = s[j + 1:]

    if tail:
        raise DecodeError("unexpected trailing data after closing quote: %r" % tail)

    return is_raw, body


def decode_inner(inner: str, *, is_raw: bool = False, is_bytes: bool = True) -> bytes:
    """Decode a literal body that has already had quotes/prefix stripped.

    ``is_raw``  -- if True, backslashes are literal (raw string semantics).
    ``is_bytes``-- if True, ``\\u``/``\\U``/``\\N{}`` keep only the low byte
                   (bytes-literal style); if False, the full code point is
                   encoded as UTF-8 (str-literal style).
    """
    out = bytearray()
    i = 0
    n = len(inner)
    while i < n:
        ch = inner[i]
        if ch != "\\":
            out.extend(ch.encode("utf-8"))
            i += 1
            continue

        if is_raw:
            # Raw: keep backslash and next char verbatim.
            if i + 1 >= n:
                raise DecodeError("trailing backslash in raw literal")
            out.extend(b"\\")
            out.extend(inner[i + 1].encode("utf-8"))
            i += 2
            continue

        if i + 1 >= n:
            raise DecodeError("trailing backslash in literal")
        kind = inner[i + 1]
        i += 2

        if kind in _SIMPLE_ESCAPES:
            out.append(_SIMPLE_ESCAPES[kind])
            continue

        if _is_octal_digit(kind):
            # Up to three octal digits, first already consumed as ``kind``.
            digits = kind
            while len(digits) < 3 and i < n and _is_octal_digit(inner[i]):
                digits += inner[i]
                i += 1
            value = int(digits, 8)
            if value > 0o377:
                raise DecodeError("octal escape out of range for a byte: %s" % digits)
            out.append(value)
            continue

        if kind == "x":
            hexdigits = ""
            while len(hexdigits) < 2 and i < n and _is_hex_digit(inner[i]):
                hexdigits += inner[i]
                i += 1
            if len(hexdigits) != 2:
                raise DecodeError("\\x escape requires exactly two hex digits")
            out.append(int(hexdigits, 16))
            continue

        if kind == "u":
            hexdigits = ""
            while len(hexdigits) < 4 and i < n and _is_hex_digit(inner[i]):
                hexdigits += inner[i]
                i += 1
            if len(hexdigits) != 4:
                raise DecodeError("\\u escape requires exactly four hex digits")
            cp = int(hexdigits, 16)
            if is_bytes:
                out.append(cp & 0xFF)
            else:
                out.extend(_codepoint_to_utf8(cp))
            continue

        if kind == "U":
            hexdigits = ""
            while len(hexdigits) < 8 and i < n and _is_hex_digit(inner[i]):
                hexdigits += inner[i]
                i += 1
            if len(hexdigits) != 8:
                raise DecodeError("\\U escape requires exactly eight hex digits")
            cp = int(hexdigits, 16)
            if cp > 0x10FFFF:
                raise DecodeError("\\U escape out of range: %s" % hexdigits)
            if is_bytes:
                out.append(cp & 0xFF)
            else:
                out.extend(_codepoint_to_utf8(cp))
            continue

        if kind == "N":
            if i >= n or inner[i] != "{":
                raise DecodeError("\\N escape requires '{...}'")
            j = inner.find("}", i + 1)
            if j == -1:
                raise DecodeError("unterminated \\N{...} escape")
            name = inner[i + 1:j]
            if not name:
                raise DecodeError("empty \\N{} name")
            try:
                cp = ord(unicodedata.lookup(name))
            except KeyError:
                raise DecodeError("unknown unicode name %r" % name) from None
            i = j + 1
            if is_bytes:
                out.append(cp & 0xFF)
            else:
                out.extend(_codepoint_to_utf8(cp))
            continue

        raise DecodeError("unknown escape sequence: \\%s" % kind)

    return bytes(out)


def decode(s: str) -> bytes:
    """Decode a Python string/bytes literal into the bytes it represents.

    See the module docstring for the full grammar.
    """
    is_raw, body = _parse_prefix_and_strip(s)
    is_bytes = not _parse_prefix_and_strip_is_str(s)
    return decode_inner(body, is_raw=is_raw, is_bytes=is_bytes)


def _parse_prefix_and_strip_is_str(s: str) -> bool:
    """True if ``s`` has a ``u`` prefix or no prefix at all (a str literal)."""
    i = 0
    n = len(s)
    prefix = []
    while i < n and s[i] in "bBrRuU":
        prefix.append(s[i].lower())
        i += 1
    if i >= n or s[i] not in "'\"":
        prefix = []
    return ("u" in prefix) or (not prefix)
