from .ident import IdentFilter

from .cppinc import CppIncFilter
from .cpppathinc import CppPathIncFilter

from .defconfig import DefConfigIdentsFilter
from .configin import ConfigInFilter

from .kconfig import KconfigFilter
from .kconfigidents import KconfigIdentsFilter

from .dtsi import DtsiFilter
from .dtscompC import DtsCompCFilter
from .dtscompD import DtsCompDFilter
from .dtscompB import DtsCompBFilter

from .makefileo import MakefileOFilter
from .makefiledtb import MakefileDtbFilter
from .makefiledir import MakefileDirFilter
from .makefilesubdir import MakefileSubdirFilter
from .makefilefile import MakefileFileFilter
from .makefilesrctree import MakefileSrcTreeFilter
from .makefilesubdir import MakefileSubdirFilter


def get_common_kconfig_filters():
    return [
        KconfigFilter(),
        KconfigIdentsFilter(),
        DefConfigIdentsFilter(),
    ]

def get_common_filters():
    return [
        DtsCompCFilter(),
        DtsCompDFilter(),
        DtsCompBFilter(),
        IdentFilter(),
        CppIncFilter(),
    ]

project_filters = {
    'amazon-freertos': lambda: [
        MakefileSubdirFilter(),
    ],
    'arm-trusted-firmware': lambda: [
        CppPathIncFilter(),
    ],
    'barebox': lambda: [
        DtsiFilter(),
        *get_common_kconfig_filters(),
        CppPathIncFilter(),
        MakefileOFilter(),
        MakefileDtbFilter(),
        MakefileDirFilter(),
        MakefileSubdirFilter(),
        MakefileFileFilter(),
        MakefileSrcTreeFilter(),
    ],
    'coreboot': lambda: [
        DtsiFilter(),
        *get_common_kconfig_filters(),
    ],
    'linux': lambda: [
        DtsiFilter(),
        *get_common_kconfig_filters(),
        MakefileOFilter(),
        MakefileDtbFilter(),
        MakefileDirFilter(),
        MakefileFileFilter(),
        MakefileSubdirFilter(),
        MakefileSrcTreeFilter(),
        # include/uapi contains includes to user headers under #ifndef __KERNEL__
        # Our solution is to ignore all includes in such paths
        CppPathIncFilter({'^/include/uapi/.*'}),
    ],
    'qemu': lambda: [
        *get_common_kconfig_filters(),
    ],
    'u-boot': lambda: [
        DtsiFilter(),
        *get_common_kconfig_filters(),
        CppPathIncFilter(),
        MakefileOFilter(),
        MakefileDtbFilter(),
        MakefileDirFilter(),
        MakefileSubdirFilter(),
        MakefileFileFilter(),
        MakefileSrcTreeFilter(),
    ],
    'uclibc-ng': lambda: [
        ConfigInFilter(),
    ],
    'zephyr': lambda: [
        DtsiFilter(),
        *get_common_kconfig_filters(),
        CppPathIncFilter(),
    ],
}
