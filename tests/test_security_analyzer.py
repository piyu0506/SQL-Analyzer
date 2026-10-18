from analyzer.lexer import tokenize
from analyzer.parser import parse
from analyzer.security_analyzer import analyze


def findings_for(query):
    tokens = tokenize(query)
    try:
        statement = parse(tokens)
    except ValueError:
        statement = None
    return analyze(tokens, statement)


def test_warns_about_tautology_and_suspicious_or():
    findings = findings_for("SELECT id FROM users WHERE id = 1 OR 1 = 1")
    titles = [finding["finding"] for finding in findings]
    assert "Potential tautological condition" in titles
    assert "Suspicious OR condition involving a tautology" in titles


def test_warns_about_select_star():
    assert any(finding["severity"] == "INFO"
               for finding in findings_for("SELECT * FROM users"))


def test_warns_about_destructive_statements_and_multiple_statements():
    findings = findings_for("DELETE FROM users; DROP TABLE users")
    titles = [finding["finding"] for finding in findings]
    assert "DELETE without a WHERE clause" in titles
    assert "Potentially destructive DROP statement" in titles
    assert "Multiple SQL statements detected" in titles


def test_warns_about_update_without_where():
    assert any("UPDATE without" in finding["finding"]
               for finding in findings_for("UPDATE users SET age = 10"))


def test_keyword_and_semicolon_text_inside_string_is_not_a_statement():
    findings = findings_for(
        "SELECT username FROM users WHERE username = 'DROP; WHERE'"
    )
    titles = [finding["finding"] for finding in findings]
    assert "Potentially destructive DROP statement" not in titles
    assert "Multiple SQL statements detected" not in titles
