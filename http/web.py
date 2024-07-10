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

from io import StringIO
from urllib import parse

realprint = print
outputBuffer = StringIO()

def print(arg, end='\n'):
    global outputBuffer
    outputBuffer.write(arg + end)

import cgitb
import cgi
import os
import re
from re import search, sub

import sys
sys.path = [ sys.path[0] + '/..' ] + sys.path
from lib import validFamily
from query import Query

q = None

# Create /tmp/elixir-errors if not existing yet (could happen after a reboot)
errdir = '/tmp/elixir-errors'

if not(os.path.isdir(errdir)):
    os.makedirs(errdir, exist_ok=True)

# Enable CGI Trackback Manager for debugging (https://docs.python.org/fr/3/library/cgitb.html)
cgitb.enable(display=0, logdir=errdir, format='text')

def parse_url_path(path):
    m = search('^/([^/]*)/([^/]*)(?:/([^/]))?/([^/]*)(.*)$', path)

    if m:
        ctx = {
            "project": m.group(1),
            "version": m.group(2),
            "version_decoded": parse.unquote(m.group(2)),
            "family": str(m.group(3)).upper(),
            "cmd": m.group(4),
            "arg": m.group(5),
            "search_family": "A",
        }

        if not validFamily(ctx["family"]):
            ctx["family"] = 'C'

        return ctx, None
    else:
        return {}, (400, )

def get_url_from_ctx(ctx):
    url = f'/{ctx["project"]}/{parse.quote(ctx["version"])}/{ctx["family"]}/{ctx["cmd"]}/{ctx["arg"]}'
    return url.rstrip('/')


# redirects if path has a trailing slash
def handle_trailing_slash(ctx):
    if len(ctx["arg"]) > 0 and (ctx["arg"][-1] == '/' or ctx["arg"][1] == '/'):
        ctx["arg"] = ctx["arg"].rstrip('/').lstrip('/')
        return ctx, (301, get_url_from_ctx(ctx))

    return ctx, None

# TODO handle legacy source urlk
# handle source urls, check if source path is valid
def handle_source_url(ctx):
    ctx, status = handle_trailing_slash(ctx)
    if status is not None:
        return ctx, status

    if not search('^[A-Za-z0-9_/.,+-]*$', ctx["arg"]):
        return ctx, (400,)

    ctx["url"] = 'source' + ctx["arg"]
    return ctx, None


# add ident to ctx, return an error if ident is not valid
def handle_invalid_ident(ctx):
    ident = ctx["arg"][1:]
    if not ident or not search('^[A-Za-z0-9_\$\.%-]*$', ident):
        return ctx, (400,)

    ctx["ident"] = parse.unquote(ident)
    return ctx, None

# handle ident search post by redirecting to ident/$ident_name
def handle_ident_post_form(ctx):
    form = cgi.FieldStorage()
    ident2 = form.getvalue('i')
    family2 = str(form.getvalue('f')).upper()
    if not validFamily(family2):
        family2 = 'C'

    if ctx.get("ident", '') == '' and ident2:
        ident2 = parse.quote(ident2.strip())
        ctx["family"] = family2
        ctx["arg"] = ident2
        return ctx, (302, get_url_from_ctx(ctx))

    return ctx, None

# TODO handle legacy ident urls
# handle ident urls, both post and get, check if ident path is valid
def handle_ident_url(ctx):
    ctx["search_family"] = ctx["family"]

    ctx, status = handle_ident_post_form(ctx)
    if status is not None:
        return ctx, status

    ctx, status = handle_invalid_ident(ctx)
    if status is not None:
        return ctx, status

    ctx["url"] = ctx["family"] + '/ident/' + ctx["ident"]
    return ctx, None


# create query object from context, add it to context, return error if project name is invalid
def add_query_to_ctx(ctx):
    basedir = os.environ['LXR_PROJ_DIR']
    datadir = basedir + '/' + ctx["project"] + '/data'
    repodir = basedir + '/' + ctx["project"] + '/repo'

    if not(os.path.exists(datadir)) or not(os.path.exists(repodir)):
        return ctx, (400,)

    ctx["query"] = Query(datadir, repodir)
    return ctx, None

# redirect latest version to the latest tag
def handle_latest_redirect(ctx):
    if ctx["version"] == 'latest':
        q = ctx["query"]
        ctx["version_decoded"] = q.query('latest')
        ctx["version"] = parse.quote(q.query('latest'))
        return ctx, (301, get_url_from_ctx(ctx))

    return ctx, None

# parse url, create query, hanle source and ident urls
def handle_request(path):
    ctx, status = parse_url_path(path)
    if status is not None:
        return ctx, status

    ctx, status = add_query_to_ctx(ctx)
    if status is not None:
        return ctx, status

    ctx, status = handle_latest_redirect(ctx)
    if status is not None:
        return ctx, status

    if ctx["cmd"] == 'source':
        return handle_source_url(ctx)
    elif ctx["cmd"] == 'ident':
        return handle_ident_url(ctx)
    else:
        return ctx, (400,)


url = os.environ.get('REQUEST_URI') or os.environ.get('SCRIPT_URL')
ctx, status = handle_request(url)
if status is not None:
    if status[0] == 301:
        realprint('Status: 301 Moved Permanently')
        realprint('Location: '+status[1]+'\n')
        exit()
    elif status[0] == 302:
        realprint('Status: 302 Found')
        realprint('Location: '+status[1]+'\n')
        exit()
    elif status[0] == 400:
        realprint('Status: 400 Bad Request\n')
        exit()


q = ctx["query"]
basedir = os.environ['LXR_PROJ_DIR']
datadir = q.data_dir
repodir = q.repo_dir

projects = []
for (dirpath, dirnames, filenames) in os.walk(basedir):
    projects.extend(dirnames)
    break
projects.sort()

dts_comp_support = q.query('dts-comp')

tag = ctx["version_decoded"]
version = ctx["version"]
project = ctx["project"]
mode = ctx["cmd"]
path = ctx["arg"]
url = ctx["url"]
family = ctx["search_family"]
ident = ctx.get("ident", '')

data = {
    **ctx,
    'baseurl': '/' + ctx["project"] + '/',
    'tag': tag,
    'url': url,
    'projects': projects,
    'family': ctx["search_family"],
    'breadcrumb': '<a class="project" href="'+version+'/source">/</a>'
}

versions = q.query('versions')

v = ''
b = 1
for topmenu in versions:
    submenus = versions[topmenu]
    v += '<li>\n'
    v += '\t<span>'+topmenu+'</span>\n'
    v += '\t<ul>\n'
    b += 1
    for submenu in submenus:
        tags = submenus[submenu]
        if submenu == tags[0] and len(tags) == 1:
            if submenu == tag: v += '\t\t<li class="li-link active"><a href="'+submenu+'/'+url+'">'+submenu+'</a></li>\n'
            else: v += '\t\t<li class="li-link"><a href="'+submenu+'/'+url+'">'+submenu+'</a></li>\n'
        else:
            v += '\t\t<li>\n'
            v += '\t\t\t<span>'+submenu+'</span>\n'
            v += '\t\t\t<ul>\n'
            for _tag in tags:
                _tag_encoded = parse.quote(_tag, safe='')
                if _tag == tag: v += '\t\t\t\t<li class="li-link active"><a href="'+_tag_encoded+'/'+url+'">'+_tag+'</a></li>\n'
                else: v += '\t\t\t\t<li class="li-link"><a href="'+_tag_encoded+'/'+url+'">'+_tag+'</a></li>\n'
            v += '\t\t\t</ul></li>\n'
    v += '\t</ul></li>\n'

data['versions'] = v

title_suffix = project.capitalize()+' source code ('+tag+') - Bootlin'

if mode == 'source':
    path_split = path.split('/')[1:]
    path_temp = ''
    links = []
    for p in path_split:
        path_temp += '/'+p
        links.append('<a href="'+version+'/source'+path_temp+'">'+p+'</a>')

    if links:
        data['breadcrumb'] += '/'.join(links)

    data['ident'] = ident
    # Create titles like this:
    # root path: "Linux source code (v5.5.6) - Bootlin"
    # first level path: "arch - Linux source code (v5.5.6) - Bootlin"
    # deeper paths: "Makefile - arch/um/Makefile - Linux source code (v5.5.6) - Bootlin"
    data['title'] = ('' if path == ''
                     else path_split[0]+' - ' if len(path_split) == 1
                     else path_split[-1]+' - '+'/'.join(path_split)+' - ') \
            +title_suffix

    lines = ['null - - -']

    type = q.query('type', tag, path)
    if len(type) > 0:
        if type == 'tree':
            lines += q.query('dir', tag, path)
        elif type == 'blob':
            code = q.query('file', tag, path)
    else:
        print('<div class="lxrerror"><h2>This file does not exist.</h2></div>')
        status = 404

    if type == 'tree':
        if path != '':
            lines[0] = 'back - - -'

        print('<div class="lxrtree">')
        print('<table><tbody>\n')
        for l in lines:
            type, name, size, perm = l.split(' ')

            if type == 'null':
                continue
            elif type == 'tree':
                size = ''
                path2 = path+'/'+name
                name = name
            elif type == 'blob':
                size = size+' bytes'
                path2 = path+'/'+name

                if perm == '120000':
                    # 120000 permission means it's a symlink
                    # So we need to handle that correctly
                    dir_name = os.path.dirname(path)
                    rel_path = q.query('file', tag, path2)

                    if dir_name != '/':
                        dir_name += '/'

                    path2 = os.path.abspath(dir_name + rel_path)

                    name = name + ' -> ' + path2
            elif type == 'back':
                size = ''
                path2 = os.path.dirname(path[:-1])
                if path2 == '/': path2 = ''
                name = 'Parent directory'

            print('  <tr>\n')
            print('    <td><a class="tree-icon icon-'+type+'" href="'+version+'/source'+path2+'">'+name+'</a></td>\n')
            print('    <td><a tabindex="-1" class="size" href="'+version+'/source'+path2+'">'+size+'</a></td>\n')
            print('  </tr>\n')

        print('</tbody></table>', end='')
        print('</div>')

    elif type == 'blob':

        import pygments
        import pygments.lexers
        import pygments.formatters

        fdir, fname = os.path.split(path)
        filename, extension = os.path.splitext(fname)
        extension = extension[1:].lower()
        family = q.query('family', fname)

        # Source common filter definitions
        os.chdir('filters')
        exec(open("common.py").read())

        # Source project specific filters
        f = project + '.py'
        if os.path.isfile(f):
            exec(open(f).read())
        os.chdir('..')

        # Apply filters
        for f in filters:
            c = f['case']
            if (c == 'any' or
                (c == 'filename' and filename in f['match']) or
                (c == 'extension' and extension in f['match']) or
                (c == 'path' and fdir.startswith(tuple(f['match']))) or
                (c == 'filename_extension' and filename.endswith(tuple(f['match'])))):

                apply_filter = True

                if 'path_exceptions' in f:
                    for p in f['path_exceptions']:
                        if re.match(p, path):
                            apply_filter = False
                            break

                if apply_filter:
                    code = sub(f ['prerex'], f ['prefunc'], code, flags=re.MULTILINE)

        try:
            lexer = pygments.lexers.guess_lexer_for_filename(path, code)
        except:
            lexer = pygments.lexers.get_lexer_by_name('text')

        lexer.stripnl = False
        formatter = pygments.formatters.HtmlFormatter(linenos=True, anchorlinenos=True)
        result = pygments.highlight(code, lexer, formatter)

        # Replace line numbers by links to the corresponding line in the current file
        result = sub('href="#-(\d+)', 'name="L\\1" id="L\\1" href="'+version+'/source'+path+'#L\\1', result)

        for f in filters:
            c = f['case']
            if (c == 'any' or
                (c == 'filename' and filename in f['match']) or
                (c == 'extension' and extension in f['match']) or
                (c == 'path' and fdir.startswith(tuple(f['match']))) or
                (c == 'filename_extension' and filename.endswith(tuple(f['match'])))):

                result = sub(f ['postrex'], f ['postfunc'], result)

        print('<div class="lxrcode">' + result + '</div>')


elif mode == 'ident':
    data['title'] = ident+' identifier - '+title_suffix

    symbol_definitions, symbol_references, symbol_doccomments = q.query('ident', tag, ident, family)

    print('<div class="lxrident">')
    if len(symbol_definitions) or len(symbol_references):
        if len(symbol_definitions):
            previous_type = ''
            types_count = {}

            # Count occurrences of each type before printing
            for symbol_definition in symbol_definitions:
                if symbol_definition.type in types_count:
                        types_count[symbol_definition.type] += 1
                else:
                        types_count[symbol_definition.type] = 1

            for symbol_definition in symbol_definitions:
                if symbol_definition.type != previous_type:
                    if previous_type != '':
                        print('</ul>')
                    print('<h2>Defined in '+str(types_count[symbol_definition.type])+' files as a '+symbol_definition.type+':</h2>')
                    print('<ul>')
                    previous_type = symbol_definition.type

                ln = str(symbol_definition.line).split(',')
                if len(ln) == 1:
                    n = ln[0]
                    print('<li><a href="{v}/source/{f}#L{n}"><strong>{f}</strong>, line {n} <em>(as a {t})</em></a>'.format(
                        v=version, f=symbol_definition.path, n=n, t=symbol_definition.type
                    ))
                else:
                    if len(symbol_definitions) > 100:    # Concise display
                        n = len(ln)
                        print('<li><a href="{v}/source/{f}#L{l}"><strong>{f}</strong>, <em>{n} times</em> <em>(as a {t})</em></a>'.format(
                            v=version, f=symbol_definition.path, n=n, t=symbol_definition.type, l=ln[0]
                        ))
                    else:    # Verbose display
                        print('<li><a href="{v}/source/{f}#L{n}"><strong>{f}</strong> <em>(as a {t})</em></a>'.format(
                            v=version, f=symbol_definition.path, n=ln[0], t=symbol_definition.type
                        ))
                        print('<ul>')
                        for n in ln:
                            print('<li><a href="{v}/source/{f}#L{n}">line {n}</a>'.format(
                                v=version, f=symbol_definition.path, n=n
                            ))
                        print('</ul>')
            print('</ul>')
        else:
            print('<h2>No definitions found in the database</h2>')

        if len(symbol_doccomments):
            print('<h2>Documented in '+str(len(symbol_doccomments))+' files:</h2>')
            print('<ul>')
            for symbol_doccomment in symbol_doccomments:
                ln = symbol_doccomment.line.split(',')
                if len(ln) == 1:
                    n = ln[0]
                    print('<li><a href="{v}/source/{f}#L{n}"><strong>{f}</strong>, line {n}</a>'.format(
                        v=version, f=symbol_doccomment.path, n=n
                    ))
                else:
                    if len(symbol_doccomments) > 100:    # Concise display
                        n = len(ln)
                        print('<li><a href="{v}/source/{f}#L{l}"><strong>{f}</strong>, <em>{n} times</em></a>'.format(
                            v=version, f=symbol_doccomment.path, n=n, l=ln[0]
                        ))
                    else:    # Verbose display
                        print('<li><a href="{v}/source/{f}#L{n}"><strong>{f}</strong></a>'.format(
                            v=version, f=symbol_doccomment.path, n=ln[0]
                        ))
                        print('<ul>')
                        for n in ln:
                            print('<li><a href="{v}/source/{f}#L{n}">line {n}</a>'.format(
                                v=version, f=symbol_doccomment.path, n=n
                            ))
                        print('</ul>')
            print('</ul>')

        if len(symbol_references):
            print('<h2>Referenced in '+str(len(symbol_references))+' files:</h2>')
            print('<ul>')
            for symbol_reference in symbol_references:
                ln = symbol_reference.line.split(',')
                if len(ln) == 1:
                    n = ln[0]
                    print('<li><a href="{v}/source/{f}#L{n}"><strong>{f}</strong>, line {n}</a>'.format(
                        v=version, f=symbol_reference.path, n=n
                    ))
                else:
                    if len(symbol_references) > 100:    # Concise display
                        n = len(ln)
                        print('<li><a href="{v}/source/{f}#L{l}"><strong>{f}</strong>, <em>{n} times</em></a>'.format(
                            v=version, f=symbol_reference.path, n=n, l=ln[0]
                        ))
                    else:    # Verbose display
                        print('<li><a href="{v}/source/{f}#L{n}"><strong>{f}</strong></a>'.format(
                            v=version, f=symbol_reference.path, n=ln[0]
                        ))
                        print('<ul>')
                        for n in ln:
                            print('<li><a href="{v}/source/{f}#L{n}">line {n}</a>'.format(
                                v=version, f=symbol_reference.path, n=n
                            ))
                        print('</ul>')
            print('</ul>')
        else:
            print('<h2>No references found in the database</h2>')
    else:
        if ident != '':
            print('<h2>Identifier not used</h2>')
            status = 404
    print('</div>')

else:
    print('Invalid request')

if status == 404:
    realprint('Status: 404 Not Found')

import jinja2
loader = jinja2.FileSystemLoader(os.path.join(os.path.dirname(os.path.realpath(__file__)), '../templates/'))
environment = jinja2.Environment(loader=loader)
template = environment.get_template('layout.html')

realprint('Content-Type: text/html;charset=utf-8\n')
data['main'] = outputBuffer.getvalue()
realprint(template.render(data), end='')
