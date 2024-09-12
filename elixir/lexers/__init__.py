import os
from .lexers import *

default_lexers = {
    '.*\.(c|h|cpp|hpp|c++|cxx|cc)': CLexer,
    'makefile\..*':  MakefileLexer,
    '.*\.dts(i)?': DTSLexer,
    '.*\.s': GasLexer,
    'kconfig.*': KconfigLexer, #TODO negative lookahead for .rst
}

linux_lexers = {
    'arch/riscv/.*\s': (GasLexer, {"arch": "riscv"}),
    'arch/openrisc/.*\s': (GasLexer, {"arch": "openrisc"}),
    'arch/s390/.*\s': (GasLexer, {"arch": "s390"}),
    'arch/xtensa/.*\s': (GasLexer, {"arch": "xtensa"}),
    'arch/microblaze/.*\s': (GasLexer, {"arch": "microblaze"}),
    'arch/mips/.*\s': (GasLexer, {"arch": "mips"}),
    'arch/alpha/.*\s': (GasLexer, {"arch": "alpha"}),
    'arch/csky/.*\s': (GasLexer, {"arch": "csky"}),
    'arch/parisc/.*\s': (GasLexer, {"arch": "parisc"}),
    'arch/x86/.*\s': (GasLexer, {"arch": "x86"}),
    'arch/sh/.*\s': (GasLexer, {"arch": "sh"}),
    'arch/sparc/.*\s': (GasLexer, {"arch": "sparc"}),
    'arch/m68k/.*\s': (GasLexer, {"arch": "m68k"}),
    'arch/arc/.*\s': (GasLexer, {"arch": "arc"}),
    # ...
}

def get_lexer(path):
    _, filename = os.path.split(path)
    filename = filename.lower()
    _, extension = os.path.splitext(filename)
    extension = extension[1:]
    if extension in ('c', 'h', 'cpp', 'hpp', 'c++', 'cxx', 'cc'):
        return CLexer
    elif filename == 'makefile' or filename == 'gnumakefile':
        return MakefileLexer
    # ./scripts/Makefile.dts in u-boot v2024.07... handled by entry above
    elif extension in ('dts', 'dtsi'):
        return DTSLexer
    elif extension in ('s',):
        return GasLexer
    elif filename.startswith('kconfig') and extension != 'rst':
        return KconfigLexer
    else:
        return None

