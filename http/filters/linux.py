# Elixir Python definitions for Linux

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

exec(open('cpppathinc.py').read())
# include/uapi contains includes to user headers under #ifndef __KERNEL__
# Our solution is to ignore all includes in such paths
cpppathinc_filters['path_exceptions'] = {'^/include/uapi/.*'}
