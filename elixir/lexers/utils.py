import re
import enum
from collections import namedtuple

# Supported token types
class TokenType(enum.Enum):
    WHITESPACE = 'whitespace',
    COMMENT = 'comment'
    STRING = 'string'
    NUMBER = 'number'
    IDENTIFIER = 'identifier'
    # may require extra parsing or context information
    SPECIAL = 'special'
    PUNCTUATION = 'punctuation'
    ERROR = 'error'

Token = namedtuple('Token', 'token_type, token, span, line')

def split_by_groups(*token_types):
    def split(ctx, match):
        pos = ctx.pos
        line = ctx.line
        for gi in range(len(match.groups())):
            token = match.group(gi+1)
            if len(token) != 0:
                action = token_types[gi]
                yield Token(action, token, (pos, pos+len(token)), line)
                line += token.count("\n")
                pos += len(token)

    return split

def match_token(ctx, pattern, token_type):
    match = re.compile(pattern).match(ctx.code, ctx.pos)
    if match is None:
        return None, ctx
    else:
        span = match.span()
        result = Token(token_type, ctx.code[span[0]:span[1]], span, ctx.line)
        new_ctx = ctx._replace(pos=span[1], line=ctx.line + result.token.count('\n'))
        return result, new_ctx

def empty_token(ctx):
    return Token(TokenType.ERROR, '', (ctx.pos, ctx.pos), ctx.line)

def token_from_match(ctx, match, token_type):
    span = match.span()
    result = Token(token_type, ctx.code[span[0]:span[1]], span, ctx.line)
    new_ctx = ctx._replace(pos=span[1], line=ctx.line+result.token.count('\n'))
    return result, new_ctx

def token_from_string(ctx, match, token_type):
    span = (ctx.pos, ctx.pos+len(match))
    result = Token(token_type, ctx.code[span[0]:span[1]], span, ctx.line)
    new_ctx = ctx._replace(pos=span[1], line=ctx.line+result.token.count('\n'))
    return result, new_ctx

LexerContext = namedtuple('LexerContext', 'code, pos, line')

def simple_lexer(rules, code):
    if len(code) == 0:
        return

    if code[-1] != '\n':
        code += '\n'

    rules = [(re.compile(rule, flags=re.MULTILINE|re.UNICODE), action) for rule, action in rules]
    pos = 0
    line = 1
    while pos < len(code):
        rule_matched = False
        for rule, action in rules:
            match = rule.match(code, pos)
            if match is not None:
                span = match.span()
                if span[0] == span[1]:
                    continue
                rule_matched = True

                if isinstance(action, TokenType):
                    token = code[span[0]:span[1]]
                    yield Token(action, token, span, line)
                    line += token.count('\n')
                    pos = span[1]
                    break
                elif callable(action):
                    last_token = None
                    for token in action(LexerContext(code, pos, line), match):
                        last_token = token
                        yield token

                    if last_token is not None:
                        pos = last_token.span[1]
                        line = last_token.line + last_token.token.count('\n')

                    break
                else:
                    raise Exception(f"invalid action {action}")

        if not rule_matched:
            yield Token(TokenType.ERROR, code[pos], (pos, pos+1), line)
            if code[pos] == '\n':
                line += 1
            pos += 1


# Combines regexes passed as arguments with pipe operator
def regex_or(*regexes):
    result = '('
    for r in regexes:
        result += f'({ r })|'
    return result[:-1] + ')'

def regex_concat(*regexes):
    result = ''
    for r in regexes:
        result += f'({ r })'
    return result

