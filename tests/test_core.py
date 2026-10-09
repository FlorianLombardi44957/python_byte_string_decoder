import unittest

from python_byte_string_decoder import decode, decode_inner, DecodeError


class TestSimple(unittest.TestCase):
    def test_plain_ascii_double(self):
        self.assertEqual(decode('"hello"'), b"hello")

    def test_plain_ascii_single(self):
        self.assertEqual(decode("'world'"), b"world")

    def test_bytes_prefix(self):
        self.assertEqual(decode('b"hi"'), b"hi")

    def test_bytes_prefix_single(self):
        self.assertEqual(decode("b'hi'"), b"hi")

    def test_uppercase_prefix(self):
        self.assertEqual(decode('B"hi"'), b"hi")

    def test_str_prefix(self):
        self.assertEqual(decode('u"hi"'), b"hi")

    def test_triple_quoted(self):
        self.assertEqual(decode('b"""line\nbreak"""'), b"line\nbreak")

    def test_triple_quoted_contains_single_quotes(self):
        self.assertEqual(decode('b"""it\'s ok"""'), b"it's ok")


class TestSimpleEscapes(unittest.TestCase):
    def test_each_simple_escape(self):
        cases = {
            "\\\\": b"\\",
            "\\'": b"'",
            '\\"': b'"',
            "\\a": b"\x07",
            "\\b": b"\x08",
            "\\f": b"\x0c",
            "\\n": b"\n",
            "\\r": b"\r",
            "\\t": b"\t",
            "\\v": b"\x0b",
        }
        for esc, expected in cases.items():
            with self.subTest(esc=esc):
                self.assertEqual(decode('b"%s"' % esc), expected)

    def test_escaped_quote_matches_opening(self):
        # Inside a single-quoted string, an escaped single quote is a literal.
        self.assertEqual(decode("b'it\\'s'"), b"it's")

    def test_unescaped_other_quote_is_literal(self):
        self.assertEqual(decode('b\'say \"hi\"\''), b'say "hi"')


class TestOctal(unittest.TestCase):
    def test_single_digit(self):
        self.assertEqual(decode('b"\\0"'), b"\x00")
        self.assertEqual(decode('b"\\7"'), b"\x07")

    def test_two_digits(self):
        self.assertEqual(decode('b"\\10"'), b"\x08")
        self.assertEqual(decode('b"\\77"'), b"\x3f")

    def test_three_digits(self):
        self.assertEqual(decode('b"\\100"'), b"\x40")
        self.assertEqual(decode('b"\\377"'), b"\xff")

    def test_three_digit_max_is_377(self):
        self.assertEqual(decode('b"\\377"'), b"\xff")

    def test_does_not_consume_fourth_digit(self):
        self.assertEqual(decode('b"\\1010"'), b"A0")

    def test_eight_is_not_octal(self):
        with self.assertRaises(DecodeError):
            decode('b"\\8"')


class TestHex(unittest.TestCase):
    def test_lower(self):
        self.assertEqual(decode('b"\\x41"'), b"A")

    def test_upper(self):
        self.assertEqual(decode('b"\\x4A"'), b"J")

    def test_zero(self):
        self.assertEqual(decode('b"\\x00"'), b"\x00")

    def test_ff(self):
        self.assertEqual(decode('b"\\xff"'), b"\xff")

    def test_requires_two_digits(self):
        with self.assertRaises(DecodeError):
            decode('b"\\xZ"')

    def test_requires_exactly_two_digits_short(self):
        with self.assertRaises(DecodeError):
            decode('b"\\xF"')


class TestUnicodeEscapesBytesMode(unittest.TestCase):
    # b-prefixed literals: keep only the low byte.
    def test_u_escape_low_byte(self):
        self.assertEqual(decode('b"\\u0041"'), b"A")

    def test_u_escape_requires_four(self):
        with self.assertRaises(DecodeError):
            decode('b"\\u41"')

    def test_U_escape_low_byte(self):
        self.assertEqual(decode('b"\\U00000041"'), b"A")

    def test_U_escape_requires_eight(self):
        with self.assertRaises(DecodeError):
            decode('b"\\U000041"')

    def test_named_escape_low_byte(self):
        self.assertEqual(decode('b"\\N{LATIN CAPITAL LETTER A}"'), b"A")

    def test_named_escape_unknown(self):
        with self.assertRaises(DecodeError):
            decode('b"\\N{NOT A REAL NAME}"')

    def test_named_escape_empty(self):
        with self.assertRaises(DecodeError):
            decode('b"\\N{}"')

    def test_named_escape_unterminated(self):
        with self.assertRaises(DecodeError):
            decode('b"\\N{LATIN')


class TestUnicodeEscapesStrMode(unittest.TestCase):
    # No 'b' prefix: full code point encoded as UTF-8.
    def test_u_escape_utf8(self):
        self.assertEqual(decode('"\\u00e9"'), b"\xc3\xa9")

    def test_U_escape_utf8(self):
        self.assertEqual(decode('"\\U0001F600"'), "\U0001F600".encode("utf-8"))

    def test_named_escape_utf8(self):
        self.assertEqual(decode('"\\N{LATIN SMALL LETTER E WITH ACUTE}"'), b"\xc3\xa9")


class TestRaw(unittest.TestCase):
    def test_raw_backslash_is_literal(self):
        self.assertEqual(decode('rb"\\n"'), b"\\n")

    def test_raw_prefix_case_insensitive(self):
        self.assertEqual(decode('BR"\\n"'), b"\\n")

    def test_raw_no_escape_processing(self):
        self.assertEqual(decode('r"\\x41"'), b"\\x41")


class TestErrors(unittest.TestCase):
    def test_unknown_escape(self):
        with self.assertRaises(DecodeError):
            decode('b"\\q"')

    def test_trailing_backslash(self):
        with self.assertRaises(DecodeError):
            decode('b"abc\\"')

    def test_unterminated_single(self):
        with self.assertRaises(DecodeError):
            decode("b'abc")

    def test_unterminated_double(self):
        with self.assertRaises(DecodeError):
            decode('b"abc')

    def test_unterminated_triple(self):
        with self.assertRaises(DecodeError):
            decode('b"""abc')

    def test_trailing_data(self):
        with self.assertRaises(DecodeError):
            decode('b"abc"xyz')

    def test_conflicting_prefixes(self):
        with self.assertRaises(DecodeError):
            decode('ub"abc"')

    def test_duplicated_prefix(self):
        with self.assertRaises(DecodeError):
            decode('bb"abc"')

    def test_non_string_input(self):
        with self.assertRaises(DecodeError):
            decode(123)  # type: ignore[arg-type]


class TestDecodeInner(unittest.TestCase):
    def test_inner_plain(self):
        self.assertEqual(decode_inner("abc"), b"abc")

    def test_inner_with_escapes(self):
        self.assertEqual(decode_inner("a\\nb"), b"a\nb")

    def test_inner_raw(self):
        self.assertEqual(decode_inner("a\\nb", is_raw=True), b"a\\nb")

    def test_inner_str_mode_utf8(self):
        self.assertEqual(decode_inner("\\u00e9", is_bytes=False), b"\xc3\xa9")

    def test_inner_bytes_mode_low_byte(self):
        self.assertEqual(decode_inner("\\u00e9", is_bytes=True), b"\xe9")


class TestErrorIsValueError(unittest.TestCase):
    def test_subclass_of_value_error(self):
        self.assertTrue(issubclass(DecodeError, ValueError))


if __name__ == "__main__":
    unittest.main()
