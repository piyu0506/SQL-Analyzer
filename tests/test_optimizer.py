from analyzer.lexer import tokenize
from analyzer.optimizer import optimize
from analyzer.parser import parse
from analyzer.sql_generator import generate


def test_removes_and_true():
    statement = parse(tokenize("SELECT id FROM users WHERE age > 18 AND TRUE"))
    optimized, rules = optimize(statement)
    assert generate(optimized) == "SELECT id FROM users WHERE age > 18;"
    assert any(rule["rule"] == "Remove AND TRUE" for rule in rules)


def test_removes_duplicate_and_predicate():
    statement = parse(tokenize(
        "SELECT id FROM users WHERE age > 18 AND age > 18"
    ))
    optimized, rules = optimize(statement)
    assert generate(optimized) == "SELECT id FROM users WHERE age > 18;"
    assert any("duplicate" in rule["rule"] for rule in rules)


def test_removes_or_false_and_preserves_keyword_text_in_string():
    statement = parse(tokenize(
        "SELECT username FROM users WHERE username = 'TRUE AND SELECT' OR FALSE"
    ))
    optimized, _rules = optimize(statement)
    assert generate(optimized) == (
        "SELECT username FROM users WHERE username = 'TRUE AND SELECT';"
    )
