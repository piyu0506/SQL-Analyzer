import pytest

from analyzer.lexer import LexerError, tokenize


def test_tokenizes_valid_query_with_positions():
    tokens = tokenize("SELECT id FROM users WHERE age >= 18;")
    assert [token.type for token in tokens[:-1]] == [
        "KEYWORD", "IDENTIFIER", "KEYWORD", "IDENTIFIER", "KEYWORD",
        "IDENTIFIER", "OPERATOR", "NUMBER", ";",
    ]
    assert tokens[0].line == 1 and tokens[0].column == 1
    assert tokens[5].value == "age"


def test_handles_escaped_quotes_and_keyword_text_in_string():
    tokens = tokenize("SELECT username FROM users WHERE username = 'it''s SELECT OR TRUE'")
    assert tokens[-2].type == "STRING"
    assert tokens[-2].value == "it's SELECT OR TRUE"


def test_rejects_invalid_character_with_location():
    with pytest.raises(LexerError, match="line 1, column 32"):
        tokenize("SELECT id FROM users WHERE age @ 2")


def test_rejects_unterminated_string():
    with pytest.raises(LexerError, match="Unterminated string literal"):
        tokenize("SELECT username FROM users WHERE username = 'unfinished")
