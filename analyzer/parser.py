"""Recursive-descent parser for SELECT statements and boolean expressions."""

from .ast_nodes import (
    BinaryExpression, Identifier, IsNullExpression, Literal, OrderItem,
    SelectStatement, UnaryExpression, Wildcard,
)
from .lexer import Token


class ParseError(ValueError):
    def __init__(self, message, token):
        self.message = message
        self.line = token.line
        self.column = token.column
        super().__init__(f"{message} at line {token.line}, column {token.column}")


class Parser:
    def __init__(self, tokens):
        self.tokens = tokens
        self.position = 0

    @property
    def current(self):
        return self.tokens[self.position]

    def _advance(self):
        token = self.current
        if token.type != "EOF":
            self.position += 1
        return token

    def _match(self, *values):
        if self.current.value in values:
            return self._advance()
        return None

    def _expect(self, value, message=None):
        token = self._match(value)
        if token is None:
            raise ParseError(message or f"Expected {value!r}", self.current)
        return token

    def _expect_identifier(self):
        if self.current.type != "IDENTIFIER":
            raise ParseError("Expected an identifier", self.current)
        return Identifier(self._advance().value)

    def parse(self):
        statement = self._select_statement()
        self._match(";")
        if self.current.type != "EOF":
            raise ParseError("Unexpected token after the end of the SELECT statement", self.current)
        return statement

    def _select_statement(self):
        self._expect("SELECT", "Only SELECT statements are supported by the parser")
        columns = [self._select_item()]
        while self._match(","):
            columns.append(self._select_item())
        self._expect("FROM")
        table = self._expect_identifier().name
        where = self._expression() if self._match("WHERE") else None
        order_by = []
        if self._match("ORDER"):
            self._expect("BY")
            while True:
                expression = self._expect_identifier()
                direction = "DESC" if self._match("DESC") else "ASC"
                if direction == "ASC":
                    self._match("ASC")
                order_by.append(OrderItem(expression, direction))
                if not self._match(","):
                    break
        limit = None
        if self._match("LIMIT"):
            if self.current.type != "NUMBER" or not isinstance(self.current.value, int):
                raise ParseError("LIMIT must be a non-negative integer", self.current)
            limit = self._advance().value
        return SelectStatement(columns, table, where, order_by, limit)

    def _select_item(self):
        if self._match("*"):
            return Wildcard()
        return self._expect_identifier()

    def _expression(self):
        return self._or_expression()

    def _or_expression(self):
        expression = self._and_expression()
        while self._match("OR"):
            expression = BinaryExpression(expression, "OR", self._and_expression())
        return expression

    def _and_expression(self):
        expression = self._not_expression()
        while self._match("AND"):
            expression = BinaryExpression(expression, "AND", self._not_expression())
        return expression

    def _not_expression(self):
        if self._match("NOT"):
            return UnaryExpression("NOT", self._not_expression())
        return self._predicate()

    def _predicate(self):
        if self._match("("):
            expression = self._expression()
            self._expect(")", "Expected ')' to close the parenthesized expression")
            return expression
        left = self._value()
        if self._match("IS"):
            negated = bool(self._match("NOT"))
            self._expect("NULL", "Expected NULL after IS or IS NOT")
            return IsNullExpression(left, negated)
        if self.current.type == "OPERATOR":
            token = self._advance()
            operator = token.value
            if operator not in ("=", "!=", "<>", ">", "<", ">=", "<="):
                raise ParseError(f"Unsupported comparison operator {operator!r}", token)
            return BinaryExpression(left, operator, self._value())
        if isinstance(left, Literal) and left.literal_type == "BOOLEAN":
            return left
        raise ParseError("Expected a comparison operator or IS NULL", self.current)

    def _value(self):
        token = self.current
        if token.type == "IDENTIFIER":
            return self._expect_identifier()
        if token.type == "NUMBER":
            self._advance()
            return Literal(token.value, "NUMBER")
        if token.type == "STRING":
            self._advance()
            return Literal(token.value, "STRING")
        if token.value in ("TRUE", "FALSE"):
            self._advance()
            return Literal(token.value == "TRUE", "BOOLEAN")
        if token.value == "NULL":
            self._advance()
            return Literal(None, "NULL")
        raise ParseError("Expected a column name or literal value", token)


def parse(tokens):
    return Parser(tokens).parse()
