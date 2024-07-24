#!/usr/bin/env python3
#!/usr/local/elixir/profile.sh

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

import time
from simple_profiler import SimpleProfiler
prof = SimpleProfiler()

total_start = time.time_ns()

# prepare a default globals dict to be later used for filter context
default_globals = {
    **globals(),
}

import_start = time.time_ns()

import cgi
import cgitb
import logging
import os
import re
import sys
from collections import OrderedDict, namedtuple
from re import search, sub
from urllib import parse
import jinja2
import pygments
import pygments.lexers
import pygments.formatters

sys.path = [ sys.path[0] + '/..' ] + sys.path
from lib import validFamily
from query import Query, SymbolInstance

prof.add_event('import', time.time_ns() - import_start)

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
        'topbar_families': topbar_families,

        'error_title': title,
    }

    if details is not None:
        template_ctx['error_details'] = details

    template = ctx.jinja_env.get_template('error.html')
    with prof.measure_block('template_render'):
        return template.render(template_ctx)

# Represents a parsed `source` URL path
# project: name of the project, ex: "musl"
# version: tagged commit of the project, ex: "v1.2.5"
# path: path to the requested file, starts with a slash, ex: "/src/prng/lrand48.c"
ParsedSourcePath = namedtuple('ParsedSourcePath', 'project, version, path')

# Parse `source` route URL path into parts
# NOTE: All parts are unquoted
def parse_source_path(path):
    m = search('^/([^/]*)/([^/]*)/[^/]*(.*)$', path)
    if m:
        return ParsedSourcePath(m.group(1), m.group(2), m.group(3))

# Converts ParsedSourcePath to a string with corresponding URL path
def stringify_source_path(ppath):
    path = f'/{ppath.project}/{ppath.version}/source{ppath.path}'
    return path.rstrip('/')

# Returns 301 redirect to path with trailing slashes removed if path has a trailing slash
def redirect_on_trailing_slash(path):
    if path[-1] == '/':
        return (301, path.rstrip('/'))

# Handles `source` URL, returns a response
# path: string with URL path of the request
def handle_source_url(ctx):
    status = redirect_on_trailing_slash(ctx.path)
    if status is not None:
        return status

    parsed_path = parse_source_path(ctx.path)
    if parsed_path is None:
        ctx.config.logger.error("Error: failed to parse path in handle_source_url %s", ctx.path)
        return (404, get_error_page(ctx, "Failed to parse path"))

    query = get_query(ctx.config.project_dir, parsed_path.project)
    if not query:
        return (404, get_error_page(ctx, "Unknown project"))

    # Check if path contains only allowed characters
    if not search('^[A-Za-z0-9_/.,+-]*$', parsed_path.path):
        return (400, get_error_page(ctx, "Path contains characters that are not allowed."))

    if parsed_path.version == 'latest':
        new_parsed_path = parsed_path._replace(version=parse.quote(query.query('latest')))
        return (301, stringify_source_path(new_parsed_path))

    return generate_source_page(ctx, query, parsed_path)


# Represents a parsed `ident` URL path
# project: name of the project, ex: musl
# version: tagged commit of the project, ex: v1.2.5
# family: searched symbol family, replaced with C if unknown, ex: A
# ident: searched identificator, ex: fpathconf
ParsedIdentPath = namedtuple('ParsedIdentPath', 'project, version, family, ident')

# Parse `ident` route URL path into parts
# NOTE: All parts are unquoted
def parse_ident_path(path):
    m = search('^/([^/]*)/([^/]*)(?:/([^/]))?/[^/]*(.*)$', path)

    if m:
        family = str(m.group(3)).upper()
        # If identifier family extracted from the path is unknown,
        # replace it with C - the default family.
        # This also handles ident paths without a family,
        # ex: https://elixir.bootlin.com/linux/v6.10/ident/ROOT_DEV
        if not validFamily(family):
            family = 'C'

        parsed_path = ParsedIdentPath(
            m.group(1),
            m.group(2),
            family,
            m.group(4)[1:]
        )

        return parsed_path

# Converts ParsedIdentPath to a string with corresponding URL path
def stringify_ident_path(ppath):
    path = f'/{ppath.project}/{ppath.version}/{ppath.family}/ident/{ppath.ident}'
    return path.rstrip('/')

# Handles `ident` URL post request, returns a permanent redirect to ident/$ident_name
# parsed_path: ParsedIdentPath
# form: cgi.FieldStorage with parsed POST request form
def handle_ident_post_form(parsed_path, form):
    post_ident = form.getvalue('i')
    post_family = str(form.getvalue('f')).upper()

    if parsed_path.ident == '' and post_ident:
        post_ident = parse.quote(post_ident.strip(), safe='/')
        new_parsed_path = parsed_path._replace(
            family=post_family,
            ident=post_ident
        )
        return (302, stringify_ident_path(new_parsed_path))

# Handles `ident` URL, returns a response
# path: string with URL path
# params: cgi.FieldStorage with request parameters
def handle_ident_url(ctx):
    parsed_path = parse_ident_path(ctx.path)
    if parsed_path is None:
        ctx.config.logger.error("Error: failed to parse path in handle_ident_url %s", ctx.path)
        return (404, get_error_page(ctx, "Invalid path."))

    status = handle_ident_post_form(parsed_path, ctx.params)
    if status is not None:
        return status

    query = get_query(ctx.config.project_dir, parsed_path.project)
    if not query:
        return (404, get_error_page(ctx, "Unknown project."))

    # Check if identifier contains only allowed characters
    if not parsed_path.ident or not search('^[A-Za-z0-9_\$\.%-]*$', parsed_path.ident):
        return (400, get_error_page(ctx, "Identifier is invalid."))

    if parsed_path.version == 'latest':
        new_parsed_path = parsed_path._replace(version=parse.quote(query.query('latest')))
        return (301, stringify_ident_path(new_parsed_path))

    return generate_ident_page(ctx, query, parsed_path)


# Calls proper handler functions based on URL path, returns 404 if path is unknown
# path: path part of the URL
# params: cgi.FieldStorage with request parameters
def route(ctx):
    if search('^/[^/]*/[^/]*/source.*$', ctx.path) is not None:
        return handle_source_url(ctx)
    elif search('^/[^/]*/[^/]*(?:/[^/])?/ident.*$', ctx.path) is not None:
        return handle_ident_url(ctx)
    else:
        return (404, get_error_page(ctx, "Unknown path."))


# Dictionary of families available in the search bar
topbar_families = {
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
@prof.measure_function('get_projects')
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
@prof.measure_function('get_versions')
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
@prof.measure_function('get_layout_template_context')
def get_layout_template_context(q, ctx, get_url_with_new_version, project, version):
    return {
        'projects': get_projects(ctx.config.project_dir),
        'versions': get_versions(q.query('versions'), get_url_with_new_version),
        'topbar_families': topbar_families,

        'source_base_url': f'/{ project }/{ version }/source',
        'ident_base_url': f'/{ project }/{ version }/ident',
        'current_project': project,
        'current_tag': parse.unquote(version),
    }

# Guesses file format based on filename, returns code formatted as HTML
@prof.measure_function('format_code')
def format_code(filename, code):
    try:
        with prof.measure_block('guess_lexer_for_filename'):
            lexer = pygments.lexers.guess_lexer_for_filename(filename, code)
    except pygments.util.ClassNotFound:
        lexer = pygments.lexers.get_lexer_by_name('text')

    lexer.stripnl = False
    with prof.measure_block('construct_html_formatter'):
        formatter = pygments.formatters.HtmlFormatter(linenos=True, anchorlinenos=True)
    with prof.measure_block('highlight'):
        return pygments.highlight(code, lexer, formatter)

# Return true if filter can be applied to file based on path of the file
def filter_applies(filter, path):
    if 'path_exceptions' in filter:
        for p in filter['path_exceptions']:
            if re.match(p, path):
                return False

    dir, filename = os.path.split(path)
    filename, extension = os.path.splitext(filename)

    c = filter['case']
    if c == 'any':
        return True
    elif c == 'filename':
        return filename in filter['match']
    elif c == 'extension':
        return extension in filter['match']
    elif c == 'path':
        return dir.startswith(tuple(filter['match']))
    elif c == 'filename_extension':
        return filename.endswith(tuple(filter['match']))
    else:
        raise ValueError('Invalid filter case', filter['case'])

# Generate formatted HTML of a file, apply filters (for ex. to add identifier links)
# q: Query object
# project: name of the requested project
# version: requested version of the project
# path: path to the file in the repository
@prof.measure_function('generate_source')
def generate_source(q, project, version, path):
    version_unquoted = parse.unquote(version)
    code = q.query('file', version_unquoted, path)

    fdir, fname = os.path.split(path)
    filename, extension = os.path.splitext(fname)
    extension = extension[1:].lower()
    family = q.query('family', fname)

    # globals required by filters
    # this dict is also modified by filters - most introduce new, global variables 
    # that are later used by prefunc/postfunc
    filter_ctx = {
        **default_globals,
        "os": os,
        "parse": parse,
        "re": re,
        "dts_comp_support": q.query('dts-comp'),

        "version": version,
        "family": family,
        "project": project,
        "path": path,
        "tag": version_unquoted,
        "q": q,
    }

    # Source common filter definitions
    os.chdir('filters')
    exec(open("common.py").read(), filter_ctx)

    # Source project specific filters
    f = project + '.py'
    if os.path.isfile(f):
        exec(open(f).read(), filter_ctx)
    os.chdir('..')

    filters = filter_ctx["filters"]

    # Apply filters
    for f in filters:
        if filter_applies(f, path):
            code = sub(f['prerex'], f['prefunc'], code, flags=re.MULTILINE)

    result = format_code(fname, code)

    # Replace line numbers by links to the corresponding line in the current file
    result = sub('href="#-(\d+)', 'name="L\\1" id="L\\1" href="#L\\1', result)

    for f in filters:
        if filter_applies(f, path):
            result = sub(f['postrex'], f['postfunc'], result)

    return result

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
@prof.measure_function('get_directory_entries')
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
# q: Query object
# basedir: path to data directory, ex: "/srv/elixir-data"
# parsed_path: ParsedSourcePath
def generate_source_page(ctx, q, parsed_path):
    status = 200

    project = parsed_path.project
    version = parsed_path.version
    path = parsed_path.path
    version_unquoted = parse.unquote(version)
    source_base_url = f'/{ project }/{ version }/source'

    type = q.query('type', version_unquoted, path)

    if type == 'tree':
        prof.set_category('tree')
        back_path = os.path.dirname(path[:-1])
        if back_path == '/':
            back_path = ''

        template_ctx = {
            'dir_entries': get_directory_entries(q, source_base_url, version_unquoted, path),
            'back_url': f'{ source_base_url }{ back_path }' if path != '' else None,
        }
        template = ctx.jinja_env.get_template('tree.html')
    elif type == 'blob':
        prof.set_category('blob')
        template_ctx = {
            'code': generate_source(q, project, version, path),
        }
        template = ctx.jinja_env.get_template('source.html')
    else:
        status = 404
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

    get_url_with_new_version = lambda v: stringify_source_path(parsed_path._replace(version=parse.quote(v, safe='')))

    # Create template context
    data = {
        **get_layout_template_context(q, ctx, get_url_with_new_version, project, version),

        'title_path': title_path,
        'breadcrumb_links': breadcrumb_links,

        **template_ctx,
    }

    with prof.measure_block('template_render'):
        return (status, template.render(data))


# Represents a symbol occurrence to be rendered by ident template
# type: type of the symbol
# path: path of the file that contains the symbol
# line: list of tuples (line number, URL of the symbol occurrence in the file)
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
        (l, f'{ base_url }/{ symbol.path }#L{ l }')
        for l in line_numbers
    ]

    return SymbolEntry(symbol.type, symbol.path, lines)

# Generates response (status code and optionally HTML) of the `ident` route
# q: Query object
# basedir: path to data directory, ex: "/srv/elixir-data"
# parsed_path: ParsedIdentPath
def generate_ident_page(ctx, q, parsed_path):
    status = 200
    prof.set_category('ident')

    ident = parsed_path.ident
    version = parsed_path.version
    version_unquoted = parse.unquote(version)
    family = parsed_path.family
    project = parsed_path.project
    source_base_url = f'/{ project }/{ version }/source'

    with prof.measure_block('ident_query'):
        symbol_definitions, symbol_references, symbol_doccomments = q.query('ident', version_unquoted, ident, family)

    symbol_sections = []

    if len(symbol_definitions) or len(symbol_references):
        with prof.measure_block('ident_preparation'):
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
            status = 404

    get_url_with_new_version = lambda v: stringify_ident_path(parsed_path._replace(version=parse.quote(v, safe='')))

    data = {
        **get_layout_template_context(q, ctx, get_url_with_new_version, project, version),

        'searched_ident': ident,
        'current_family': family,

        'symbol_sections': symbol_sections,
    }

    template = ctx.jinja_env.get_template('ident.html')
    with prof.measure_block('template_render'):
        return (status, template.render(data))


# Enables cgitb module based on global context
def enable_cgitb():
    # Create /tmp/elixir-errors if not existing yet (could happen after a reboot)
    errdir = '/tmp/elixir-errors'

    if not(os.path.isdir(errdir)):
        os.makedirs(errdir, exist_ok=True)

    # Enable CGI Trackback Manager for debugging (https://docs.python.org/fr/3/library/cgitb.html)
    cgitb.enable(display=0, logdir=errdir, format='text')

# Elixir config, currently contains only path to directory with projects and a logger
Config = namedtuple('Config', 'project_dir, logger')

# Builds a Config instance from global context
def get_config():
    return Config(os.environ['LXR_PROJ_DIR'], logging.getLogger(__name__))

# Basic information about handled request - current Elixir configuration, configured Jinja environment,
# request path and parameters
RequestContext = namedtuple('RequestContext', 'config, jinja_env, path, params')

# Builds a RequestContext instance from global context
def get_request_context():
    script_dir = os.path.dirname(os.path.realpath(__file__))
    templates_dir = os.path.join(script_dir, '../templates/')
    loader = jinja2.FileSystemLoader(templates_dir)
    environment = jinja2.Environment(loader=loader, bytecode_cache=jinja2.FileSystemBytecodeCache('/tmp/jinja-cache'))

    path = os.environ.get('REQUEST_URI') or os.environ.get('SCRIPT_URL')

    # parses and stores request parameters, both query string and POST request form
    request_params = cgi.FieldStorage()

    return RequestContext(get_config(), environment, path, request_params)

@prof.measure_function('handle_request')
def handle_request():
    enable_cgitb()
    ctx = get_request_context()
    result = route(ctx)

    if result is not None:
        if result[0] == 200:
            print('Content-Type: text/html;charset=utf-8\n')
            print(result[1], end='')
        elif result[0] == 301:
            print('Status: 301 Moved Permanently')
            print('Location: '+ result[1] +'\n')
        elif result[0] == 302:
            print('Status: 302 Found')
            print('Location: '+ result[1] +'\n')
        elif result[0] == 400:
            print('Status: 400 Bad Request')
            print('Content-Type: text/html;charset=utf-8\n')
            print(result[1], end='')
        elif result[0] == 404:
            print('Status: 404 Not Found')
            print('Content-Type: text/html;charset=utf-8\n')
            print(result[1], end='')
        else:
            print('Status: 500 Internal Server Error')
            print('Content-Type: text/html;charset=utf-8\n')
            ctx.config.logger.error('Error - route returned an unknown status code %s', str(result))
            print('Unknown error - check error logs for details\n')
    else:
        print('Status: 500 Internal Server Error')
        print('Content-Type: text/html;charset=utf-8\n')
        ctx.config.logger.error('Error - route returned None')
        print('Unknown error - check error logs for details\n')

if __name__ == '__main__':
    handle_request()
    prof.set_total(time.time_ns() - total_start)
    prof.log_to_file("/tmp/elixir-profiler-logs")

