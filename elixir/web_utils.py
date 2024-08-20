import re
from urllib import parse
import falcon

from .lib import validFamily

# Validates and unquotes project parameter
class ProjectConverter(falcon.routing.BaseConverter):
    def convert(self, value: str):
        value = parse.unquote(value)
        if re.match(r'^[a-zA-Z0-9-]+$', value):
            return value.strip()

def validate_version(version):
    if re.match(r'^[a-zA-Z0-9_.,:/-]+$', version):
        return version.strip()

# Validates and unquotes version parameter
class VersionConverter(falcon.routing.BaseConverter):
    def convert(self, value: str):
        value = parse.unquote(value)
        return validate_version(value)

# Validates and unquotes identifier parameter
class IdentConverter(falcon.routing.BaseConverter):
    def convert(self, value: str):
        value = parse.unquote(value)
        if re.match(r'^[A-Za-z0-9_,.+?#-]+$', value):
            return value.strip()

# Returns default family if family is not valid
class FamilyConverter(falcon.routing.BaseConverter):
    def convert(self, value: str):
        value = parse.unquote(value)
        if not validFamily(value):
            value = 'C'
        return value

