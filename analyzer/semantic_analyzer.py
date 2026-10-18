"""Schema and basic type validation over the parsed AST."""

from .ast_nodes import (
    BinaryExpression, Identifier, IsNullExpression, Literal, UnaryExpression,
    Wildcard,
)
from .schema_catalog import SCHEMA


NUMERIC_TYPES = {"INTEGER", "DECIMAL", "NUMBER"}


class SemanticAnalyzer:
    def __init__(self, schema=None):
        self.schema = schema or SCHEMA
        self.errors = []

    def analyze(self, statement):
        self.errors = []
        table_name = statement.table.lower()
        if table_name not in self.schema:
            self.errors.append(f"Unknown table '{statement.table}'.")
            return {"valid": False, "errors": self.errors}
        columns = self.schema[table_name]
        for selected in statement.columns:
            if isinstance(selected, Identifier):
                self._check_column(selected, columns)
        for item in statement.order_by or []:
            self._check_column(item.expression, columns)
        if statement.where:
            self._check_expression(statement.where, columns)
        return {"valid": not self.errors, "errors": self.errors}

    def _check_column(self, identifier, columns):
        name = identifier.name.lower()
        if name not in columns:
            self.errors.append(f"Unknown column '{identifier.name}'.")
        return columns.get(name)

    def _check_expression(self, expression, columns):
        if isinstance(expression, Identifier):
            return self._check_column(expression, columns)
        if isinstance(expression, Literal):
            return expression.literal_type
        if isinstance(expression, UnaryExpression):
            operand_type = self._check_expression(expression.operand, columns)
            if operand_type not in (None, "BOOLEAN"):
                self.errors.append("NOT requires a boolean expression.")
            return "BOOLEAN"
        if isinstance(expression, IsNullExpression):
            self._check_expression(expression.expression, columns)
            return "BOOLEAN"
        if isinstance(expression, BinaryExpression):
            left_type = self._check_expression(expression.left, columns)
            right_type = self._check_expression(expression.right, columns)
            if expression.operator in ("AND", "OR"):
                if left_type not in (None, "BOOLEAN") or right_type not in (None, "BOOLEAN"):
                    self.errors.append(f"{expression.operator} requires boolean expressions.")
                return "BOOLEAN"
            if (left_type and right_type and left_type != "NULL" and right_type != "NULL"
                    and not (left_type in NUMERIC_TYPES and right_type in NUMERIC_TYPES)
                    and left_type != right_type):
                self.errors.append(
                    f"Type mismatch in comparison: {left_type} cannot be compared with {right_type}."
                )
            return "BOOLEAN"
        if isinstance(expression, Wildcard):
            return None
        return None


def analyze(statement, schema=None):
    return SemanticAnalyzer(schema).analyze(statement)
