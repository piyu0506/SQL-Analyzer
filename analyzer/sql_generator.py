"""Readable SQL generation from AST nodes."""

from .ast_nodes import (
    BinaryExpression, Identifier, IsNullExpression, Literal, UnaryExpression,
    Wildcard,
)


def _value(expression):
    if isinstance(expression, Identifier):
        return expression.name
    if isinstance(expression, Wildcard):
        return "*"
    if isinstance(expression, Literal):
        if expression.literal_type == "STRING":
            return "'" + str(expression.value).replace("'", "''") + "'"
        if expression.literal_type == "NULL":
            return "NULL"
        if expression.literal_type == "BOOLEAN":
            return "TRUE" if expression.value else "FALSE"
        return str(expression.value)
    if isinstance(expression, IsNullExpression):
        return f"{_value(expression.expression)} IS {'NOT ' if expression.negated else ''}NULL"
    if isinstance(expression, UnaryExpression):
        operand = _value(expression.operand)
        if isinstance(expression.operand, BinaryExpression):
            operand = f"({operand})"
        return f"{expression.operator} {operand}"
    if isinstance(expression, BinaryExpression):
        precedence = {"OR": 1, "AND": 2}
        own = precedence.get(expression.operator, 3)
        left, right = _value(expression.left), _value(expression.right)
        if isinstance(expression.left, BinaryExpression):
            if precedence.get(expression.left.operator, 3) < own:
                left = f"({left})"
        if isinstance(expression.right, BinaryExpression):
            if precedence.get(expression.right.operator, 3) <= own:
                right = f"({right})"
        return f"{left} {expression.operator} {right}"
    raise TypeError(f"Cannot generate SQL for {type(expression).__name__}")


def generate(statement):
    columns = ", ".join(_value(column) for column in statement.columns)
    sql = f"SELECT {columns} FROM {statement.table}"
    if statement.where:
        sql += f" WHERE {_value(statement.where)}"
    if statement.order_by:
        items = ", ".join(
            f"{item.expression.name} {item.direction}" for item in statement.order_by
        )
        sql += f" ORDER BY {items}"
    if statement.limit is not None:
        sql += f" LIMIT {statement.limit}"
    return sql + ";"
