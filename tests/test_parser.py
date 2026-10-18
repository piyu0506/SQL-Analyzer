import pytest

from analyzer.lexer import tokenize
from analyzer.parser import ParseError, parse


def test_parses_and_precedence_binds_and_tighter_than_or():
    tree = parse(tokenize(
        "SELECT id FROM users WHERE age > 18 OR role = 'admin' AND id = 2"
    )).to_dict()["where"]
    assert tree["operator"] == "OR"
    assert tree["right"]["operator"] == "AND"


def test_parses_parentheses_not_is_null_order_and_limit():
    statement = parse(tokenize(
        "SELECT id FROM users WHERE NOT (age IS NULL OR age < 18) "
        "ORDER BY age DESC LIMIT 10"
    ))
    assert statement.where.operator == "NOT"
    assert statement.order_by[0].direction == "DESC"
    assert statement.limit == 10


@pytest.mark.parametrize("query", [
    "SELECT FROM users",
    "SELECT id users",
    "SELECT id FROM users WHERE age >",
    "SELECT id FROM users WHERE age IS UNKNOWN",
    "SELECT id FROM users LIMIT 1.5",
])
def test_reports_syntax_errors(query):
    with pytest.raises(ParseError):
        parse(tokenize(query))


def test_reports_extra_statement():
    with pytest.raises(ParseError, match="Unexpected token"):
        parse(tokenize("SELECT id FROM users; SELECT id FROM orders"))
