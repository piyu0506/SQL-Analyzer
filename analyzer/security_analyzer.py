"""Conservative pattern-based findings; this stage never executes user SQL."""

from .ast_nodes import BinaryExpression, Literal, UnaryExpression, Wildcard


def _finding(severity, title, explanation, recommendation):
    return {
        "severity": severity,
        "finding": title,
        "explanation": explanation,
        "recommendation": recommendation,
    }


def _is_tautology(expression):
    if not isinstance(expression, BinaryExpression) or expression.operator != "=":
        return False
    left, right = expression.left, expression.right
    return (isinstance(left, Literal) and isinstance(right, Literal)
            and left.literal_type in ("NUMBER", "STRING")
            and right.literal_type == left.literal_type
            and left.value == right.value)


def _walk(expression):
    if expression is None:
        return
    yield expression
    if isinstance(expression, BinaryExpression):
        yield from _walk(expression.left)
        yield from _walk(expression.right)
    elif isinstance(expression, UnaryExpression):
        yield from _walk(expression.operand)


def analyze(tokens, statement=None):
    findings = []
    significant = [token for token in tokens if token.type != "EOF"]
    segments = []
    segment = []
    for token in significant:
        if token.type == ";":
            if segment:
                segments.append(segment)
                segment = []
        else:
            segment.append(token)
    if segment:
        segments.append(segment)
    if len(segments) > 1:
        findings.append(_finding(
            "HIGH", "Multiple SQL statements detected",
            "More than one statement is present. Executing concatenated user input can expose an application to statement injection.",
            "Accept one statement per request and use parameterized queries.",
        ))

    upper_values = [
        str(token.value).upper() for token in significant if token.type == "KEYWORD"
    ]
    if "DROP" in upper_values:
        findings.append(_finding(
            "HIGH", "Potentially destructive DROP statement",
            "DROP can remove database objects. This analyzer does not execute SQL.",
            "Avoid running destructive statements from untrusted input; require authorization and explicit review.",
        ))
    for statement_tokens in segments:
        statement_values = [
            str(token.value).upper() for token in statement_tokens
            if token.type == "KEYWORD"
        ]
        for command in ("DELETE", "UPDATE"):
            if command in statement_values:
                command_index = statement_values.index(command)
                if "WHERE" not in statement_values[command_index:]:
                    findings.append(_finding(
                        "HIGH", f"{command} without a WHERE clause",
                        f"This {command} statement appears to affect every row in its target table.",
                        "Add and verify a restrictive WHERE clause before running the statement.",
                    ))
    if statement and any(isinstance(column, Wildcard) for column in statement.columns):
        findings.append(_finding(
            "INFO", "SELECT * retrieves every column",
            "Selecting every column can expose data that the caller does not need.",
            "Select only the required columns and apply appropriate access controls.",
        ))
    if statement and statement.where:
        nodes = list(_walk(statement.where))
        if any(_is_tautology(node) for node in nodes):
            findings.append(_finding(
                "MEDIUM", "Potential tautological condition",
                "A comparison such as 1 = 1 is always true and may unintentionally broaden a filter.",
                "Remove unintended constant conditions. Use parameterized queries to defend against SQL injection.",
            ))
        if any(isinstance(node, BinaryExpression) and node.operator == "OR"
               and (_is_tautology(node.left) or _is_tautology(node.right))
               for node in nodes):
            findings.append(_finding(
                "HIGH", "Suspicious OR condition involving a tautology",
                "An always-true comparison joined with OR can make a filter match every row.",
                "Review the condition and bind user values with parameterized queries; this pattern alone does not prove an injection.",
            ))
    return findings
