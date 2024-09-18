import re
import enum
import sys
from collections import namedtuple

from elixir.lexers import shared

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
    return lambda code, pos, _: rule.match(code, pos)

class Matcher:
    def update_after_match(self, code: str, pos: int, line: int, token: Token) -> None:
        pass

    def match(self, code: str, pos: int, line: int) -> None | re.Match:
        pass

class FirstInLine(Matcher):
    def __init__(self, regex):
        self.rule = re.compile(regex, flags=re.MULTILINE)
        self.first_in_line = True

    def update_after_match(self, code, pos, line, token):
        if pos == 0:
            self.first_in_line = True
            return

        newline_pos = token.token.rfind('\n')

        if newline_pos != -1:
            post_newline_tok = token.token[newline_pos+1:]

            if re.fullmatch(r'\s*', post_newline_tok):
                self.first_in_line = True
        elif self.first_in_line and re.fullmatch(r'\s*', token.token):
            self.first_in_line = True
        else:
            self.first_in_line = False

    def match(self, code, pos, line):
        if self.first_in_line:
            return self.rule.match(code, pos)

LexerContext = namedtuple('LexerContext', 'code, pos, line')

def simple_lexer(rules, code):
    if len(code) == 0:
        return

    if code[-1] != '\n':
        code += '\n'

    rules_compiled = []
    after_match_hooks = []

    for rule, action in rules:
        if type(rule) is str:
            rules_compiled.append((match_regex(rule), action))
        elif callable(rule):
            rules_compiled.append((rule, action))
        elif isinstance(rule, Matcher):
            rules_compiled.append((rule.match, action))
            after_match_hooks.append(rule.update_after_match)

    def yield_token(to_yield):
        for hook in after_match_hooks:
            hook(code, pos, line, to_yield)
        return to_yield

    pos = 0
    line = 1
    while pos < len(code):
        rule_matched = False
        for rule, action in rules_compiled:
            match = rule(code, pos, line)

            if match is not None:
                span = match.span()
                if span[0] == span[1]:
                    continue
                rule_matched = True

                if isinstance(action, TokenType):
                    token = code[span[0]:span[1]]
                    token_obj = Token(action, token, span, line)
                    yield yield_token(token_obj)
                    line += token.count('\n')
                    pos = span[1]
                    break
                elif callable(action):
                    last_token = None
                    for token in action(LexerContext(code, pos, line), match):
                        last_token = token
                        yield yield_token(token)

                    if last_token is not None:
                        pos = last_token.span[1]
                        line = last_token.line + last_token.token.count('\n')

                    break
                else:
                    raise Exception(f"invalid action {action}")

        if not rule_matched:
            token = Token(TokenType.ERROR, code[pos], (pos, pos+1), line)
            yield yield_token(token)
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

