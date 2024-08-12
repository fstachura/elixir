from os.path import dirname
import re
from filters.utils import Filter, FilterContext, decode_number, encode_number, filename_without_ext_matches, pick_query_exists

# Filters for Makefile directory includes as follows:
# obj-$(VALUE) += dir/
# Example: u-boot/v2023.10/source/Makefile#L867
class MakefileDirFilter(Filter):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.makefiledir = []

    def check_if_applies(self, ctx) -> bool:
        return super().check_if_applies(ctx) and \
                filename_without_ext_matches(ctx.filepath, {'Makefile'})

    dir_matcher = '(?<=\s)([-\w/]+)/(\s+|$)'

    def transform_raw_code(self, ctx, code: str) -> str:
        results = re.findall(self.dir_matcher, code, flags=re.MULTILINE)
        file_exists = pick_query_exists(len(results), ctx.query, ctx.tag)

        def keep_makefiledir(m):
            filedir = dirname(ctx.filepath)

            if filedir != '/':
                filedir += '/'

            if file_exists(filedir + m.group(1) + '/Makefile'):
                self.makefiledir.append(m.group(1))
                return f'__KEEPMAKEFILEDIR__{ encode_number(len(self.makefiledir)) }/{ m.group(2) }'
            else:
                return m.group(0)

        return re.sub(self.dir_matcher, keep_makefiledir, code, flags=re.MULTILINE)

    def untransform_formatted_code(self, ctx: FilterContext, html: str) -> str:
        def replace_makefiledir(m):
            w = self.makefiledir[decode_number(m.group(1)) - 1]
            filedir = dirname(ctx.filepath)

            if filedir != '/':
                filedir += '/'

            fpath = f'{ filedir }{ w }/Makefile'

            return f'<a href="{ ctx.get_absolute_source_url(fpath) }">{ w }/</a>'

        return re.sub('__KEEPMAKEFILEDIR__([A-J]+)/', replace_makefiledir, html, flags=re.MULTILINE)

