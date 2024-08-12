import re
from filters.utils import Filter, FilterContext, decode_number, encode_number, filename_without_ext_matches, pick_query_exists

# Filters for files listed in Makefiles using $(srctree)
# $(srctree)/Makefile
# Example: u-boot/v2023.10/source/Makefile#L1983
class MakefileSrcTreeFilter(Filter):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.makefilesrctree = []

    def check_if_applies(self, ctx) -> bool:
        return super().check_if_applies(ctx) and \
            filename_without_ext_matches(ctx.filepath, {'Makefile'})

    srctree_matcher = '(?:(?<=\s|=)|(?<=-I))(?!/)\$\(srctree\)/((?:[-\w/]+/)?[-\w\.]+)(\s+|\)|$)'

    def transform_raw_code(self, ctx, code: str) -> str:
        results = re.findall(self.srctree_matcher, code, flags=re.MULTILINE)
        file_exists = pick_query_exists(len(results), ctx.query, ctx.tag)

        def keep_makefilesrctree(m):
            if file_exists('/' + m.group(1)):
                self.makefilesrctree.append(m.group(1))
                return f'__KEEPMAKEFILESRCTREE__{ encode_number(len(self.makefilesrctree)) }{ m.group(2) }'
            else:
                return m.group(0)

        return re.sub(self.srctree_matcher, keep_makefilesrctree, code, flags=re.MULTILINE)

    def untransform_formatted_code(self, ctx: FilterContext, html: str) -> str:
        def replace_makefilesrctree(m):
            w = self.makefilesrctree[decode_number(m.group(1)) - 1]
            url = ctx.get_absolute_source_url(w)
            return f'<a href="{ url }">$(srctree)/{ w }</a>'

        return re.sub('__KEEPMAKEFILESRCTREE__([A-J]+)', replace_makefilesrctree, html, flags=re.MULTILINE)

