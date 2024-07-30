import re
from os.path import split, splitext
from typing import List
from query import Query

# Context data used by Filters
# tag: browsed version, unqoted 
# family: family of file
# path: path of file
# get_ident_url: function that returns URL to identifier passed as argument
# get_absolute_source_url: function that returns a URL to file with absolute path passed as an argument
# get_relative_source_url: function that returns a URL to file in directory of current file
class FilterContext:
    def __init__(self, query: Query, tag, family, path, get_ident_url, get_absolute_source_url, get_relative_source_url):
        self.query = query
        self.tag = tag
        self.family = family
        self.path = path
        self.get_ident_url = get_ident_url
        self.get_absolute_source_url = get_absolute_source_url
        self.get_relative_source_url = get_relative_source_url

# Filter interface/base class
class Filter:
    def __init__(self, path_exceptions: List[str] = []):
        self.path_exceptions = []

    # Return True if filter can be applied to file with path
    def check_if_applies(self, ctx: FilterContext, path: str) -> bool:
        for p in self.path_exceptions:
            if re.match(p, path):
                return False

        return True

    # Add information required by filter by transforming raw source code.
    # Known identifiers are marked by '\033[31m' and '\033[0m'
    def transform_raw_code(self, ctx: FilterContext, code: str) -> str:
        return code

    # Replace information left by `transform_raw_code` with target HTML
    # html: HTML output from code formatter 
    def untransform_formatted_code(self, ctx: FilterContext, html: str) -> str:
        return html

def filename_without_ext_matches(path: str, filenames) -> bool:
    _, full_filename = split(path)
    filename, _ = splitext(full_filename)
    return filename in filenames

def extension_matches(path: str, extensions) -> bool:
    _, extension = splitext(path)
    extension = extension[1:].lower()
    return extension in extensions


def encode_number(number):
    result = ''

    while number != 0:
        number, rem = divmod(number, 10)
        rem = chr(ord('A') + rem)
        result = rem + result

    return result


def decode_number(string):
    result = ''

    while string != '':
        string, char = string[:-1], string[-1]
        char = str(ord(char) - ord('A'))
        result = char + result

    return int(result)

