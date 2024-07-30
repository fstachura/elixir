import re
from filters.utils import Filter, FilterContext, encode_number, decode_number

# Filter for identifier links
# Replaces identifiers marked by Query.query('file') with links to ident page
class IdentFilter(Filter):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.idents = []

    def check_if_applies(self, ctx, path: str) -> bool:
        return super().check_if_applies(ctx, path)

    def transform_raw_code(self, ctx, code: str) -> str:
        def sub_func(m):
            self.idents.append(m.group(1))
            return '__KEEPIDENTS__' + encode_number(len(self.idents))

        return re.sub('\033\[31m(?!CONFIG_)(.*?)\033\[0m', sub_func, code, flags=re.MULTILINE)

    def untransform_formatted_code(self, ctx: FilterContext, html: str) -> str:
        def sub_func(m):
            i = self.idents[decode_number(m.group(2)) - 1]
            link = f'<a class="ident" href="{ ctx.get_ident_url(i) }">{ i }</a>'
            return str(m.group(1) or '') + link

        return re.sub('__(<.+?>)?KEEPIDENTS__([A-J]+)', sub_func, html, flags=re.MULTILINE)

