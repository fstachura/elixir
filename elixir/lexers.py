import os
import re
import enum
from collections import namedtuple

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
            yield Token(token_types[gi], token, (pos, pos+len(token)), line)
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

# https://en.cppreference.com/w/c/language
# https://www.iso-9899.info/wiki/The_Standard

c_multline_comment = r'/\*(.|\s)*?\*/'
c_singleline_comment = r'//(\\\s*\n|[^\n])*\n'
c_comment = f'(({ c_multline_comment })|({ c_singleline_comment }))'

c_string = r'"([^\\"]|\\(.|\s))*?"'

# technically not valid c, but should cover all valid escape cases
single_quote_string = r"'([^\\']|\\(.|\s))*?'"

c_string_and_char = f'(({ single_quote_string })|({ c_string }))'

# not entirely correct... accepts way more than the standard allows
c_number_suffix = r'([uU]|[lL]|(wb|WB)|[fF]){0,5}'

c_decimal_integer = r'[+-]?[0-9][0-9\']*'
c_hexidecimal_integer = r'[+-]?0[xX][0-9a-fA-F][0-9a-fA-F\']*'
c_octal_integer = r'[+-]?0[0-7][0-7\']*'
c_binary_integer = r'[+-]?0[bB][01][01\']*'

c_exponent = r'(e[+-]?[0-9][0-9\']*)'
c_hexidecimal_exponent = r'(p[+-]?[0-9][0-9\']*)'

c_decimal_double_part = r'\.[0-9\']*' + c_exponent + '?'
c_octal_double_part = r'\.[0-7\']*' + c_exponent + '?'
c_hexidecimal_double_part = r'\.[0-9a-fA-F\']*' + c_hexidecimal_exponent  + '?'

c_decimal = f'{ c_decimal_integer }({ c_decimal_double_part })?'
c_hexidecimal = f'{ c_hexidecimal_integer }({ c_hexidecimal_double_part })?'
c_octal = f'{ c_octal_integer }({ c_decimal_double_part })?'

c_number = f'(({ c_hexidecimal })|({ c_binary_integer })|({ c_decimal })|({ c_octal }))({ c_number_suffix })'

c_angled_include = r'#\s*include\s*<.*?>'
c_warning_and_error = r'#\s*(warning|error)(\\\s*\n|[^\n])*\n'
c_special = f'(({ c_angled_include })|({ c_warning_and_error }))'

whitespace = r'\s+'

# NOTE: does not support unicode identifiers
c_identifier = r'[a-zA-Z_][a-zA-Z_0-9]*'

c_punctuation = r'[!#%&`()*+,./:;<=>?\[\]\\^_{|}~-]'

# NOTE: macros don't always contain C code, but detecting that in pratice is hard
# without information about context (where the file is included from).
# idea for the future: map with locations of files that should be treated differently
# than by defaults (arch/*/include/asm/*)
# @ - arch/sh/include/mach-kfr2r09/mach/romimage.h
# @ - arch/arm/include/asm/assembler.h
# $ - arch/loongarch/include/asm/asmmacro.h
c_punctuation_extra = r'[$\\@]'

C_rules = [
    (whitespace, TokenType.WHITESPACE),
    (c_comment, TokenType.COMMENT),
    (c_string_and_char, TokenType.STRING),
    (c_number, TokenType.NUMBER),
    (c_identifier, TokenType.IDENTIFIER),
    (c_special, TokenType.SPECIAL),
    (c_punctuation, TokenType.PUNCTUATION),
    (c_punctuation_extra, TokenType.PUNCTUATION),
]

# https://www.devicetree.org/specifications/

# handles both property and node names
# technically identifiers in dts can be up to 31 characters long, but this limitation does not apply to defines...
# identifiers also probably can in practice start with special characters and end with special characters, 
# but telling an identifier with a comma apart from two identifiers separated by a comma would require more context
# dependent information. let's try the simple way, for now
# NOTE: previous versions would split identifiers by commas, this might have been intended?
dts_identifier = r'[0-9a-zA-Z_][0-9a-zA-Z,._+?#-]*[0-9a-zA-Z_]'
dts_single_char_identifier = r'[0-9a-zA-Z_]'

# 2.2.1, groups should be split in rules. it's not exactly a number...
dts_unit_address = r'(@)([0-9a-zA-Z,._+-]+)'

dts_punctuation = r'[#@:;{}\[\]()^<>=+*/%&\\|~!?,-]'

DTS_rules = [
    (whitespace, TokenType.WHITESPACE),
    (c_comment, TokenType.COMMENT),
    (c_string_and_char, TokenType.STRING),
    (c_number, TokenType.NUMBER),
    (dts_identifier, TokenType.IDENTIFIER),
    (c_angled_include, TokenType.SPECIAL),
    (dts_unit_address, split_by_groups(TokenType.PUNCTUATION, TokenType.SPECIAL)),
    (dts_punctuation, TokenType.PUNCTUATION),
    (dts_single_char_identifier, TokenType.IDENTIFIER),
]

# https://www.kernel.org/doc/html/next/kbuild/kconfig-language.html#kconfig-syntax
# https://www.kernel.org/doc/html/next/kbuild/kconfig-language.html#kconfig-hints

# TODO better help support
# TODO better macros support

hash_comment = r'#(\\\s*\n|[^\n])*\n'

# NOTE: matches only uppercase identifiers - this saves us from parsing macro calls, at least for now
kconfig_identifier = r'[A-Z0-9_][A-Z0-9_-]*'
# other perhaps interesting identifiers
kconfig_minor_identifier = r'[a-zA-Z0-9_/][a-zA-Z0-9_/.-]*'
kconfig_punctuation = r'[|&!=$()/_.+<>,-]'
kconfig_double_quote_string = r'"[^\n]*?"'
kconfig_single_quote_string = r"'[^\n]*?'"
kconfig_string = f'(({ kconfig_double_quote_string })|({ kconfig_single_quote_string }))'

# NOTE no identifiers are parsed out of KConfig help texts now
# for example see all instances of USB in /u-boot/v2024.07/source/drivers/usb/Kconfig#L3 

def count_kconfig_help_whitespace(start_whitespace_str):
    tabs = start_whitespace_str.count('\t')
    spaces = start_whitespace_str.count(' ')
    return 8*tabs + spaces + (len(start_whitespace_str)-tabs-spaces)

def parse_kconfig_help_text(ctx, match):
    # assumes called with matched help keyword, return the keyword
    token, ctx = token_from_match(ctx, match, TokenType.IDENTIFIER)
    yield token

    # match whitespace after help
    whitespace_after_help, ctx = match_token(ctx, r'\s*?\n', TokenType.WHITESPACE)
    if whitespace_after_help is None:
        # failed to match whitespace and newline after kconfig help - perhaps it's not the right context (macro call for exapmle)
        return
    else:
        yield whitespace_after_help

    line_matcher = re.compile(r'[^\n]*\n', flags=re.MULTILINE|re.UNICODE)

    start_help_text_pos = ctx.pos
    current_pos = ctx.pos
    min_whitespace = None

    def collect_tokens(start, end):
        return Token(TokenType.COMMENT, ctx.code[start:end], (start, end), ctx.line)

    # match first line with whitespace at the beginning
    while current_pos < len(ctx.code):
        line = line_matcher.match(ctx.code, current_pos)
        if line is None:
            yield collect_tokens(start_help_text_pos, current_pos)
            return

        token = line.group(0)
        span = line.span()

        if token == '\n':
            # just an empty line
            current_pos = span[1]
            continue
        else:
            start_whitespace = re.match(r'\s*', token)
            if start_whitespace is None:
                # no whitespace at the beginning of the line
                yield collect_tokens(start_help_text_pos, current_pos)
                return
            elif min_whitespace is None:
                # first nonemtpy line - save amount of whitespace
                min_whitespace = count_kconfig_help_whitespace(start_whitespace.group(0))
                current_pos = span[1]
            else:
                cur_whitespace = count_kconfig_help_whitespace(start_whitespace.group(0))
                if cur_whitespace < min_whitespace:
                    yield collect_tokens(start_help_text_pos, current_pos)
                    return
                else:
                    current_pos = span[1]

    yield collect_tokens(start_help_text_pos, current_pos)


KCONFIG_rules = [
    (whitespace, TokenType.WHITESPACE),
    (hash_comment, TokenType.COMMENT),
    (kconfig_string, TokenType.STRING),
    # for whatever reason u-boot kconfigs sometimes use ---help--- instead of help
    # /u-boot/v2024.07/source/arch/arm/mach-sunxi/Kconfig#L732
    (r'-*help-*', parse_kconfig_help_text),
    (kconfig_punctuation, TokenType.PUNCTUATION),
    (r'help', parse_kconfig_help_text),
    (kconfig_identifier, TokenType.IDENTIFIER),
    (kconfig_minor_identifier, TokenType.SPECIAL),
    # things that do not match are probably things from a macro call.
    # unless the syntax changed, or the help parser got confused.
    # https://www.kernel.org/doc/html/next/kbuild/kconfig-macro-language.html
    # both shell call and warning/error would require additinal parsing
    (r'[^\n]+', TokenType.SPECIAL),
]


# https://sourceware.org/binutils/docs/as.html#Syntax

# https://sourceware.org/binutils/docs/as.html#Symbol-Intro
# apparently dots are okay, BUT ctags removes the first dot from labels, for example. same with dollars
# /musl/v1.2.5/source/src/string/aarch64/memcpy.S#L92
gasm_identifier = r'[a-zA-Z0-9_][a-zA-Z0-9_$.]*'

gasm_flonum = r'0?\.[a-zA-Z][+-][0-9]*\.[0-9]*([eE][+-]*[0-9]+)?'
gasm_number = f'(({ c_hexidecimal_integer })|({ c_binary_integer })|({ c_decimal_integer })|({ gasm_flonum }))'

gasm_char = r"'(\\.|.|\n)"
gasm_string = f'(({ c_string })|({ gasm_char }))'

# TODO allow for this somehow (maybe #digits and #SCREAM_CASE only, without spaces? and #(SCREAM_CASE))
# u-boot/v2024.07/source/arch/arm/cpu/armv7/psci.S#L147

# single space is required after characters in rare comments - people *usually* place
# a space after a comment character. each architecture in gasm has different syntax,
# some have different syntax for comments. sometimes syntax for comments in one arch
# collides with syntax for something else in another arch (and i'm only talking about
# architectures that are supported in linux - i didn't research the niche ones).
# SH and SPARC use ! for comments, but ! is sometimes used for something else in arm64.
# same with @. ; is often used to separate statements...
# this (matching space after comment character) is works 99% of the time. but not 100%. 
# for 100% i believe the lexer will need hints about the context, and the only way to 
# provide these hints i see is to provide a map of directories that belong to problematic 
# architectures.

# NOTE hash comments can be preproc directives if there is only whitespace before them
# or sometimes not? depending on architecture
# also apparently if it starts with a number then it's a special line directive, but this probably is not interesting
gasm_hash_comment = r'#(\s*\n|\s+[^0-9\s].*\n)'

# used in HPPA (PA-RISC) https://sourceware.org/binutils/docs/as.html#HPPA-Syntax
# /linux/v6.10.7/source/arch/parisc/kernel/perf_asm.S#L28
gasm_semicolon_comment = r';\s+[a-zA-Z0-9](\s*\n|\s*[^0-9\s].*\n)'
# used in SH https://sourceware.org/binutils/docs/as.html#SH-Syntax
# /linux/v6.10.7/source/arch/sh/kernel/head_32.S#L58
# and SPARC https://sourceware.org/binutils/docs/as.html#Sparc_002dSyntax
# /linux/v6.10.7/source/arch/sparc/lib/memset.S#L125
gasm_exclamation_comment = r'!\s+[a-zA-Z0-9](\s*\n|\s*[^0-9\s].*\n)'
# used in ARM https://sourceware.org/binutils/docs/as.html#ARM-Syntax
# /linux/v6.10.7/source/arch/arm/mach-sa1100/sleep.S#L33
gasm_at_comment = r'@\s+[a-zA-Z0-9](\s*\n|\s*[^0-9\s].*\n)'

# there are also pipe comments, but some archs use pipes for binary operations

gasm_comment = f'(({ c_comment })|({ hash_comment })|({ gasm_semicolon_comment })|'\
    '({ gasm_exclamation_comment })|({ gasm_at_comment }))'

gasm_punctuation = r'[.,\[\]()<>{}%&+*!|@#$;:^/\\=~-]'
# TODO check if first in line
gasm_preprocessor = r'#[ \t]*(define|ifdef|ifndef|undef|if|else|elif)'

GASM_rules = [
    (whitespace, TokenType.WHITESPACE),
    # don't interpret macro concatenate as comment
    ('##', TokenType.PUNCTUATION),
    (gasm_preprocessor, TokenType.PUNCTUATION),
    (gasm_comment, TokenType.COMMENT),
    (gasm_string, TokenType.STRING),
    (gasm_number, TokenType.NUMBER),
    (gasm_identifier, TokenType.IDENTIFIER),
    (gasm_punctuation, TokenType.PUNCTUATION),
]

# https://www.gnu.org/software/make/manual/make.html

# TODO read https://pubs.opengroup.org/onlinepubs/007904975/utilities/make.html

# NOTE same as in KConfig, we only care about screaming case names
make_identifier = r'[A-Z0-9_]+'
make_minor_identifier = r'[a-zA-Z0-9_][a-zA-Z0-9-_]*'
make_variable = r'(\$\([a-zA-Z0-9_-]\)|\$\{[a-zA-Z0-9_-]\})'
make_single_quote_string = r"'*?'"
make_string = f'(({ make_single_quote_string })|({ c_string }))'
make_escaped = r'\\[#"\']'
make_punctuation = r'[~\\`\[\](){}<>.,:;|%$^@&?!+*/=-]'
make_comment = r'(?<!\\)#(\\\s*\n|[^\n])*\n'

MAKE_rules = [
    (whitespace, TokenType.WHITESPACE),
    (make_escaped, TokenType.PUNCTUATION),
    (make_comment, TokenType.COMMENT),
    (make_string, TokenType.STRING),
    (make_identifier, TokenType.IDENTIFIER),
    (make_minor_identifier, TokenType.SPECIAL),
    (make_punctuation, TokenType.PUNCTUATION),
]

LexerContext = namedtuple('LexerContext', 'code, pos, line')

def lex(rules, code):
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

def get_lexer(path):
    _, filename = os.path.split(path)
    filename = filename.lower()
    _, extension = os.path.splitext(filename)
    extension = extension[1:]
    if extension in ('c', 'h', 'cpp', 'hpp', 'c++', 'cxx', 'cc'):
        return lambda code: lex(C_rules, code)
    elif filename == 'makefile' or filename == 'gnumakefile':
        return lambda code: lex(MAKE_rules, code)
    # ./scripts/Makefile.dts in u-boot v2024.07... handled by entry above
    elif extension in ('dts', 'dtsi'):
        return lambda code: lex(DTS_rules, code)
    elif extension in ('s',):
        return lambda code: lex(GASM_rules, code)
    elif filename.startswith('kconfig') and extension != 'rst':
        return lambda code: lex(KCONFIG_rules, code)
    else:
        return None

