#!/usr/bin/env python3

#  This file is part of Elixir, a source code cross-referencer.
#
#  Copyright (C) 2017  Mikaël Bouillot
#  <mikael.bouillot@bootlin.com>
#
#  Elixir is free software: you can redistribute it and/or modify
#  it under the terms of the GNU Affero General Public License as published by
#  the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.
#
#  Elixir is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU Affero General Public License for more details.
#
#  You should have received a copy of the GNU Affero General Public License
#  along with Elixir.  If not, see <http://www.gnu.org/licenses/>.

import sys
import logging
import subprocess, os

logger = logging.getLogger(__name__)

CURRENT_DIR = os.path.abspath(os.path.dirname(os.path.abspath(__file__)) + '/../')

def script(*args, env=None):
    args = (os.path.join(CURRENT_DIR, 'script.sh'),) + args
    p = subprocess.run(args, stdout=subprocess.PIPE, env=env)
    return p.stdout

def run_cmd(*args, env=None):
    p = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env)
    if len(p.stderr) != 0:
        logger.error('command %s printed to stderr: \n%s', str(args), p.stderr.decode('utf-8'))
    return p.stdout, p.returncode

# Invoke ./script.sh with the given arguments
# Returns the list of output lines

def scriptLines(*args, env=None):
    p = script(*args, env=env)
    p = p.split(b'\n')
    del p[-1]
    return p

def unescape(bstr):
    subs = (
        ('\1','\n'),
    )
    for a,b in subs:
        a = a.encode()
        b = b.encode()
        bstr = bstr.replace(a, b)
    return bstr

def decode(byte_object):
    # decode('ascii') fails on special chars
    # FIXME: major hack until we handle everything as bytestrings
    try:
        return byte_object.decode('utf-8')
    except UnicodeDecodeError:
        return byte_object.decode('iso-8859-1')

# List of tokens which we don't want to consider as identifiers
# Typically for very frequent variable names and things redefined by #define
# TODO: allow to have per project blacklists
blacklist = set([
    b'enum',
    b'struct',
    b'union',

    b'if',
    b'else',

    b'return',

    b'switch',
    b'case',
    b'default',

    b'for',
    b'while',
    b'do',
    b'break',
    b'continue',
    b'goto',

    b'true',
    b'false',
    b'NULL',

    b'define',
    b'elif',
    b'else',
    b'endif',
    b'ifdef',
    b'ifndef',
    b'elifdef',
    b'elifndef',
    b'undef',
    b'__',
])

# list of tokens, that are indexed as references even if no definitions are known

always_indexed_tokens = set([
# gcc/c-family/c-common.cc
    b'_Alignas',
    b'_Alignof',
    b'_Atomic',
    b'_BitInt',
    b'_Bool',
    b'_Complex',
    b'_Imaginary',
    b'_Float16',
    b'_Float32',
    b'_Float64',
    b'_Float128',
    b'_Float32x',
    b'_Float64x',
    b'_Float128x',
    b'_Decimal32',
    b'_Decimal64',
    b'_Decimal128',
    b'_Fract',
    b'_Accum',
    b'_Sat',
    b'_Static_assert',
    b'_Noreturn',
    b'_Generic',
    b'_Thread_local',
    b'__FUNCTION__',
    b'__PRETTY_FUNCTION__',
    b'__alignof',
    b'__alignof__',
    b'__asm',
    b'__asm__',
    b'__attribute',
    b'__attribute__',
    b'__auto_type',
    b'__complex',
    b'__complex__',
    b'__const',
    b'__const__',
    b'__constinit',
    b'__decltype',
    b'__extension__',
    b'__func__',
    b'__imag',
    b'__imag__',
    b'__inline',
    b'__inline__',
    b'__label__',
    b'__null',
    b'__real',
    b'__real__',
    b'__restrict',
    b'__restrict__',
    b'__signed',
    b'__signed__',
    b'__thread',
    b'__transaction_atomic',
    b'__transaction_relaxed',
    b'__transaction_cancel',
    b'__typeof',
    b'__typeof__',
    b'__typeof_unqual',
    b'__typeof_unqual__',
    b'__volatile',
    b'__volatile__',
    b'__GIMPLE',
    b'__PHI',
    b'__RTL',
    b'alignas',
    b'alignof',
    b'asm',
    b'auto',
    b'thread_local',
    b'sizeof',

# https://gcc.gnu.org/onlinedocs/gcc/_005f_005fint128.html
    b'__int128',

# https://gcc.gnu.org/onlinedocs/gcc/Floating-Types.html
    b'__float80',
    b'__ibm128',

# https://gcc.gnu.org/onlinedocs/gcc/Half-Precision.html
    b'__fp16',

# https://gcc.gnu.org/onlinedocs/gcc/Named-Address-Spaces.html
    b'__flash',
    b'__flash1',
    b'__flash2',
    b'__flash3',
    b'__flash4',
    b'__flash5',
    b'__memx',
    b'__far',
    b'__regio_symbol',
    b'__seg_fs',
    b'__seg_gs',
])

always_indexed_prefixes = (
    b'__builtin',

# https://gcc.gnu.org/onlinedocs/gcc/_005f_005fsync-Builtins.html
    b'__sync',

# https://gcc.gnu.org/onlinedocs/gcc/_005f_005fatomic-Builtins.html
    b'__atomic',
    b'__ATOMIC',
)

def isIdent(bstr):
    if (len(bstr) < 2 or
        bstr in blacklist or
        bstr.startswith(b'~')):
        return False
    else:
        return True

def autoBytes(arg):
    if type(arg) is str:
        arg = arg.encode()
    elif type(arg) is int:
        arg = str(arg).encode()
    return arg

def getDataDir():
    try:
        return os.environ['LXR_DATA_DIR']
    except KeyError:
        print(sys.argv[0] + ': LXR_DATA_DIR needs to be set')
        exit(1)

def getRepoDir():
    try:
        return os.environ['LXR_REPO_DIR']
    except KeyError:
        print(sys.argv[0] + ': LXR_REPO_DIR needs to be set')
        exit(1)

def currentProject():
    return os.path.basename(os.path.dirname(getDataDir()))

# List all families supported by Elixir
families = ['A', 'B', 'C', 'D', 'K', 'M']

# Those families have databases that cache the content of definitions.db.
# This allows faster lookup.
CACHED_DEFINITIONS_FAMILIES = ['C', 'K', 'D', 'M']

def validFamily(family):
    return family in families

def getFileFamily(filename):
    name, ext = os.path.splitext(filename)
    name, ext = name.lower(), ext.lower()

    if ext in ['.c', '.cc', '.cpp', '.c++', '.cxx', '.h', '.s'] :
        return 'C' # C file family and ASM
    elif ext in ['.dts', '.dtsi'] :
        return 'D' # Devicetree files
    elif name[:7] == 'kconfig' and ext != '.rst':
        # Some files are named like Kconfig-nommu so we only check the first 7 letters
        # We also exclude documentation files that can be named kconfig
        return 'K' # Kconfig files
    elif name[:8] == 'makefile' and ext != '.rst' or ext == '.mk':
        return 'M' # Makefiles
    else :
        return None

# 1 char values are file families
# 2 chars values with a M are macros families
compatibility_list = {
    'C' : ['C', 'K'],
    'K' : ['K'],
    'D' : ['D', 'CM'],
    'M' : ['K']
}

# Check if families are compatible
# First argument can be a list of different families
# Second argument is the key for choosing the right array in the compatibility list
def compatibleFamily(file_family, requested_family):
    return any(item in file_family for item in compatibility_list[requested_family])

# Check if a macro is compatible with the requested family
# First argument can be a list of different families
# Second argument is the key for choosing the right array in the compatibility list
def compatibleMacro(macro_family, requested_family):
    result = False
    for item in macro_family:
        item += 'M'
        result = result or item in compatibility_list[requested_family]
    return result
