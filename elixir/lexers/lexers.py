import re

from . import shared
from .utils import TokenType, Token, \
        simple_lexer, split_by_groups, \
        match_token, token_from_match, token_from_string, \
        regex_or

# Lexers used to extract possible references from source files
# Design strongly inspired by Pygments lexers

# https://en.cppreference.com/w/c/language
# https://www.iso-9899.info/wiki/The_Standard
class CLexer:
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

    rules = [
        (shared.whitespace, TokenType.WHITESPACE),
        (shared.common_slash_comment, TokenType.COMMENT),
        (shared.common_string_and_char, TokenType.STRING),
        (shared.c_number, TokenType.NUMBER),
        (c_identifier, TokenType.IDENTIFIER),
        (shared.c_preproc_ignore, TokenType.SPECIAL),
        (c_punctuation, TokenType.PUNCTUATION),
        (c_punctuation_extra, TokenType.PUNCTUATION),
    ]

    def __init__(self, code):
        self.code = code

    def lex(self):
        return simple_lexer(self.rules, self.code)

# https://www.devicetree.org/specifications/
class DTSLexer:
    # TODO handle macros separately

    # NOTE: previous versions would split identifiers by commas (and other special characters),
    # this changes the old behavior
    dts_single_char_identifier = r'[0-9a-zA-Z_]'

    # 6.2
    dts_label = r'[a-zA-Z_][a-zA-Z_0-9]{0,30}'
    # no whitespace between label and ampersand/colon is allowed
    dts_label_reference = f'(&)({ dts_label })'
    dts_label_definition = f'({ dts_label })(:)'

    # 2.2.1
    dts_node_name = r'[a-zA-Z0-9,._+-]{1,31}'
    # can contain macro symbols
    dts_unit_address = r'[a-zA-Z0-9,._+-]*'

    dts_node_name_with_unit_address = f'({ dts_node_name })(@)({ dts_unit_address })' + r'(\s*)({)'
    dts_node_name_without_unit_address = f'({ dts_node_name })' + r'(\s*)({)'

    # 2.2.4
    dts_property_name = r'[0-9a-zA-Z,._+?#-]{1,31}'
    dts_property_assignment = f'({ dts_property_name })' + r'(\s*)(=)'
    dts_property_empty = f'({ dts_property_name })' + r'(\s*)(;)'

    # 6.3
    dts_node_reference = r'(&)({)([a-zA-Z0-9,._+/@-]+?)(})'

    dts_punctuation = r'[#@:;{}\[\]()^<>=+*/%&\\|~!?,-]'
    # other, unknown, identifiers - for exmple macros
    dts_default_identifier = r'[a-zA-Z_][0-9a-zA-Z_]*'

    # Parse DTS node reference, ex: &{/path/to/node@20/test}
    @staticmethod
    def parse_dts_node_reference(ctx, match):
        # &
        token, ctx = token_from_string(ctx, match.group(1), TokenType.PUNCTUATION)
        yield token

        # {
        token, ctx = token_from_string(ctx, match.group(2), TokenType.PUNCTUATION)
        yield token

        path = match.group(3)
        path_part_matcher = re.compile(DTSLexer.dts_unit_address)
        strpos = 0

        while strpos < len(path):
            if path[strpos] == '@' or path[strpos] == '/':
                token, ctx = token_from_string(ctx, path[strpos], TokenType.PUNCTUATION)
                yield token
                strpos += 1
            else:
                part_match = path_part_matcher.match(path, strpos)
                if part_match is None:
                    token, _ = token_from_string(ctx, TokenType.ERROR, '')
                    yield token
                    return None

                token, ctx = token_from_string(ctx, part_match.group(0), TokenType.IDENTIFIER)
                yield token
                strpos += len(part_match.group(0))
        # }
        token, ctx = token_from_string(ctx, match.group(4), TokenType.PUNCTUATION)
        yield token

    rules = [
        (shared.whitespace, TokenType.WHITESPACE),
        (shared.common_slash_comment, TokenType.COMMENT),
        (shared.common_string_and_char, TokenType.STRING),
        (shared.c_number, TokenType.NUMBER),

        (dts_label_reference, split_by_groups(TokenType.PUNCTUATION, TokenType.IDENTIFIER)),
        (dts_label_definition, split_by_groups(TokenType.IDENTIFIER, TokenType.PUNCTUATION)),
        (dts_node_reference, parse_dts_node_reference),

        (dts_property_assignment, split_by_groups(TokenType.IDENTIFIER, TokenType.WHITESPACE, TokenType.PUNCTUATION)),
        (dts_property_empty, split_by_groups(TokenType.IDENTIFIER, TokenType.WHITESPACE, TokenType.PUNCTUATION)),

        (dts_node_name_with_unit_address, split_by_groups(TokenType.IDENTIFIER, TokenType.PUNCTUATION,
                                                          TokenType.IDENTIFIER, TokenType.WHITESPACE, TokenType.PUNCTUATION)),
        (dts_node_name_without_unit_address, split_by_groups(TokenType.IDENTIFIER, TokenType.WHITESPACE, TokenType.PUNCTUATION)),

        (dts_default_identifier, TokenType.IDENTIFIER),
        (shared.c_preproc_ignore, TokenType.SPECIAL),
        (dts_punctuation, TokenType.PUNCTUATION),
        (dts_single_char_identifier, TokenType.IDENTIFIER),
    ]

    def __init__(self, code):
        self.code = code

    def lex(self):
        return simple_lexer(self.rules, self.code)


# https://www.kernel.org/doc/html/next/kbuild/kconfig-language.html#kconfig-syntax
# https://www.kernel.org/doc/html/next/kbuild/kconfig-language.html#kconfig-hints

# TODO better macros calls support

class KconfigLexer:
    hash_comment = r'#' + shared.singleline_comment_with_escapes_base

    # NOTE pretty much all kconfig identifiers either start uppercase or with a number. this saves us from parsing macro calls
    kconfig_identifier = r'[A-Z0-9_][A-Z0-9a-z_a-]*'
    # other perhaps interesting identifiers
    kconfig_minor_identifier = r'[a-zA-Z0-9_/][a-zA-Z0-9_/.-]*'
    kconfig_punctuation = r'[|&!=$()/_.+<>,-]'
    kconfig_double_quote_string = r'"[^\n]*?"'
    kconfig_single_quote_string = r"'[^\n]*?'"
    kconfig_string = regex_or(kconfig_double_quote_string, kconfig_single_quote_string)
    kconfig_number = f'[0-9]+'

    # NOTE no identifiers are parsed out of KConfig help texts now, this changes the
    # old behavior
    # for example see all instances of USB in /u-boot/v2024.07/source/drivers/usb/Kconfig#L3

    @staticmethod
    def count_kconfig_help_whitespace(start_whitespace_str):
        tabs = start_whitespace_str.count('\t')
        spaces = start_whitespace_str.count(' ')
        return 8*tabs + spaces + (len(start_whitespace_str)-tabs-spaces)

    @staticmethod
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
                    min_whitespace = KconfigLexer.count_kconfig_help_whitespace(start_whitespace.group(0))
                    current_pos = span[1]
                else:
                    cur_whitespace = KconfigLexer.count_kconfig_help_whitespace(start_whitespace.group(0))
                    if cur_whitespace < min_whitespace:
                        yield collect_tokens(start_help_text_pos, current_pos)
                        return
                    else:
                        current_pos = span[1]

        yield collect_tokens(start_help_text_pos, current_pos)

    rules = [
        (shared.whitespace, TokenType.WHITESPACE),
        (hash_comment, TokenType.COMMENT),
        (kconfig_string, TokenType.STRING),
        (kconfig_number, TokenType.NUMBER),
        # for whatever reason u-boot kconfigs sometimes use ---help--- instead of help
        # /u-boot/v2024.07/source/arch/arm/mach-sunxi/Kconfig#L732
        (r'-+help-+', parse_kconfig_help_text),
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

    def __init__(self, code):
        self.code = code

    def lex(self):
        return simple_lexer(self.rules, self.code)


# https://sourceware.org/binutils/docs/as.html#Syntax
class GasmLexer:
    # https://sourceware.org/binutils/docs/as.html#Symbol-Intro
    # apparently dots are okay, BUT ctags removes the first dot from labels, for example. same with dollars
    # /musl/v1.2.5/source/src/string/aarch64/memcpy.S#L92
    gasm_identifier = r'[a-zA-Z0-9_][a-zA-Z0-9_$.]*'

    gasm_flonum = r'0?\.[a-zA-Z][+-][0-9]*\.[0-9]*([eE][+-]*[0-9]+)?'
    gasm_number = regex_or(shared.common_hexidecimal_integer, shared.common_binary_integer,
                           shared.common_decimal_integer, gasm_flonum)

    gasm_char = r"'(\\.|.|\n)"
    gasm_string = f'(({ shared.double_quote_string_with_escapes })|({ gasm_char }))'

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

    gasm_comment_chars_map = {
        'nios2': ('#',),
        'openrisc': ('#',),
        'powerpc': ('#',),
        's390': ('#',),
        'xtensa': ('#',),
        'microblaze': ('#',),
        'mips': ('#',),
        'alpha': ('#',),
        'csky': ('#',),
        'score': ('#',),
        'parisc': (';',),
        'x86': (';',),
        'tic6x': (';', '*'), # cx6, tms320, although the star is sketchy

        # technically # can be a comment if first character of the line
        'sh': ('!', '^#'),
        'sparc': ('!', '^#'),
        'm68k': ('|', '^#'), # BUT double pipe in macros is an operator... and # not in the first line in m68k/ifpsp060/src/fplsp.S
        'arc': ('#',';' '^#'),
        'arm32': ('@', '^#'),
        'cris': (';', '^#'),
        'avr': (';', '^#'),
        # blackfin, tile
    }

    whitespace_single_newline = '[ \t]*\n'

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

    gasm_comment = regex_or(shared.common_slash_comment, gasm_hash_comment, gasm_semicolon_comment,
                            gasm_exclamation_comment, gasm_at_comment)

    gasm_punctuation = r'[.,\[\]()<>{}%&+*!|@#$;:^/\\=~-]'
    # TODO check if first in line
    gasm_preprocessor = r'#[ \t]*(define|ifdef|ifndef|undef|if|else|elif)'

    rules = [
        (shared.whitespace, TokenType.WHITESPACE),
        # don't interpret macro concatenate as comment
        ('##', TokenType.PUNCTUATION),
        (gasm_preprocessor, TokenType.PUNCTUATION),
        (gasm_comment, TokenType.COMMENT),
        (gasm_string, TokenType.STRING),
        (gasm_number, TokenType.NUMBER),
        (gasm_identifier, TokenType.IDENTIFIER),
        (gasm_punctuation, TokenType.PUNCTUATION),
    ]

    def __init__(self, code):
        self.code = code

    def lex(self):
        return simple_lexer(self.rules, self.code)


# https://www.gnu.org/software/make/manual/make.html
class MakefileLexer:
    # TODO read https://pubs.opengroup.org/onlinepubs/007904975/utilities/make.html

    # NOTE same as in KConfig, we only care about screaming case names
    make_identifier = r'[A-Z0-9_]+'
    make_minor_identifier = r'[a-zA-Z0-9_][a-zA-Z0-9-_]*'
    make_variable = r'(\$\([a-zA-Z0-9_-]\)|\$\{[a-zA-Z0-9_-]\})'
    make_single_quote_string = r"'*?'"
    make_string = f'(({ make_single_quote_string })|({ shared.double_quote_string_with_escapes }))'
    make_escape = r'\\[#"\']'
    make_punctuation = r'[~\\`\[\](){}<>.,:;|%$^@&?!+*/=-]'
    make_comment = r'(?<!\\)#(\\\s*\n|[^\n])*\n'

    rules = [
        (shared.whitespace, TokenType.WHITESPACE),
        (make_escape, TokenType.PUNCTUATION),
        (make_comment, TokenType.COMMENT),
        (make_string, TokenType.STRING),
        (make_identifier, TokenType.IDENTIFIER),
        (make_minor_identifier, TokenType.SPECIAL),
        (make_punctuation, TokenType.PUNCTUATION),
    ]

    def __init__(self, code):
        self.code = code

    def lex(self):
        return simple_lexer(self.rules, self.code)

# Attempts to emulate the old tokenizer, only supports C-style comments and strings
# Skips angled includes
class DefaultLexer:
    rules = [
        (shared.whitespace, TokenType.WHITESPACE),
        (shared.common_slash_comment, TokenType.COMMENT),
        (shared.common_string_and_char, TokenType.STRING),
        (shared.c_preproc_ignore, TokenType.SPECIAL),
        (r'[a-zA-Z0-9_]+', TokenType.IDENTIFIER),
        (r'.', TokenType.PUNCTUATION),
    ]

    def __init__(self, code):
        self.code = code

    def lex(self):
        return simple_lexer(self.rules, self.code)

