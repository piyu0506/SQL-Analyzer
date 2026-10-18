"""Small, explicit AST node types used by the parser and later compiler stages."""

from dataclasses import dataclass


class Node:
    def to_dict(self):
        raise NotImplementedError


class Expression(Node):
    pass


@dataclass
class Identifier(Expression):
    name: str

    def to_dict(self):
        return {"type": "Identifier", "name": self.name}


@dataclass
class Wildcard(Expression):
    def to_dict(self):
        return {"type": "Wildcard", "value": "*"}


@dataclass
class Literal(Expression):
    value: object
    literal_type: str

    def to_dict(self):
        return {
            "type": "Literal",
            "value": self.value,
            "literal_type": self.literal_type,
        }


@dataclass
class UnaryExpression(Expression):
    operator: str
    operand: Expression

    def to_dict(self):
        return {
            "type": "UnaryExpression",
            "operator": self.operator,
            "operand": self.operand.to_dict(),
        }


@dataclass
class BinaryExpression(Expression):
    left: Expression
    operator: str
    right: Expression

    def to_dict(self):
        return {
            "type": "BinaryExpression",
            "operator": self.operator,
            "left": self.left.to_dict(),
            "right": self.right.to_dict(),
        }


@dataclass
class IsNullExpression(Expression):
    expression: Expression
    negated: bool = False

    def to_dict(self):
        return {
            "type": "IsNullExpression",
            "expression": self.expression.to_dict(),
            "negated": self.negated,
        }


@dataclass
class OrderItem(Node):
    expression: Identifier
    direction: str = "ASC"

    def to_dict(self):
        return {
            "type": "OrderItem",
            "expression": self.expression.to_dict(),
            "direction": self.direction,
        }


@dataclass
class SelectStatement(Node):
    columns: list
    table: str
    where: Expression = None
    order_by: list = None
    limit: int = None

    def to_dict(self):
        return {
            "type": "SelectStatement",
            "columns": [column.to_dict() for column in self.columns],
            "from": self.table,
            "where": self.where.to_dict() if self.where else None,
            "order_by": [item.to_dict() for item in (self.order_by or [])],
            "limit": self.limit,
        }
