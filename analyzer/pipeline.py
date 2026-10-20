"""Coordinates the independent compiler and analysis stages."""

from .lexer import LexerError, tokenize
from .optimizer import optimize
from .parser import ParseError, parse
from .schema_catalog import get_current_schema
from .security_analyzer import analyze as analyze_security
from .semantic_analyzer import analyze as analyze_semantics
from .sql_generator import generate


def analyze_query(query):
    schema = get_current_schema()
    response = {
        "tokens": [],
        "parse_tree": None,
        "semantic_analysis": {"valid": None, "errors": []},
        "security_findings": [],
        "optimized_sql": None,
        "optimization_explanations": [],
        "overall_status": "pending",
        "pipeline_status": {
            "lexical_analysis": "pending",
            "syntax_analysis": "pending",
            "ast_construction": "pending",
            "semantic_analysis": "pending",
            "security_analysis": "pending",
            "optimization": "pending",
        },
        "errors": {"lexical": None, "syntax": None, "semantic": []},
        "schema": schema,
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
            "ast_construction": "blocked",
            "semantic_analysis": "blocked", "security_analysis": "blocked",
            "optimization": "blocked",
        })
        response["overall_status"] = "lexical_error"
        return response

    statement = None
    try:
        statement = parse(tokens)
        response["parse_tree"] = statement.to_dict()
        response["pipeline_status"]["syntax_analysis"] = "passed"
        response["pipeline_status"]["ast_construction"] = "passed"
    except ParseError as error:
        response["errors"]["syntax"] = {
            "message": error.message, "line": error.line, "column": error.column,
        }
        response["pipeline_status"].update({
            "syntax_analysis": "failed", "ast_construction": "failed",
            "semantic_analysis": "blocked",
            "optimization": "blocked",
        })

    response["security_findings"] = analyze_security(tokens, statement)
    response["pipeline_status"]["security_analysis"] = "passed"
    if statement is None:
        response["overall_status"] = "syntax_error"
        return response

    semantics = analyze_semantics(statement, schema=schema)
    response["semantic_analysis"] = semantics
    response["errors"]["semantic"] = semantics["errors"]
    response["pipeline_status"]["semantic_analysis"] = (
        "passed" if semantics["valid"] else "failed"
    )
    if not semantics["valid"]:
        response["pipeline_status"]["optimization"] = "blocked"
        response["overall_status"] = "semantic_error"
        return response
    optimized, rules = optimize(statement)
    response["optimized_sql"] = generate(optimized)
    response["optimization_explanations"] = rules
    response["pipeline_status"]["optimization"] = "passed"
    response["overall_status"] = "passed"
    return response
