import re
import os
from collections import OrderedDict
from .lexers import *

default_lexers = {
    r'.*\.(c|h|cpp|hpp|c++|cxx|cc)': CLexer,
    r'makefile\..*':  MakefileLexer,
    r'.*\.dts(i)?': DTSLexer,
    r'.*\.s': GasLexer,
    r'kconfig.*': KconfigLexer, #TODO negative lookahead for .rst
}

linux_lexers = OrderedDict({
    r'.*\.(c|h|cpp|hpp|c++|cxx|cc)': CLexer,
    r'makefile\..*':  MakefileLexer,
    r'.*\.dts(i)?': DTSLexer,
    r'kconfig.*': KconfigLexer, #TODO negative lookahead for .rst

    r'/arch/alpha/.*\.s': (GasLexer, {"arch": "alpha"}),
    r'/arch/arc/.*\.s': (GasLexer, {"arch": "arc"}),
    r'/arch/arm/.*\.s': (GasLexer, {"arch": "arm32"}),
    r'/arch/csky/.*\.s': (GasLexer, {"arch": "csky"}),
    r'/arch/m68k/.*\.s': (GasLexer, {"arch": "m68k"}),
    r'/arch/microblaze/.*\.s': (GasLexer, {"arch": "microblaze"}),
    r'/arch/mips/.*\.s': (GasLexer, {"arch": "mips"}),
    r'/arch/openrisc/.*\.s': (GasLexer, {"arch": "openrisc"}),
    r'/arch/parisc/.*\.s': (GasLexer, {"arch": "parisc"}),
    r'/arch/riscv/.*\.s': (GasLexer, {"arch": "riscv"}),
    r'/arch/s390/.*\.s': (GasLexer, {"arch": "s390"}),
    r'/arch/sh/.*\.s': (GasLexer, {"arch": "sh"}),
    r'/arch/sparc/.*\.s': (GasLexer, {"arch": "sparc"}),
    r'/arch/um/.*\.s': (GasLexer, {"arch": "x86"}),
    r'/arch/x86/.*\.s': (GasLexer, {"arch": "x86"}),
    r'/arch/xtensa/.*\.s': (GasLexer, {"arch": "xtensa"}),
    r'.*\.s': GasLexer,
    # ...
})

def get_lexer(path):
    path = path.lower()
    lexers = linux_lexers
    for regex, lexer in lexers.items():
        if re.match(regex, path):
            if type(lexer) == tuple:
                lexer_cls, kwargs = lexer
                return lambda code: lexer_cls(code, **kwargs)
            else:
                return lambda code: lexer(code)

