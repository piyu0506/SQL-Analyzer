"""Coordinates the independent compiler and analysis stages."""

from .lexer import LexerError, tokenize
from .optimizer import optimize
from .parser import ParseError, parse
from .security_analyzer import analyze as analyze_security
from .semantic_analyzer import analyze as analyze_semantics
from .sql_generator import generate


def analyze_query(query):
    response = {
        "tokens": [],
        "parse_tree": None,
        "semantic_analysis": {"valid": None, "errors": []},
        "security_findings": [],
        "optimized_sql": None,
        "optimization_explanations": [],
        "pipeline_status": {
            "lexical_analysis": "pending",
            "syntax_analysis": "pending",
            "semantic_analysis": "pending",
            "security_analysis": "pending",
            "optimization": "pending",
        },
        "errors": {"lexical": None, "syntax": None, "semantic": []},
    }
    try:
        tokens = tokenize(query)
        response["tokens"] = [token.to_dict() for token in tokens if token.type != "EOF"]
        response["pipeline_status"]["lexical_analysis"] = "passed"
    except LexerError as error:
        response["errors"]["lexical"] = {
            "message": error.message, "line": error.line, "column": error.column,
        }
        response["pipeline_status"].update({
            "lexical_analysis": "failed", "syntax_analysis": "blocked",
            "semantic_analysis": "blocked", "security_analysis": "blocked",
            "optimization": "blocked",
        })
        return response

    statement = None
    try:
        statement = parse(tokens)
        response["parse_tree"] = statement.to_dict()
        response["pipeline_status"]["syntax_analysis"] = "passed"
    except ParseError as error:
        response["errors"]["syntax"] = {
            "message": error.message, "line": error.line, "column": error.column,
        }
        response["pipeline_status"].update({
            "syntax_analysis": "failed", "semantic_analysis": "blocked",
            "optimization": "blocked",
        })

    response["security_findings"] = analyze_security(tokens, statement)
    response["pipeline_status"]["security_analysis"] = "passed"
    if statement is None:
        return response

    semantics = analyze_semantics(statement)
    response["semantic_analysis"] = semantics
    response["errors"]["semantic"] = semantics["errors"]
    response["pipeline_status"]["semantic_analysis"] = (
        "passed" if semantics["valid"] else "failed"
    )
    optimized, rules = optimize(statement)
    response["optimized_sql"] = generate(optimized)
    response["optimization_explanations"] = rules
    response["pipeline_status"]["optimization"] = "passed"
    return response
