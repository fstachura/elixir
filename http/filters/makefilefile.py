from os.path import dirname
import re
from filters.utils import Filter, FilterContext, decode_number, encode_number, filename_without_ext_matches, pick_query_exists

# Filters for files listed in Makefiles
# path/file
# Example: u-boot/v2023.10/source/Makefile#L1509
class MakefileFileFilter(Filter):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.makefilefile = []

    def check_if_applies(self, ctx) -> bool:
        return super().check_if_applies(ctx) and \
                filename_without_ext_matches(ctx.filepath, {'Makefile'})

    file_matcher = '(?:(?<=\s|=)|(?<=-I))(?!/)([-\w/]+/[-\w\.]+)(\s+|\)|$)'

    def transform_raw_code(self, ctx, code: str) -> str:
        results = re.findall(self.file_matcher, code, flags=re.MULTILINE)
        file_exists = pick_query_exists(len(results), ctx.query, ctx.tag)

        def keep_makefilefile(m):
            filedir = dirname(ctx.filepath)

            if filedir != '/':
                filedir += '/'

            if file_exists(filedir + m.group(1)):
                self.makefilefile.append(m.group(1))
                return f'__KEEPMAKEFILEFILE__{ encode_number(len(self.makefilefile)) }{ m.group(2) }'
            else:
                return m.group(0)

        return re.sub(self.file_matcher, keep_makefilefile, code, flags=re.MULTILINE)

    def untransform_formatted_code(self, ctx: FilterContext, html: str) -> str:
        def replace_makefilefile(m):
            w = self.makefilefile[decode_number(m.group(1)) - 1]
            filedir = dirname(ctx.filepath)

            if filedir != '/':
                filedir += '/'

            npath = filedir + w
            return f'<a href="{ ctx.get_absolute_source_url(npath) }">{ w }</a>'

        return re.sub('__KEEPMAKEFILEFILE__([A-J]+)', replace_makefilefile, html, flags=re.MULTILINE)

