"""A position-aware lexer for the SQL subset accepted by this project."""

from dataclasses import asdict, dataclass


KEYWORDS = {
    "SELECT", "FROM", "WHERE", "AND", "OR", "NOT", "TRUE", "FALSE",
    "NULL", "IS", "ORDER", "BY", "ASC", "DESC", "LIMIT", "DELETE",
    "UPDATE", "DROP", "SET",
}


@dataclass(frozen=True)
class Token:
    type: str
    value: object
    line: int
    column: int

    def to_dict(self):
        return asdict(self)


class LexerError(ValueError):
    def __init__(self, message, line, column):
        self.message = message
        self.line = line
        self.column = column
        super().__init__(f"{message} at line {line}, column {column}")


class Lexer:
    def __init__(self, source):
        self.source = source
        self.position = 0
        self.line = 1
        self.column = 1

    def tokenize(self):
        tokens = []
        while self.position < len(self.source):
            char = self.source[self.position]
            if char.isspace():
                self._advance(char)
            elif char == "'":
                tokens.append(self._read_string())
            elif char.isalpha() or char == "_":
                tokens.append(self._read_identifier())
            elif char.isdigit():
                tokens.append(self._read_number())
            elif char in "(),;.*":
                tokens.append(self._single(char))
            elif char in "=<>!":
                tokens.append(self._read_operator())
            else:
                raise LexerError(f"Invalid character {char!r}", self.line, self.column)
        tokens.append(Token("EOF", "", self.line, self.column))
        return tokens

    def _advance(self, char):
        self.position += 1
        if char == "\n":
            self.line += 1
            self.column = 1
        else:
            self.column += 1

    def _single(self, char):
        token = Token(char, char, self.line, self.column)
        self._advance(char)
        return token

    def _read_identifier(self):
        line, column, start = self.line, self.column, self.position
        while self.position < len(self.source):
            char = self.source[self.position]
            if not (char.isalnum() or char == "_"):
                break
            self._advance(char)
        value = self.source[start:self.position]
        upper = value.upper()
        return Token("KEYWORD" if upper in KEYWORDS else "IDENTIFIER",
                     upper if upper in KEYWORDS else value, line, column)

    def _read_number(self):
        line, column, start = self.line, self.column, self.position
        while self.position < len(self.source) and self.source[self.position].isdigit():
            self._advance(self.source[self.position])
        is_decimal = False
        if (self.position < len(self.source) and self.source[self.position] == "."
                and self.position + 1 < len(self.source)
                and self.source[self.position + 1].isdigit()):
            is_decimal = True
            self._advance(".")
            while self.position < len(self.source) and self.source[self.position].isdigit():
                self._advance(self.source[self.position])
        raw = self.source[start:self.position]
        return Token("NUMBER", float(raw) if is_decimal else int(raw), line, column)

    def _read_string(self):
        line, column = self.line, self.column
        self._advance("'")
        value = []
        while self.position < len(self.source):
            char = self.source[self.position]
            if char == "'":
                self._advance(char)
                if self.position < len(self.source) and self.source[self.position] == "'":
                    self._advance("'")
                    value.append("'")
                    continue
                return Token("STRING", "".join(value), line, column)
            value.append(char)
            self._advance(char)
        raise LexerError("Unterminated string literal", line, column)

    def _read_operator(self):
        line, column = self.line, self.column
        char = self.source[self.position]
        self._advance(char)
        value = char
        if (char in "<>!" and self.position < len(self.source)
                and self.source[self.position] in "=>"):
            value += self.source[self.position]
            self._advance(self.source[self.position])
        if value == "!":
            raise LexerError("Expected '=' after '!'", line, column)
        return Token("OPERATOR", value, line, column)


def tokenize(source):
    return Lexer(source).tokenize()
