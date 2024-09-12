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

def match_regex(regex):
    rule = re.compile(regex, flags=re.MULTILINE)
    return lambda code, pos, _, __: rule.match(code, pos)

def if_first_in_line(regex):
    rule = re.compile(regex, flags=re.MULTILINE)
    def match(code, pos, line, prev_token):
        if pos == 0:
            return rule.match(code, pos)

        newline_pos = prev_token.token.rfind('\n')
        if newline_pos != -1:
            post_newline_tok = prev_token.token[newline_pos+1:]
            if re.fullmatch('\w*', post_newline_tok):
                return rule.match(code, pos)

    return match

LexerContext = namedtuple('LexerContext', 'code, pos, line, prev_token')

def simple_lexer(rules, code):
    if len(code) == 0:
        return

    if code[-1] != '\n':
        code += '\n'

    rules_compiled = []

    for rule, action in rules:
        if type(rule) is str:
            rules_compiled.append((match_regex(rule), action))
        else:
            rules_compiled.append((rule, action))

    pos = 0
    line = 1
    prev_token = None
    while pos < len(code):
        rule_matched = False
        for rule, action in rules_compiled:
            match = rule(code, pos, line, prev_token)

            if match is not None:
                span = match.span()
                if span[0] == span[1]:
                    continue
                rule_matched = True

                if isinstance(action, TokenType):
                    token = code[span[0]:span[1]]
                    token_obj = Token(action, token, span, line)
                    prev_token = token_obj
                    yield token_obj
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
                        prev_token = last_token

                    break
                else:
                    raise Exception(f"invalid action {action}")

        if not rule_matched:
            token = Token(TokenType.ERROR, code[pos], (pos, pos+1), line)
            yield token
            prev_token = token
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

