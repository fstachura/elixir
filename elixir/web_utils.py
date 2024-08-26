import os
import re
import logging
from urllib import parse
from typing import Any, NamedTuple
import falcon
import jinja2

from .lib import validFamily

# Elixir config, currently contains only path to directory with projects
class Config(NamedTuple):
    project_dir: str

# Basic information about handled request - current Elixir configuration, configured Jinja environment
# and logger
class RequestContext(NamedTuple):
    config: Config
    jinja_env: jinja2.Environment
    logger: logging.Logger

# Builds a RequestContext instance from global context
def get_request_context(environ: dict[str, Any]) -> RequestContext:
    script_dir = os.path.dirname(os.path.realpath(__file__))
    templates_dir = os.path.join(script_dir, '../templates/')
    loader = jinja2.FileSystemLoader(templates_dir)
    environment = jinja2.Environment(loader=loader)

    # TODO - config should probably be read from a file and passed to resource classes,
    # not read from apache config environment that's passed to each request
    return RequestContext(Config(environ['LXR_PROJ_DIR']), environment, logging.getLogger("web"))

def validate_project(project: str) -> str|None:
    if project is not None and re.match(r'^[a-zA-Z0-9_.,:/-]+$', project):
        return project.strip()

# Validates and unquotes project parameter
class ProjectConverter(falcon.routing.BaseConverter):
    def convert(self, value: str) -> str:
        value = parse.unquote(value)
        project = validate_project(value)
        if project is None:
            raise falcon.HTTPBadRequest('Error', 'Invalid project name')
        return project

def validate_version(version) -> str|None:
    if version is not None and re.match(r'^[a-zA-Z0-9_.,:/-]+$', version):
        return version.strip()

# Validates and unquotes version parameter
class VersionConverter(falcon.routing.BaseConverter):
    def convert(self, value: str) -> str:
        value = parse.unquote(value)
        version = validate_version(value)
        if version is None:
            raise falcon.HTTPBadRequest('Error', 'Invalid version name')
        return version

def validate_ident(ident) -> str|None:
    if ident is not None and re.match(r'^[A-Za-z0-9_,.+?#-]+$', ident):
        return ident.strip()

# Validates and unquotes identifier parameter
class IdentConverter(falcon.routing.BaseConverter):
    def convert(self, value: str) -> str:
        value = parse.unquote(value)
        ident = validate_ident(value)
        if ident is None:
            raise falcon.HTTPBadRequest('Error', 'Invalid identifier')
        return ident

# Returns default family if family is not valid
class FamilyConverter(falcon.routing.BaseConverter):
    def convert(self, value: str) -> str:
        value = parse.unquote(value)
        if not validFamily(value):
            value = 'C'
        return value

