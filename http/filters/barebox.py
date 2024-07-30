# Elixir Python definitions for Barebox

from filters.dtsi import DtsiFilter

from filters.kconfig import KconfigFilter
from filters.kconfigidents import KconfigIdentsFilter
from filters.defconfig import DefConfigIdentsFilter

from filters.makefileo import MakefileOFilter
from filters.makefiledtb import MakefileDtbFilter
from filters.makefiledir import MakefileDirFilter
from filters.makefilesubdir import MakefileSubdirFilter
from filters.makefilefile import MakefileFileFilter
from filters.makefilesrctree import MakefileSrcTreeFilter

exec(open('cpppathinc.py').read())

new_filters.extend([
    DtsiFilter(),

    KconfigFilter(),
    KconfigIdentsFilter(),
    DefConfigIdentsFilter(),

    MakefileOFilter(),
    MakefileDtbFilter(),
    MakefileDirFilter(),
    MakefileSubdirFilter(),
    MakefileFileFilter(),
    MakefileSrcTreeFilter(),
])
