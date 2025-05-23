from typing import Generator, Tuple
from pygments.formatters import HtmlFormatter

class DiffFormater(HtmlFormatter):
    def __init__(self, diff, left: bool, *args, **kwargs):
        self.diff = diff
        self.left = left
        super().__init__(*args[2:], **kwargs)

    def get_next_diff_line(self, diff_num, next_diff_line):
        next_diff = self.diff[diff_num] if len(self.diff) > diff_num else None

        if next_diff is not None:
            if self.left and (next_diff[0] == '-' or next_diff[0] == '+'):
                next_diff_line = next_diff[1]
            elif next_diff[0] == '-' or next_diff[0] == '+':
                next_diff_line = next_diff[2]
            elif self.left and next_diff[0] == '=':
                next_diff_line = next_diff[1]
            elif next_diff[0] == '=':
                next_diff_line = next_diff[3]
            else:
                raise Exception("invlaid next diff mode")

        return next_diff, diff_num+1, next_diff_line

    # Wraps a single line with a CSS class, yields tuple (is a new line, wrapped line)
    def mark_line(self, line: Tuple[int, str], css_class: str) -> Generator[Tuple[int, str]]:
        yield line[0], f'<span class="{css_class}">{line[1]}</span>'

    # Wraps multiple lines with a CSS class, yields tuple of (is a new line, wrapped line)
    def mark_lines(self, source: Generator[Tuple[int, str]], num: int, css_class: str) -> Generator[Tuple[int, str]]:
        i = 0
        while i < num:
            try:
                t, line = next(source)
            except StopIteration:
                break
            if t == 1:
                yield t, f'<span class="{css_class}">{line}</span>'
                i += 1
            else:
                yield t, line

    # Yields num empty lines (displayed without line number)
    def yield_empty(self, num: int) -> Generator[Tuple[int, str]]:
        for _ in range(num):
            yield 0, '<span class="diff-line">&nbsp;\n</span>'

    # Wraps Pygments formatted source generator into diff generator
    def wrap_diff(self, source: Generator[Tuple[int, str]]) -> Generator[Tuple[int, str]]:
        next_diff, diff_num, next_diff_line = self.get_next_diff_line(0, None)

        linenum = 0

        while True:
            try:
                line = next(source)
            except StopIteration:
                break

            if linenum == next_diff_line:
                if next_diff is not None:
                    if self.left and next_diff[0] == '+':
                        yield from self.yield_empty(next_diff[3])
                        yield line
                        linenum += 1
                    elif next_diff[0] == '+':
                        yield from self.mark_line(line, 'line-added')
                        yield from self.mark_lines(source, next_diff[3]-1, 'line-added')
                        linenum += next_diff[3]
                    elif self.left and next_diff[0] == '-':
                        yield from self.mark_line(line, 'line-removed')
                        yield from self.mark_lines(source, next_diff[3]-1, 'line-removed')
                        linenum += next_diff[3]
                    elif next_diff[0] == '-':
                        yield from self.yield_empty(next_diff[3])
                        yield line
                        linenum += 1
                    elif next_diff[0] == '=':
                        total = max(next_diff[2], next_diff[4])
                        to_print = next_diff[2] if self.left else next_diff[4]
                        yield from self.mark_line(line, 'line-removed' if self.left else 'line-added')
                        yield from self.mark_lines(source, to_print-1, 'line-removed' if self.left else 'line-added')
                        yield from self.yield_empty(total-to_print)
                        linenum += to_print
                    else:
                        yield line
                        linenum += 1

                next_diff, diff_num, next_diff_line = self.get_next_diff_line(diff_num, next_diff_line)
            else:
                yield line
                linenum += 1

    # Pygments formatter entry
    def wrap(self, source: Generator[Tuple[int, str]]) -> Generator[Tuple[int, str]]:
        return super().wrap(self.wrap_diff(source))

def format_diff(filename: str, diff, code: str, code_other: str) -> Tuple[str, str]:
    import pygments
    import pygments.lexers
    import pygments.formatters
    from pygments.lexers.asm import GasLexer
    from pygments.lexers.r import SLexer

    try:
        lexer = pygments.lexers.guess_lexer_for_filename(filename, code)
        if filename.endswith('.S') and isinstance(lexer, SLexer):
            lexer = GasLexer()
    except pygments.util.ClassNotFound:
        lexer = pygments.lexers.get_lexer_by_name('text')

    lexer.stripnl = False

    formatter_options = {
        # Adds line numbers column to output
        'linenos': 'inline',
        # Wraps line numbers in link (a) tags
        'anchorlinenos': True,
        # Wraps each line in a span tag with id='codeline-{line_number}'
        'linespans': 'codeline',
    }

    formatter = DiffFormater(diff, True, **formatter_options)
    formatter_other = DiffFormater(diff, False, **formatter_options)

    return pygments.highlight(code, lexer, formatter), pygments.highlight(code_other, lexer, formatter_other)

