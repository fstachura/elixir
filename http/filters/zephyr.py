# Elixir Python definitions for Zephyr

from filters.dtsi import DtsiFilter

from filters.kconfig import KconfigFilter
from filters.kconfigidents import KconfigIdentsFilter
from filters.defconfig import DefConfigIdentsFilter

exec(open('cpppathinc.py').read())

new_filters.extend([
    DtsiFilter(),

    KconfigFilter(),
    KconfigIdentsFilter(),
    DefConfigIdentsFilter(),
])

