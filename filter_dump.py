import re
import sys
from elixir.lexers import dts_identifier

def file_allowed_hash_comments(filename, file_line, keyword):
    if filename.lower().endswith(('.s', 'makefile', 'kconfig')) or filename.lower().startswith(('makefile', 'kconfig')):
        return not (re.match(r'\s*#\s*', file_line) and not re.match(r'\s*#\s*(define|undef|if|ifdef|ifndef|elif|elifdef|elifndef)', file_line))

    return True

def file_allowed_full_strings(filename, file_line, keyword):
    if file_line.count('"') == 2 and re.match(r'\s*".*?"\s*', file_line):
        return False

    if file_line.count('"') == 2 and re.match(r"\s*'.*?'\s*", file_line):
        return False

    return True

def file_allowed_comments(filename, file_line, keyword):
    if re.match(r'\s*/\*', file_line):
        return False

    # high probability that this is the middle of a multiline comment
    if re.match(r'\s*\* \s*[a-zA-Z0-9 \']*', file_line):
        return False

    return True

def file_allowed_preproc(filename, file_line, keyword):
    return not re.match(r'\s*#\s*(error|warning|include)', file_line)

def file_allowed_strings(filename, file_line, keyword):
    k_count = file_line.count(keyword)
    dstring = re.findall(r'".*?"', file_line)
    sstring = re.findall(r"'.*?'", file_line)
    count = 0
    if dstring is not None:
        for match in dstring:
            count += match.count(keyword)

    if sstring is not None:
        for match in sstring:
            count += match.count(keyword)

    #if len(dstring) + len(sstring) != 0:
    #    print("debug", keyword, k_count, count, dstring, sstring)
    return k_count == count

def file_allowed_dts_id_commas(filename, file_line, keyword):
    if filename.lower().endswith(('dts', 'dtsi')):
        ident = file_line.strip().split(' ')[0]
        return not (re.match(dts_identifier, ident) and ',' in ident)
    else:
        return True

def file_allowed_short_keywords(filename, file_line, keyword):
    return len(keyword) > 2

filters = [
    file_allowed_hash_comments,
    file_allowed_dts_id_commas,
    file_allowed_strings,
    file_allowed_full_strings,
    file_allowed_comments,
    file_allowed_preproc,
    file_allowed_short_keywords,
]

def file_allowed(filename, file_line, keyword):
    for f in filters:
        if not f(filename, file_line, keyword):
            return False
    return True

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(f"usage: {sys.argv[0]} dump_path")
        exit(1)

    with open(sys.argv[1]) as f:
        for line in f.readlines():
            if len(line) == 0:
                print()
                continue
            elif re.match(r'^[0-9a-f,-]+\s*$', line):
                continue

            prefix = ''
            if line.startswith(('< ', '> ')):
                prefix = line[:1]
                line = line[2:]

            line_split = line.split(" ")
            if len(line_split) == 1:
                continue

            filename = line_split[0]
            keyword = line_split[1]
            line_number = line_split[2]
            line_contents = " ".join(line_split[3:])

            if not filename.lower().endswith(('.c','.h')):
                continue

            if file_allowed(filename, line_contents, keyword):
                print(prefix, filename, keyword, line_number, line_contents[:-1])
            #else:
            #    print("DELETED ", prefix, filename, line_number, keyword, line_contents[:-1])


