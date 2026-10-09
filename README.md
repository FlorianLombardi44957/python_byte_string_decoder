# python-byte-string-decoder

Parses Python string literals (bytes and str forms) containing escape sequences, octal, hex, and named unicode escapes, and returns the bytes they represent.

```python
from python_byte_string_decoder import decode, decode_inner, DecodeError

decode('b"hello\\n"')            # b'hello\n'
decode('b"\\x41\\101\\N{LATIN CAPITAL LETTER A}"')  # b'AAA'
decode('"\\u00e9"')               # b'\xc3\xa9'  (str literal -> UTF-8)
decode('rb"\\n"')                 # b'\\n'       (raw: backslash literal)

decode_inner('a\\tb', is_raw=False, is_bytes=True)  # b'a\tb'
```

## Why this exists

You have text that *looks like* Python source — escape sequences and all — and you need the actual bytes without spinning up the Python tokenizer. `ast.literal_eval` is the obvious tool but it (a) rejects `\N{...}` on bytes literals and (b) evaluates arbitrary Python object syntax, which is more power than callers usually want when feeding untrusted text. This library is a focused, single-purpose scanner that handles exactly the escape forms Python string literals allow and nothing else.

## The one edge you will hit

For `b`-prefixed literals, real CPython raises `ValueError` on `\u`, `\U`, and `\N{...}` escapes — bytes literals may only contain bytes. This library deliberately diverges: on `b`-prefixed input those escapes keep only the **low byte** of the code point (`\u0041` → `b'A'`, `\u00e9` → `b'\xe9'`). On str literals (no `b` prefix, or an explicit `u`) the full code point is encoded as UTF-8 (`"\u00e9"` → `b'\xc3\xa9'`). If you need strict CPython bytes-literal semantics, this library is not that — use `ast.literal_eval` and catch its errors.

Octal escapes are capped at `\377` (one byte) and `\x` requires exactly two hex digits, matching CPython. Triple-quoted forms are supported; raw prefixes (`r`/`R`) disable escape processing entirely.
