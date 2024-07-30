# Common filters
from filters.utils import encode_number, decode_number
from filters.ident import IdentFilter
from filters.dtscompB import DtsCompBFilter
from filters.dtscompC import DtsCompCFilter
from filters.dtscompD import DtsCompDFilter

new_filters = [
    IdentFilter(),
]

if dts_comp_support:
    new_filters = [
        DtsCompBFilter(),
        DtsCompCFilter(),
        DtsCompDFilter(),
    ] + new_filters

filters = []
exec(open('cppinc.py').read())
