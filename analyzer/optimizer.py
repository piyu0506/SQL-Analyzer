"""Meaning-preserving boolean simplification over the supported expression AST."""

from .ast_nodes import BinaryExpression, Literal, SelectStatement, UnaryExpression


def _boolean(expression):
    if isinstance(expression, Literal) and expression.literal_type == "BOOLEAN":
        return expression.value
    return None


def _key(node):
    return repr(node.to_dict())


class Optimizer:
    def __init__(self):
        self.rules = []

    def optimize(self, statement):
        self.rules = []
        where = self._simplify(statement.where) if statement.where else None
        return SelectStatement(
            statement.columns, statement.table, where,
            statement.order_by, statement.limit,
        ), self.rules

    def _record(self, name, explanation):
        self.rules.append({"rule": name, "explanation": explanation})

    def _simplify(self, expression):
        if isinstance(expression, UnaryExpression):
            operand = self._simplify(expression.operand)
            value = _boolean(operand)
            if value is not None:
                self._record("NOT constant", "Evaluated NOT applied to a boolean literal.")
                return Literal(not value, "BOOLEAN")
            return UnaryExpression(expression.operator, operand)
        if not isinstance(expression, BinaryExpression):
            return expression
        left = self._simplify(expression.left)
        right = self._simplify(expression.right)
        operator = expression.operator
        left_bool, right_bool = _boolean(left), _boolean(right)
        if operator == "AND":
            if left_bool is False or right_bool is False:
                self._record("AND FALSE", "An AND expression with FALSE is always FALSE.")
                return Literal(False, "BOOLEAN")
            if left_bool is True:
                self._record("Remove AND TRUE", "TRUE does not change the result of an AND expression.")
                return right
            if right_bool is True:
                self._record("Remove AND TRUE", "TRUE does not change the result of an AND expression.")
                return left
            if _key(left) == _key(right):
                self._record("Remove duplicate AND predicate",
                             "Repeated deterministic predicates joined by AND need only be evaluated once.")
                return left
        elif operator == "OR":
            if left_bool is True or right_bool is True:
                self._record("OR TRUE", "An OR expression with TRUE is always TRUE.")
                return Literal(True, "BOOLEAN")
            if left_bool is False:
                self._record("Remove OR FALSE", "FALSE does not change the result of an OR expression.")
                return right
            if right_bool is False:
                self._record("Remove OR FALSE", "FALSE does not change the result of an OR expression.")
                return left
        if left is expression.left and right is expression.right:
            return expression
        return BinaryExpression(left, operator, right)


def optimize(statement):
    return Optimizer().optimize(statement)
