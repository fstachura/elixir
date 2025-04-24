from .filters import *
from .project_utils import ProjectConfig

# Dictionary of custom per-projects settings.
# filters: List of filters that add extra formatting information to rendered source
# You can pass additional options to filters by putting a Filter
# class and a dictionary with options in a tuple, like this:
# (FilterCls, {"option": True}).
# Check files in elixir/filters for documentation on available filters 
projects = {
    'amazon-freertos': ProjectConfig(
        filters=[
            *default_filters,
            MakefileSubdirFilter,
        ],
    ),
    'arm-trusted-firmware': ProjectConfig(
        filters=[
            *default_filters,
            CppPathIncFilter,
        ],
    ),
    'barebox': ProjectConfig(
        filters=[
            *default_filters,
            DtsiFilter,
            *common_kconfig_filters,
            CppPathIncFilter,
            *common_makefile_filters,
        ],
    ),
    'coreboot': ProjectConfig(
        filters=[
            *default_filters,
            DtsiFilter,
            *common_kconfig_filters,
            *common_makefile_filters,
        ],
    ),
    'iproute2': ProjectConfig(
        filters=[
            *default_filters,
            *common_makefile_filters,
        ],
    ),
    'linux': ProjectConfig(
        filters=[
            *default_filters,
            DtsiFilter,
            *common_kconfig_filters,
            *common_makefile_filters,
            # include/uapi contains includes to user headers under #ifndef __KERNEL__
            # Our solution is to ignore all includes in such paths
            (CppPathIncFilter, {"path_exceptions": {'^/include/uapi/.*'}}),
        ],
    ),
    'opensbi': ProjectConfig(
        filters=[
            *default_filters,
            *common_kconfig_filters,
        ],
    ),
    'qemu': ProjectConfig(
        filters=[
            *default_filters,
            *common_kconfig_filters,
        ],
    ),
    'u-boot': ProjectConfig(
        filters=[
            *default_filters,
            DtsiFilter,
            *common_kconfig_filters,
            CppPathIncFilter,
            *common_makefile_filters,
        ],
    ),
    'uclibc-ng': ProjectConfig(
        filters=[
            *default_filters,
            ConfigInFilter,
        ],
    ),
    'vpp': ProjectConfig(
        filters=[
            *default_filters,
            (CppPathIncFilter, {"prefix_path": ['src', 'src/plugins', 'src/vpp-api', 'src/vpp-api/vapi']}),
            MakefileFileFilter,
        ],
    ),
    'zephyr': ProjectConfig(
        filters=[
            *default_filters,
            DtsiFilter,
            *common_kconfig_filters,
            CppPathIncFilter,
        ],
    ),
}

