from analyzer.lexer import tokenize
from analyzer.parser import parse
from analyzer.semantic_analyzer import analyze


def test_accepts_known_table_and_columns():
    result = analyze(parse(tokenize(
        "SELECT username FROM users WHERE age >= 18"
    )))
    assert result == {"valid": True, "errors": []}


def test_reports_unknown_table_and_column():
    unknown_table = analyze(parse(tokenize("SELECT id FROM customers")))
    assert any("Unknown table" in error for error in unknown_table["errors"])
    unknown_column = analyze(parse(tokenize("SELECT nickname FROM users")))
    assert any("Unknown column" in error for error in unknown_column["errors"])


def test_reports_basic_type_mismatch():
    result = analyze(parse(tokenize("SELECT id FROM users WHERE age = 'adult'")))
    assert not result["valid"]
    assert any("Type mismatch" in error for error in result["errors"])


def test_accepts_text_columns_compared_with_string_literals():
    result = analyze(parse(tokenize(
        "SELECT username FROM users WHERE username = 'alice'"
    )))
    assert result == {"valid": True, "errors": []}
