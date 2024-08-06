#!/usr/bin/env python3

#  This file is part of Elixir, a source code cross-referencer.
#
#  Copyright (C) 2017--2020 Mikaël Bouillot <mikael.bouillot@bootlin.com>
#  and contributors.
#
#  Elixir is free software: you can redistribute it and/or modify
#  it under the terms of the GNU Affero General Public License as published by
#  the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.
#
#  Elixir is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU Affero General Public License for more details.
#
#  You should have received a copy of the GNU Affero General Public License
#  along with Elixir.  If not, see <http://www.gnu.org/licenses/>.

import logging
import os
import re
import sys
from collections import OrderedDict, namedtuple
from re import search, sub
from urllib import parse
import falcon
import jinja2

ELIXIR_DIR = os.path.dirname(os.path.realpath(__file__)) + '/..'

if ELIXIR_DIR not in sys.path:
    sys.path = [ ELIXIR_DIR ] + sys.path

HTTP_DIR = os.path.dirname(os.path.realpath(__file__))

if HTTP_DIR not in sys.path:
    sys.path = [ HTTP_DIR ] + sys.path

from lib import validFamily
from query import Query, SymbolInstance
from filters import get_filters
from filters.utils import FilterContext


# Returns a Query class instance or None if project data directory does not exist
# basedir: absolute path to parent directory of all project data directories, ex. "/srv/elixir-data/"
# project: name of the project, directory in basedir, ex. "linux"
def get_query(basedir, project):
    datadir = basedir + '/' + project + '/data'
    repodir = basedir + '/' + project + '/repo'

    if not(os.path.exists(datadir)) or not(os.path.exists(repodir)):
        return None

    return Query(datadir, repodir)

def get_error_page(ctx, title, details=None):
    template_ctx = {
        'projects': get_projects(ctx.config.project_dir),
        'topbar_families': TOPBAR_FAMILIES,

        'error_title': title,
    }

    if details is not None:
        template_ctx['error_details'] = details

    template = ctx.jinja_env.get_template('error.html')
    return template.render(template_ctx)


# Converts ParsedSourcePath to a string with corresponding URL path
def stringify_source_path(project, version, path):
    if not path.startswith('/'):
        path = '/' + path
    path = f'/{ project }/{ version }/source{ path }'
    return path.rstrip('/')

class SourceResource:
    def on_get(self, req, resp, project, version, path):
        if not path.startswith('/') and len(path) != 0:
            path = f'/{ path }'

        if path.endswith('/'):
            raise falcon.HTTPFound(stringify_source_path(project, version, path))

        ctx = get_request_context(req.env)

        query = get_query(ctx.config.project_dir, project)
        if not query:
            resp.status = falcon.HTTP_NOT_FOUND
            resp.content_type = falcon.MEDIA_HTML
            resp.text = get_error_page(ctx, "Unknown project")
            return

        # Check if path contains only allowed characters
        if not search('^[A-Za-z0-9_/.,+-]*$', path):
            resp.status = falcon.HTTP_BAD_REQUEST
            resp.content_type  = falcon.MEDIA_HTML
            resp.text = get_error_page(ctx, "Path contains characters that are not allowed.")
            return

        if version == 'latest':
            version = parse.quote(query.query('latest'))
            raise falcon.HTTPFound(stringify_source_path(project, version, path))

        resp.content_type = falcon.MEDIA_HTML
        resp.status, resp.text = generate_source_page(ctx, query, project, version, path)


class SourceWithoutPathResource(SourceResource):
    def on_get(self, req, resp, project, version):
        return super().on_get(req, resp, project, version, '')


# Converts ParsedIdentPath to a string with corresponding URL path
def stringify_ident_path(project, version, family, ident):
    path = f'/{ project }/{ version }/{ family }/ident/{ ident }'
    return path.rstrip('/')

class IdentResource:
    # Handles `ident` URL, returns a response
    # ctx: RequestContext
    def on_get(self, req, resp, project, version, family, ident):
        # If identifier family extracted from the path is unknown,
        # replace it with C - the default family.
        # This also handles ident paths without a family,
        # ex: https://elixir.bootlin.com/linux/v6.10/ident/ROOT_DEV
        if not validFamily(family):
            family = 'C'

        ctx = get_request_context(req.env)

        query = get_query(ctx.config.project_dir, project)
        if not query:
            resp.status = falcon.HTTP_NOT_FOUND
            resp.content_type = falcon.MEDIA_HTML
            resp.text = get_error_page(ctx, "Unknown project.")
            return

        # Check if identifier contains only allowed characters
        if not ident or not search('^[A-Za-z0-9_\$\.%-]*$', ident):
            resp.status = falcon.HTTP_BAD_REQUEST
            resp.content_type = falcon.MEDIA_HTML
            resp.text = get_error_page(ctx, "Identifier is invalid.")
            return

        if version == 'latest':
            version = parse.quote(query.query('latest'))
            raise falcon.HTTPFound(stringify_ident_path(project, version, family, ident))

        resp.content_type = falcon.MEDIA_HTML
        resp.status, resp.text = generate_ident_page(ctx, query, project, version, family, ident)

class IdentWithoutFamilyResource(IdentResource):
    def on_get(self, req, resp, project, version, ident):
        super().on_get(req, resp, project, version, 'C', ident)

class IdentPostRedirectResource:
    def on_post(self, req, resp, project, version):
        form = req.get_media()
        post_ident = form.get('i')
        post_family = str(form.get('f')).upper()

        if post_ident:
            post_ident = parse.quote(post_ident.strip(), safe='/')
            new_path = stringify_ident_path(project, version, post_family, post_ident)
            raise falcon.HTTPFound(new_path)
        else:
            raise falcon.HTTPInternalServerError()


TOPBAR_FAMILIES = {
    'A': 'All symbols',
    'C': 'C/CPP/ASM',
    'K': 'Kconfig',
    'D': 'Devicetree',
    'B': 'DT compatible',
}

# Returns a list of names of top-level directories in basedir
def get_directories(basedir):
    directories = []
    for filename in os.listdir(basedir):
        filepath = os.path.join(basedir, filename)
        if os.path.isdir(filepath):
            directories.append(filename)
    return sorted(directories)

# Tuple of project name and URL to root of that project
# Used to render project list
ProjectEntry = namedtuple('ProjectEntry', 'name, url')

# Returns a list of ProjectEntry tuples of projects stored in directory basedir
def get_projects(basedir):
    return [ProjectEntry(p, f"/{p}/latest/source") for p in get_directories(basedir)]

# Tuple of version name and URL to chosen resource with that version
# Used to render version list in the sidebar
VersionEntry = namedtuple('VersionEntry', 'version, url')

# Takes result of Query.query('version') and prepares it for the sidebar template
# versions: OrderedDict with major parts of versions as keys, values are OrderedDicts
#   with minor version parts as keys and complete version strings as values
# get_url: function that takes a version string and returns the URL
#   for that version. Meaning of the URL can depend on the context
def get_versions(versions, get_url):
    result = OrderedDict()
    for major, minor_verions in versions.items():
        for minor, patch_versions in minor_verions.items():
            for v in patch_versions:
                if major not in result:
                    result[major] = OrderedDict()
                if minor not in result[major]:
                    result[major][minor] = []
                result[major][minor].append(VersionEntry(v, get_url(v)))

    return result

# Retruns template context used by the layout template
# q: Query object
# ctx: RequestContext object
# get_url_with_new_version: see get_url parameter of get_versions
# project: name of the project
# version: version of the project
def get_layout_template_context(q, ctx, get_url_with_new_version, project, version):
    return {
        'projects': get_projects(ctx.config.project_dir),
        'versions': get_versions(q.query('versions'), get_url_with_new_version),
        'topbar_families': TOPBAR_FAMILIES,

        'source_base_url': f'/{ project }/{ version }/source',
        'ident_base_url': f'/{ project }/{ version }/ident',
        'current_project': project,
        'current_tag': parse.unquote(version),
        'current_family': 'A',
    }

# Guesses file format based on filename, returns code formatted as HTML
def format_code(filename, code):
    import pygments
    import pygments.lexers
    import pygments.formatters

    try:
        lexer = pygments.lexers.guess_lexer_for_filename(filename, code)
    except pygments.util.ClassNotFound:
        lexer = pygments.lexers.get_lexer_by_name('text')

    lexer.stripnl = False
    formatter = pygments.formatters.HtmlFormatter(linenos=True, anchorlinenos=True)
    return pygments.highlight(code, lexer, formatter)

# Generate formatted HTML of a file, apply filters (for ex. to add identifier links)
# q: Query object
# project: name of the requested project
# version: requested version of the project
# path: path to the file in the repository
def generate_source(q, project, version, path):
    version_unquoted = parse.unquote(version)
    code = q.query('file', version_unquoted, path)

    _, fname = os.path.split(path)
    _, extension = os.path.splitext(fname)
    extension = extension[1:].lower()
    family = q.query('family', fname)

    source_base_url = f'/{ project }/{ version }/source'

    def get_ident_url(ident, ident_family=None):
        if ident_family is None:
            ident_family = family
        ident = parse.quote(ident, safe='')
        return stringify_ident_path(project, version, ident_family, ident)

    filter_ctx = FilterContext(
        q,
        version_unquoted,
        family,
        path,
        get_ident_url,
        lambda path: f'{ source_base_url }{ "/" if not path.startswith("/") else "" }{ path }',
        lambda rel_path: f'{ source_base_url }{ os.path.dirname(path) }/{ rel_path }',
    )

    filters = get_filters(filter_ctx, project)

    # Apply filters
    for f in filters:
        code = f.transform_raw_code(filter_ctx, code)

    html_code_block = format_code(fname, code)

    # Replace line numbers by links to the corresponding line in the current file
    html_code_block = sub('href="#-(\d+)', 'name="L\\1" id="L\\1" href="#L\\1', html_code_block)

    for f in filters:
        html_code_block = f.untransform_formatted_code(filter_ctx, html_code_block)

    return html_code_block


# Represents a file entry in git tree
# type: either tree (directory), blob (file) or symlink
# name: filename of the file
# path: path of the file, path to the target in case of symlinks
# url: absolute URL of the file
# size: int, file size in bytes, None for directories and symlinks
DirectoryEntry = namedtuple('DirectoryEntry', 'type, name, path, url, size')

# Returns a list of DirectoryEntry objects with information about files in a directory
# q: Query object
# base_url: file URLs will be created by appending file path to this URL. It shouldn't end with a slash
# tag: requested repository tag
# path: path to the directory in the repository
def get_directory_entries(q, base_url, tag, path):
    dir_entries = []
    lines = q.query('dir', tag, path)

    for l in lines:
        type, name, size, perm = l.split(' ')
        file_path = f"{ path }/{ name }"

        if type == 'tree':
            dir_entries.append(('tree', name, file_path, f"{ base_url }{ file_path }", None))
        elif type == 'blob':
            # 120000 permission means it's a symlink
            if perm == '120000':
                dir_path = path if path.endswith('/') else path + '/'
                link_contents = q.get_file_raw(tag, file_path)
                link_target_path = os.path.abspath(dir_path + link_contents)

                dir_entries.append(('symlink', name, link_target_path, f"{ base_url }{ link_target_path }", size))
            else:
                dir_entries.append(('blob', name, file_path, f"{ base_url }{ file_path }", size))

    return dir_entries

# Generates response (status code and optionally HTML) of the `source` route
# ctx: RequestContext
# q: Query object
# parsed_path: ParsedSourcePath
def generate_source_page(ctx, q, project, version, path):
    status = falcon.HTTP_OK

    version_unquoted = parse.unquote(version)
    source_base_url = f'/{ project }/{ version }/source'

    type = q.query('type', version_unquoted, path)

    if type == 'tree':
        back_path = os.path.dirname(path[:-1])
        if back_path == '/':
            back_path = ''

        template_ctx = {
            'dir_entries': get_directory_entries(q, source_base_url, version_unquoted, path),
            'back_url': f'{ source_base_url }{ back_path }' if path != '' else None,
        }
        template = ctx.jinja_env.get_template('tree.html')
    elif type == 'blob':
        template_ctx = {
            'code': generate_source(q, project, version, path),
        }
        template = ctx.jinja_env.get_template('source.html')
    else:
        status = falcon.HTTP_NOT_FOUND
        template_ctx = {
            'error_title': 'This file does not exist.',
        }
        template = ctx.jinja_env.get_template('error.html')


    # Generate breadcrumbs
    path_split = path.split('/')[1:]
    path_temp = ''
    breadcrumb_links = []
    for p in path_split:
        path_temp += '/'+p
        breadcrumb_links.append((p, f'{ source_base_url }{ path_temp }'))

    # Create titles like this:
    # root path: "Linux source code (v5.5.6) - Bootlin"
    # first level path: "arch - Linux source code (v5.5.6) - Bootlin"
    # deeper paths: "Makefile - arch/um/Makefile - Linux source code (v5.5.6) - Bootlin"
    if path == '':
        title_path = ''
    elif len(path_split) == 1:
        title_path = f'{ path_split[0] } - '
    else:
        title_path = f'{ path_split[-1] } - { "/".join(path_split) } - '

    get_url_with_new_version = lambda v: stringify_source_path(project, parse.quote(v, safe=''), path)

    # Create template context
    data = {
        **get_layout_template_context(q, ctx, get_url_with_new_version, project, version),

        'title_path': title_path,
        'breadcrumb_links': breadcrumb_links,

        **template_ctx,
    }

    return (status, template.render(data))

# Represents line in a file with URL to that line
LineWithURL = namedtuple('LineWithURL', 'lineno, url')

# Represents a symbol occurrence to be rendered by ident template
# type: type of the symbol
# path: path of the file that contains the symbol
# line: list of LineWithURL
SymbolEntry = namedtuple('SymbolEntry', 'type, path, lines')

# Converts SymbolInstance into SymbolEntry
# path of SymbolInstance will be appended to base_url
def symbol_instance_to_entry(base_url, symbol):
    # TODO this should be a responsibility of Query
    if type(symbol.line) is str:
        line_numbers = symbol.line.split(',')
    else:
        line_numbers = [symbol.line]

    lines = [
        LineWithURL(l, f'{ base_url }/{ symbol.path }#L{ l }')
        for l in line_numbers
    ]

    return SymbolEntry(symbol.type, symbol.path, lines)

# Generates response (status code and optionally HTML) of the `ident` route
# ctx: RequestContext
# basedir: path to data directory, ex: "/srv/elixir-data"
# parsed_path: ParsedIdentPath
def generate_ident_page(ctx, q, project, version, family, ident):
    status = falcon.HTTP_OK

    version_unquoted = parse.unquote(version)
    source_base_url = f'/{ project }/{ version }/source'

    ident_unquoted = parse.unquote(ident)
    symbol_definitions, symbol_references, symbol_doccomments = q.query('ident', version_unquoted, ident_unquoted, family)

    symbol_sections = []

    if len(symbol_definitions) or len(symbol_references):
        if len(symbol_definitions):
            defs_by_type = OrderedDict({})

            # TODO this should be a responsibility of Query
            for sym in symbol_definitions:
                if sym.type not in defs_by_type:
                    defs_by_type[sym.type] = [symbol_instance_to_entry(source_base_url, sym)]
                else:
                    defs_by_type[sym.type].append(symbol_instance_to_entry(source_base_url, sym))

            symbol_sections.append({
                'title': 'Defined',
                'symbols': defs_by_type,
            })
        else:
            symbol_sections.append({
                'message': 'No definitions found in the database',
            })

        if len(symbol_doccomments):
            symbol_sections.append({
                'title': 'Documented',
                'symbols': {'_unknown': [symbol_instance_to_entry(source_base_url, sym) for sym in symbol_doccomments]},
            })

        if len(symbol_references):
            symbol_sections.append({
                'title': 'Referenced',
                'symbols': {'_unknown': [symbol_instance_to_entry(source_base_url, sym) for sym in symbol_references]},
            })
        else:
            symbol_sections.append({
                'message': 'No references found in the database',
            })

    else:
        if ident != '':
            status = falcon.HTTP_NOT_FOUND

    get_url_with_new_version = lambda v: stringify_ident_path(project, parse.quote(v, safe=''), family, ident)

    data = {
        **get_layout_template_context(q, ctx, get_url_with_new_version, project, version),

        'searched_ident': ident_unquoted,
        'current_family': family,

        'symbol_sections': symbol_sections,
    }

    template = ctx.jinja_env.get_template('ident.html')
    return (status, template.render(data))

# Elixir config, currently contains only path to directory with projects and a logger
Config = namedtuple('Config', 'project_dir, logger')

# Builds a Config instance from global context
def get_config(environ):
    return Config(environ['LXR_PROJ_DIR'], logging.getLogger(__name__))

# Basic information about handled request - current Elixir configuration, configured Jinja environment
# and full request path
RequestContext = namedtuple('RequestContext', 'config, jinja_env')

# Builds a RequestContext instance from global context
def get_request_context(environ):
    script_dir = os.path.dirname(os.path.realpath(__file__))
    templates_dir = os.path.join(script_dir, '../templates/')
    loader = jinja2.FileSystemLoader(templates_dir)
    environment = jinja2.Environment(loader=loader)

    # TODO - config should probably be read from a file and passed to source classes,
    # not read from apache config environment passed to each request
    return RequestContext(get_config(environ), environment)

def get_application():
    app = falcon.App()
    app.add_route('/{project}/{version}/source/{path:path}', SourceResource())
    app.add_route('/{project}/{version}/source', SourceWithoutPathResource())
    app.add_route('/{project}/{version}/ident', IdentPostRedirectResource())
    app.add_route('/{project}/{version}/ident/{ident}', IdentWithoutFamilyResource())
    app.add_route('/{project}/{version}/{family}/ident/{ident}', IdentResource())
    return app

application = get_application()

