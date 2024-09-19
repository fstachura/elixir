import json
import sys
from . import get_lexer
from .utils import Token, TokenType

def serialize_tokens(tokens, buf):
    for t in tokens:
        type, token, span, line = t
        buf.write(json.dumps([type.name, token, span, line]))
        buf.write("\n")

def deserialize_tokens(buf):
    for line in buf.readlines():
        token = json.loads(line)
        yield Token(TokenType[token[0]], token[1], (token[2][0], token[2][1]), token[3])

if __name__ == '__main__':
    if len(sys.argv) != 2:
        print("usage:", sys.argv[0], "path/to/file")
        exit(1)

    filename = sys.argv[1]
    lexer = get_lexer(filename)
    if lexer is not None:
        with open(filename) as f:
            code = f.read()

        tokens = lexer(code).lex()
        serialize_tokens(tokens, sys.stdout)

