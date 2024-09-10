import os
from .lexers import *

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
        return GasmLexer
    elif filename.startswith('kconfig') and extension != 'rst':
        return KconfigLexer
    else:
        return None

