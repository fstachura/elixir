import unittest
from .lexers import DTSLexer, KconfigLexer, CLexer, GasLexer

class LexerTest(unittest.TestCase):
    default_filtered_tokens = ("SPECIAL", "COMMENT", "STRING", "IDENTIFIER", "SPECIAL", "ERROR")

    # Checks if each token starts in the claimed position of code, if tokens cover all code and if no tokens overlap
    def verify_positions(self, code, tokens):
        last_token = None
        for t in tokens:
            if code[t.span[0]:t.span[1]] != t.token:
                self.fail(f"token {t} span != code span {code[t.span[0]:t.span[1]].encode()}")

            if last_token is not None and last_token.span[1] != t.span[0]:
                self.fail(f"token does not start where the previous token ends. prev: {last_token}, next: {t}")
            elif last_token is None and t.span[0] != 0:
                self.fail(f"first token does not start at zero: {t}")

            last_token = t

        if last_token.span[1] != len(code):
            self.fail(f"code is longer than position of the last token: {t}, code len: {len(code)}")

    # Checks if each token is in the claimed line of code
    def verify_lines(self, code, tokens):
        lines = [""] + code.split("\n") # zero line is emtpy
        last_line_number = None
        last_line_contents_left = None
        for t in tokens:
            if last_line_number != t.line:
                last_line_number = t.line
                last_line_contents_left = lines[t.line]

            if last_line_contents_left is None:
                self.fail(f"nothing left in line {t.line} for {t.token} {t}")

            newline_count = t.token.count("\n")
            all_token_lines = last_line_contents_left + "\n" + \
                    "\n".join([lines[i] for i in range(t.line+1, t.line+newline_count+1)]) + "\n"
            token_pos_in_lines = all_token_lines.find(t.token)
            if token_pos_in_lines == -1:
                self.fail(f"token {t.token} not found in line {t.line}: {all_token_lines.encode()}")
            if token_pos_in_lines < len(last_line_contents_left):
                last_line_contents_left = last_line_contents_left[token_pos_in_lines:]
            else:
                last_line_contents_left = None

    # Lex code, do basic soundness checks on tokens (lines and positions) and compare lexing results with a list of tokens
    def lex(self, code, expected, filtered_tokens=None, lexer_options={}):
        if filtered_tokens is None:
            filtered_tokens = self.default_filtered_tokens

        code = code.lstrip()
        tokens = list(self.lexer_cls(code, **lexer_options).lex())
        self.verify_positions(code, tokens)
        self.verify_lines(code, tokens)

        tokens = [[type.name, token] for type, token, span, line in tokens]
        tokens = [t for t in tokens if t[0] in filtered_tokens]
        try:
            self.assertEqual(tokens, expected)
        except Exception as e:
            print()
            for t in tokens: print(t, end=",\n")
            raise e

class DTSLexerTests(LexerTest):
    lexer_cls = DTSLexer
    default_filtered_tokens = ("SPECIAL", "COMMENT", "STRING", "IDENTIFIER", "SPECIAL", "ERROR")

    def test_preproc(self):
        self.lex(r"""
#include <file.dtsi>
#include "file2.dtsi"
#error error message asldjlksajdlksad
#warning   warning message alsjdlkasjdlksajd
#define MACRO(arg) \
        arg = <3>;
#if 0
/ {
    property = <2>;
    MACRO(test)
};
#endif
""", [
        ['SPECIAL', '#include <file.dtsi>'],
        ['SPECIAL', '#include "file2.dtsi"'],
        ['SPECIAL', '#error error message asldjlksajdlksad\n'],
        ['SPECIAL', '#warning   warning message alsjdlkasjdlksajd\n'],
        ['SPECIAL', '#define'],
        ['IDENTIFIER', 'MACRO'],
        ['IDENTIFIER', 'arg'],
        ['IDENTIFIER', 'arg'],
        ['SPECIAL', '#if'],
        ['IDENTIFIER', 'property'],
        ['IDENTIFIER', 'MACRO'],
        ['IDENTIFIER', 'test'],
        ['SPECIAL', '#endif'],
    ])

    def test_dts_directives(self):
        self.lex(r"""
/include/ "file.dtsi"
/dts-v1/;
/memreserve/ 0x100 0x2;
/ {
    test_label: test-node {
        test-prop2 = <3>;
    };
    test-prop = <2>;
    /delete-node/ test-node;
    /delete-node/ &test_label;
    /delete-property/ test-prop;
};
""", [
        ['SPECIAL', '/include/'],
        ['STRING', '"file.dtsi"'],
        ['SPECIAL', '/dts-v1/'],
        ['SPECIAL', '/memreserve/'],
        ['IDENTIFIER', 'test_label'],
        ['IDENTIFIER', 'test-node'],
        ['IDENTIFIER', 'test-prop2'],
        ['IDENTIFIER', 'test-prop'],
        ['SPECIAL', '/delete-node/'],
        ['IDENTIFIER', 'test-node'],
        ['SPECIAL', '/delete-node/'],
        ['IDENTIFIER', 'test_label'],
        ['SPECIAL', '/delete-property/'],
        ['IDENTIFIER', 'test-prop'],
    ])

    def test_dts_unusual_identifiers(self):
        self.lex(r"""
/ {
    _test_label:        5id,test._+asd-2           {
        property,name = <2>;
        0p,r.o_p+e?r#t-y,name = [1,2,3];
        way_too_long_label_123219380921830218309218309213    :  node@234 {
            compatible = "asd,zxc";
        }
        test  =   <&way_too_long_label_123219380921830218309218309213>;
    };
};
""", [
        ['IDENTIFIER', '_test_label'],
        ['IDENTIFIER', 'id,test._+asd-2'],
        ['IDENTIFIER', 'property,name'],
        ['IDENTIFIER', 'p,r.o_p+e?r#t-y,name'],
        ['IDENTIFIER', 'way_too_long_label_123219380921830218309218309213'],
        ['IDENTIFIER', 'node'],
        ['IDENTIFIER', '234'],
        ['IDENTIFIER', 'compatible'],
        ['STRING', '"asd,zxc"'],
        ['IDENTIFIER', 'test'],
        ['IDENTIFIER', 'way_too_long_label_123219380921830218309218309213'],
    ])

    def test_non_numeric_unit_address(self):
        self.lex(r"""
/ {
    test: node@test_address {
    };
    test2: node@MACRO_ADDRESS(123) {
    };
};
""", [
        ['IDENTIFIER', 'test'],
        ['IDENTIFIER', 'node'],
        ['IDENTIFIER', 'test_address'],
        ['IDENTIFIER', 'test2'],
        ['IDENTIFIER', 'node'],
        ['IDENTIFIER', 'MACRO_ADDRESS'],
    ])

    def test_values_with_labels(self):
        self.lex(r"""
/ {
    prop1 = label1: <0 label2: 0x21323>;
    prop2 = [1 2 3 label3: 4];
    prop3 = label4: "val" label5: ;
};
""", [
        ['PUNCTUATION', '/'],
        ['PUNCTUATION', '{'],
        ['IDENTIFIER', 'prop1'],
        ['PUNCTUATION', '='],
        ['IDENTIFIER', 'label1'],
        ['PUNCTUATION', ':'],
        ['PUNCTUATION', '<'],
        ['NUMBER', '0'],
        ['IDENTIFIER', 'label2'],
        ['PUNCTUATION', ':'],
        ['NUMBER', '0x21323'],
        ['PUNCTUATION', '>'],
        ['PUNCTUATION', ';'],
        ['IDENTIFIER', 'prop2'],
        ['PUNCTUATION', '='],
        ['PUNCTUATION', '['],
        ['NUMBER', '1'],
        ['NUMBER', '2'],
        ['NUMBER', '3'],
        ['IDENTIFIER', 'label3'],
        ['PUNCTUATION', ':'],
        ['NUMBER', '4'],
        ['PUNCTUATION', ']'],
        ['PUNCTUATION', ';'],
        ['IDENTIFIER', 'prop3'],
        ['PUNCTUATION', '='],
        ['IDENTIFIER', 'label4'],
        ['PUNCTUATION', ':'],
        ['STRING', '"val"'],
        ['IDENTIFIER', 'label5'],
        ['PUNCTUATION', ':'],
        ['PUNCTUATION', ';'],
        ['PUNCTUATION', '}'],
        ['PUNCTUATION', ';'],
    ], self.default_filtered_tokens + ('PUNCTUATION', 'NUMBER'))

    def test_references(self):
        self.lex(r"""
/ {
    interrupt-parent = < &{/node@c2342/another_node@address(2)/node3} >;
    property2 = <&{/node@c2342/another_node@address(2)}>;
    power-domains = <&power DEVICE_DOMAIN>;
};
""", [
        ['IDENTIFIER', 'interrupt-parent'],
        ['IDENTIFIER', 'node'],
        ['IDENTIFIER', 'c2342'],
        ['IDENTIFIER', 'another_node'],
        ['IDENTIFIER', 'address'],
        ['IDENTIFIER', 'node3'],
        ['IDENTIFIER', 'property2'],
        ['IDENTIFIER', 'node'],
        ['IDENTIFIER', 'c2342'],
        ['IDENTIFIER', 'another_node'],
        ['IDENTIFIER', 'address'],
        ['IDENTIFIER', 'power-domains'],
        ['IDENTIFIER', 'power'],
        ['IDENTIFIER', 'DEVICE_DOMAIN'],
    ])

    def test_property_types(self):
        self.lex(r"""
/ {
    prop1 = <0 0x21323>;
    prop2 = [1 2 3 4];
    prop3 = "val", "val4" ;
    prop4 = <~1+2-3*4/5%6&7|8^9<<10>>11>;
    prop5;
};
""", [
        ['PUNCTUATION', '/'],
        ['PUNCTUATION', '{'],
        ['IDENTIFIER', 'prop1'],
        ['PUNCTUATION', '='],
        ['PUNCTUATION', '<'],
        ['NUMBER', '0'],
        ['NUMBER', '0x21323'],
        ['PUNCTUATION', '>'],
        ['PUNCTUATION', ';'],
        ['IDENTIFIER', 'prop2'],
        ['PUNCTUATION', '='],
        ['PUNCTUATION', '['],
        ['NUMBER', '1'],
        ['NUMBER', '2'],
        ['NUMBER', '3'],
        ['NUMBER', '4'],
        ['PUNCTUATION', ']'],
        ['PUNCTUATION', ';'],
        ['IDENTIFIER', 'prop3'],
        ['PUNCTUATION', '='],
        ['STRING', '"val"'],
        ['PUNCTUATION', ','],
        ['STRING', '"val4"'],
        ['PUNCTUATION', ';'],
        ['IDENTIFIER', 'prop4'],
        ['PUNCTUATION', '='],
        ['PUNCTUATION', '<'],
        ['PUNCTUATION', '~'],
        ['NUMBER', '1'],
        ['PUNCTUATION', '+'],
        ['NUMBER', '2'],
        ['PUNCTUATION', '-'],
        ['NUMBER', '3'],
        ['PUNCTUATION', '*'],
        ['NUMBER', '4'],
        ['PUNCTUATION', '/'],
        ['NUMBER', '5'],
        ['PUNCTUATION', '%'],
        ['NUMBER', '6'],
        ['PUNCTUATION', '&'],
        ['NUMBER', '7'],
        ['PUNCTUATION', '|'],
        ['NUMBER', '8'],
        ['PUNCTUATION', '^'],
        ['NUMBER', '9'],
        ['PUNCTUATION', '<'],
        ['PUNCTUATION', '<'],
        ['NUMBER', '10'],
        ['PUNCTUATION', '>'],
        ['PUNCTUATION', '>'],
        ['NUMBER', '11'],
        ['PUNCTUATION', '>'],
        ['PUNCTUATION', ';'],
        ['IDENTIFIER', 'prop5'],
        ['PUNCTUATION', ';'],
        ['PUNCTUATION', '}'],
        ['PUNCTUATION', ';'],
    ], self.default_filtered_tokens + ('PUNCTUATION', 'NUMBER'))

    def test_comments(self):
        self.lex(r"""
//license info
/ {
    interrupts = <NAME 100 TYPE>, /* comment 1 */
        <NAME 101 TYPE>; // comemnt2
    /* long
    * coment
    * asdasd
    */
};
""", [
        ['COMMENT', '//license info\n'],
        ['IDENTIFIER', 'interrupts'],
        ['IDENTIFIER', 'NAME'],
        ['IDENTIFIER', 'TYPE'],
        ['COMMENT', '/* comment 1 */'],
        ['IDENTIFIER', 'NAME'],
        ['IDENTIFIER', 'TYPE'],
        ['COMMENT', '// comemnt2\n'],
        ['COMMENT', '/* long\n    * coment\n    * asdasd\n    */'],
    ], self.default_filtered_tokens)


class KconfigLexerTest(LexerTest):
    lexer_cls = KconfigLexer
    default_filtered_tokens = ("SPECIAL", "COMMENT", "STRING", "IDENTIFIER", "SPECIAL", "ERROR")

    # TODO improve macro calls

    def test_comments(self):
        self.lex(r"""
# comment1
config 64BIT # comment2
    bool # comment3
    default "# asd"
    default $(shell, \#)
    help
        asdasdsajdlakjd # not a comment

        asdasdsajdlakjd # not a comment

        # comment 5

    # comment 6
""", [
            ['COMMENT', '# comment1\n'],
            ['SPECIAL', 'config'],
            ['IDENTIFIER', '64BIT'],
            ['COMMENT', '# comment2\n'],
            ['SPECIAL', 'bool'],
            ['COMMENT', '# comment3\n'],
            ['SPECIAL', 'default'],
            ['STRING', '"# asd"'],
            ['SPECIAL', 'default'],
            ['SPECIAL', 'shell'],
            ['SPECIAL', '\\#)'],
            ['SPECIAL', 'help'],
            ['COMMENT', '        asdasdsajdlakjd # not a comment\n\n        asdasdsajdlakjd # not a comment\n\n        # comment 5\n\n'],
            ['COMMENT', '# comment 6\n'],
        ])


    def test_keywords(self):
        self.lex(r""",
menu "menu name"

visible if y

choice
    prompt "test prompt"
    default y

config 86CONIFG
    bool "text"
    prompt "prompt"
    default y
    tristate "test"
    def_bool TEST_bool
    depends on TEST
    select TEST2
    imply TEST3
    range 5 512 if CONFIG_512
    help
        help text

        more help text

endmenu
""", [
        ['SPECIAL', 'menu'],
        ['STRING', '"menu name"'],
        ['SPECIAL', 'visible'],
        ['SPECIAL', 'if'],
        ['SPECIAL', 'y'],
        ['SPECIAL', 'choice'],
        ['SPECIAL', 'prompt'],
        ['STRING', '"test prompt"'],
        ['SPECIAL', 'default'],
        ['SPECIAL', 'y'],
        ['SPECIAL', 'config'],
        ['IDENTIFIER', '86CONIFG'],
        ['SPECIAL', 'bool'],
        ['STRING', '"text"'],
        ['SPECIAL', 'prompt'],
        ['STRING', '"prompt"'],
        ['SPECIAL', 'default'],
        ['SPECIAL', 'y'],
        ['SPECIAL', 'tristate'],
        ['STRING', '"test"'],
        ['SPECIAL', 'def_bool'],
        ['IDENTIFIER', 'TEST_bool'],
        ['SPECIAL', 'depends'],
        ['SPECIAL', 'on'],
        ['IDENTIFIER', 'TEST'],
        ['SPECIAL', 'select'],
        ['IDENTIFIER', 'TEST2'],
        ['SPECIAL', 'imply'],
        ['IDENTIFIER', 'TEST3'],
        ['SPECIAL', 'range'],
        ['SPECIAL', 'if'],
        ['IDENTIFIER', 'CONFIG_512'],
        ['SPECIAL', 'help'],
        ['COMMENT', '        help text\n\n        more help text\n\n'],
        ['SPECIAL', 'endmenu'],
    ])

    def test_conditions(self):
        self.lex(r"""
config TEST
    select TEST1 if TEST2 = TEST3
    select TEST2 if TEST5 != TEST6
    select TEST7 if TEST8 < TEST9
    select TEST10 if TEST11 > TEST12
    select TEST13 if TEST14 <=  TEST15
""", [
        ['SPECIAL', 'config'],
        ['IDENTIFIER', 'TEST'],
        ['SPECIAL', 'select'],
        ['IDENTIFIER', 'TEST1'],
        ['SPECIAL', 'if'],
        ['IDENTIFIER', 'TEST2'],
        ['PUNCTUATION', '='],
        ['IDENTIFIER', 'TEST3'],
        ['SPECIAL', 'select'],
        ['IDENTIFIER', 'TEST2'],
        ['SPECIAL', 'if'],
        ['IDENTIFIER', 'TEST5'],
        ['PUNCTUATION', '!'],
        ['PUNCTUATION', '='],
        ['IDENTIFIER', 'TEST6'],
        ['SPECIAL', 'select'],
        ['IDENTIFIER', 'TEST7'],
        ['SPECIAL', 'if'],
        ['IDENTIFIER', 'TEST8'],
        ['PUNCTUATION', '<'],
        ['IDENTIFIER', 'TEST9'],
        ['SPECIAL', 'select'],
        ['IDENTIFIER', 'TEST10'],
        ['SPECIAL', 'if'],
        ['IDENTIFIER', 'TEST11'],
        ['PUNCTUATION', '>'],
        ['IDENTIFIER', 'TEST12'],
        ['SPECIAL', 'select'],
        ['IDENTIFIER', 'TEST13'],
        ['SPECIAL', 'if'],
        ['IDENTIFIER', 'TEST14'],
        ['PUNCTUATION', '<'],
        ['PUNCTUATION', '='],
        ['IDENTIFIER', 'TEST15'],
    ], self.default_filtered_tokens + ("PUNCTUATION",))

    def test_conditions2(self):
        self.lex(r"""
config TEST
    select TEST16    if TEST17   >= TEST3
    select TEST17 if (TEST18 = TEST19)

    select TEST20 if !(TEST21 = TEST22)
    select TEST23 if TEST24 && TEST25
    select TEST26 if TEST27 || TEST28
""", [
        ['SPECIAL', 'config'],
        ['IDENTIFIER', 'TEST'],
        ['SPECIAL', 'select'],
        ['IDENTIFIER', 'TEST16'],
        ['SPECIAL', 'if'],
        ['IDENTIFIER', 'TEST17'],
        ['PUNCTUATION', '>'],
        ['PUNCTUATION', '='],
        ['IDENTIFIER', 'TEST3'],
        ['SPECIAL', 'select'],
        ['IDENTIFIER', 'TEST17'],
        ['SPECIAL', 'if'],
        ['PUNCTUATION', '('],
        ['IDENTIFIER', 'TEST18'],
        ['PUNCTUATION', '='],
        ['IDENTIFIER', 'TEST19'],
        ['PUNCTUATION', ')'],
        ['SPECIAL', 'select'],
        ['IDENTIFIER', 'TEST20'],
        ['SPECIAL', 'if'],
        ['PUNCTUATION', '!'],
        ['PUNCTUATION', '('],
        ['IDENTIFIER', 'TEST21'],
        ['PUNCTUATION', '='],
        ['IDENTIFIER', 'TEST22'],
        ['PUNCTUATION', ')'],
        ['SPECIAL', 'select'],
        ['IDENTIFIER', 'TEST23'],
        ['SPECIAL', 'if'],
        ['IDENTIFIER', 'TEST24'],
        ['PUNCTUATION', '&'],
        ['PUNCTUATION', '&'],
        ['IDENTIFIER', 'TEST25'],
        ['SPECIAL', 'select'],
        ['IDENTIFIER', 'TEST26'],
        ['SPECIAL', 'if'],
        ['IDENTIFIER', 'TEST27'],
        ['PUNCTUATION', '|'],
        ['PUNCTUATION', '|'],
        ['IDENTIFIER', 'TEST28'],
    ], self.default_filtered_tokens + ("PUNCTUATION",))

    def test_macros(self):
        self.lex(r"""
config TEST
    depends on $(shell,cat file | grep -vi "option 2")
    depends on $(info,info to print)
    depends on $(warning-if,a != b,warning to print)
""", [
        ['SPECIAL', 'config'],
        ['IDENTIFIER', 'TEST'],
        ['SPECIAL', 'depends'],
        ['SPECIAL', 'on'],
        ['PUNCTUATION', '$'],
        ['PUNCTUATION', '('],
        ['SPECIAL', 'shell'],
        ['PUNCTUATION', ','],
        ['SPECIAL', 'cat'],
        ['SPECIAL', 'file'],
        ['PUNCTUATION', '|'],
        ['SPECIAL', 'grep'],
        ['PUNCTUATION', '-'],
        ['SPECIAL', 'vi'],
        ['STRING', '"option 2"'],
        ['PUNCTUATION', ')'],
        ['SPECIAL', 'depends'],
        ['SPECIAL', 'on'],
        ['PUNCTUATION', '$'],
        ['PUNCTUATION', '('],
        ['SPECIAL', 'info'],
        ['PUNCTUATION', ','],
        ['SPECIAL', 'info'],
        ['SPECIAL', 'to'],
        ['SPECIAL', 'print'],
        ['PUNCTUATION', ')'],
        ['SPECIAL', 'depends'],
        ['SPECIAL', 'on'],
        ['PUNCTUATION', '$'],
        ['PUNCTUATION', '('],
        ['SPECIAL', 'warning-if'],
        ['PUNCTUATION', ','],
        ['SPECIAL', 'a'],
        ['PUNCTUATION', '!'],
        ['PUNCTUATION', '='],
        ['SPECIAL', 'b'],
        ['PUNCTUATION', ','],
        ['SPECIAL', 'warning'],
        ['SPECIAL', 'to'],
        ['SPECIAL', 'print'],
        ['PUNCTUATION', ')'],
    ], self.default_filtered_tokens + ("PUNCTUATION",))

def test_macros2(self):
    self.lex(r"""
config TEST
    depends on $(error-if,a != b,warning to print)
    depends on $(filename)
    depends on $(lineno)
""", [
        ['SPECIAL', 'config'],
        ['IDENTIFIER', 'TEST'],
        ['SPECIAL', 'depends'],
        ['SPECIAL', 'on'],
        ['PUNCTUATION', '$'],
        ['PUNCTUATION', '('],
        ['SPECIAL', 'error-if'],
        ['PUNCTUATION', ','],
        ['SPECIAL', 'a'],
        ['PUNCTUATION', '!'],
        ['PUNCTUATION', '='],
        ['SPECIAL', 'b'],
        ['PUNCTUATION', ','],
        ['SPECIAL', 'warning'],
        ['SPECIAL', 'to'],
        ['SPECIAL', 'print'],
        ['PUNCTUATION', ')'],
        ['SPECIAL', 'depends'],
        ['SPECIAL', 'on'],
        ['PUNCTUATION', '$'],
        ['PUNCTUATION', '('],
        ['SPECIAL', 'filename'],
        ['PUNCTUATION', ')'],
        ['SPECIAL', 'depends'],
        ['SPECIAL', 'on'],
        ['PUNCTUATION', '$'],
        ['PUNCTUATION', '('],
        ['SPECIAL', 'lineno'],
        ['PUNCTUATION', ')'],
    ], self.default_filtered_tokens + ("PUNCTUATION",))

    def test_help(self):
        self.lex(r"""
config
    help
     help test lasdlkajdk sadlksajd
     lsajdlad

     salkdjaldlksajd

     "
     asdlkajsdlkjsadlajdsk

     salkdjlsakdj'
config
    select TEST
config
    ---help---
     help test lasdlkajdk sadlksajd
     lsajdlad

     salkdjaldlksajd
        
config
    select TEST
""", [
        ['SPECIAL', 'config'],
        ['SPECIAL', 'help'],
        ['COMMENT', '     help test lasdlkajdk sadlksajd\n     lsajdlad\n\n     salkdjaldlksajd\n\n     "\n     asdlkajsdlkjsadlajdsk\n\n     salkdjlsakdj\'\n'],
        ['SPECIAL', 'config'],
        ['SPECIAL', 'select'],
        ['IDENTIFIER', 'TEST'],
        ['SPECIAL', 'config'],
        ['SPECIAL', '---help---'],
        ['COMMENT', '     help test lasdlkajdk sadlksajd\n     lsajdlad\n\n     salkdjaldlksajd\n        \n'],
        ['SPECIAL', 'config'],
        ['SPECIAL', 'select'],
        ['IDENTIFIER', 'TEST'],
    ])

    def test_types(self):
        self.lex(r"""
config
    bool
    default y

config
    tristate
    default m

config
    hex
	default 0xdfffffff00000000

config
    string
    default "string \" test # \# zxc"

config
    int
    default 21312323
""", [
        ['SPECIAL', 'config'],
        ['SPECIAL', 'bool'],
        ['SPECIAL', 'default'],
        ['SPECIAL', 'y'],
        ['SPECIAL', 'config'],
        ['SPECIAL', 'tristate'],
        ['SPECIAL', 'default'],
        ['SPECIAL', 'm'],
        ['SPECIAL', 'config'],
        ['SPECIAL', 'hex'],
        ['SPECIAL', 'default'],
        ['IDENTIFIER', '0xdfffffff00000000'],
        ['SPECIAL', 'config'],
        ['SPECIAL', 'string'],
        ['SPECIAL', 'default'],
        ['STRING', '"string \\" test # \\# zxc"'],
        ['SPECIAL', 'config'],
        ['SPECIAL', 'int'],
        ['SPECIAL', 'default'],
    ])

class CLexerTest(LexerTest):
    lexer_cls = CLexer
    default_filtered_tokens = ("SPECIAL", "COMMENT", "STRING", "IDENTIFIER", "SPECIAL", "ERROR")

    def test_if0(self):
        self.lex(r"""
#if 0
static bool test_v3_0_test(void *h,
                    enum type_enum e) {
    return false;
}
#endif
static bool test_v3_0_test(void *h,
                    enum type_enum e) {
    return false;
}
""", [
        ['SPECIAL', '#if'],
        ['NUMBER', '0'],
        ['IDENTIFIER', 'static'],
        ['IDENTIFIER', 'bool'],
        ['IDENTIFIER', 'test_v3_0_test'],
        ['IDENTIFIER', 'void'],
        ['IDENTIFIER', 'h'],
        ['IDENTIFIER', 'enum'],
        ['IDENTIFIER', 'type_enum'],
        ['IDENTIFIER', 'e'],
        ['IDENTIFIER', 'return'],
        ['IDENTIFIER', 'false'],
        ['SPECIAL', '#endif'],
        ['IDENTIFIER', 'static'],
        ['IDENTIFIER', 'bool'],
        ['IDENTIFIER', 'test_v3_0_test'],
        ['IDENTIFIER', 'void'],
        ['IDENTIFIER', 'h'],
        ['IDENTIFIER', 'enum'],
        ['IDENTIFIER', 'type_enum'],
        ['IDENTIFIER', 'e'],
        ['IDENTIFIER', 'return'],
        ['IDENTIFIER', 'false'],
    ], self.default_filtered_tokens + ("NUMBER",))

    def test_preproc(self):
        self.lex(r"""
#include <stdio.h>
#   include <stdio.h>
# include "test.h"
#   include "test.h"

# warning war
#       error err
    #       error err
    #warning war

#error "escaped\
        message"

#warning "escaped\  
        message"

#  if defined(TEST)
#   elif defined(TEST2)
#else
""", [
        ['SPECIAL', '#include <stdio.h>'],
        ['SPECIAL', '#   include <stdio.h>'],
        ['SPECIAL', '# include "test.h"'],
        ['SPECIAL', '#   include "test.h"'],
        ['SPECIAL', '# warning war\n'],
        ['SPECIAL', '#       error err\n'],
        ['SPECIAL', '#       error err\n'],
        ['SPECIAL', '#warning war\n'],
        ['SPECIAL', '#error "escaped\\\n        message"\n'],
        ['SPECIAL', '#warning "escaped\\  \n        message"\n'],
        ['SPECIAL', '#  if'],
        ['IDENTIFIER', 'defined'],
        ['IDENTIFIER', 'TEST'],
        ['SPECIAL', '#   elif'],
        ['IDENTIFIER', 'defined'],
        ['IDENTIFIER', 'TEST2'],
        ['SPECIAL', '#else'],
    ])

    def test_defines(self):
        self.lex("""
# define test "long string \
    escaped newline"

    #define     test define1
#       define     test2 define12323

#define func(name, arg1,arg2...) \
    void name##f() { \
        return arg1 + arg2;
    }
""", [
        ['SPECIAL', '# define'],
        ['IDENTIFIER', 'test'],
        ['STRING', '"long string     escaped newline"'],
        ['SPECIAL', '#define'],
        ['IDENTIFIER', 'test'],
        ['IDENTIFIER', 'define1'],
        ['SPECIAL', '#       define'],
        ['IDENTIFIER', 'test2'],
        ['IDENTIFIER', 'define12323'],
        ['SPECIAL', '#define'],
        ['IDENTIFIER', 'func'],
        ['IDENTIFIER', 'name'],
        ['IDENTIFIER', 'arg1'],
        ['IDENTIFIER', 'arg2'],
        ['IDENTIFIER', 'void'],
        ['IDENTIFIER', 'name'],
        ['IDENTIFIER', 'f'],
        ['IDENTIFIER', 'return'],
        ['IDENTIFIER', 'arg1'],
        ['IDENTIFIER', 'arg2'],
    ])

    def test_strings(self):
        self.lex(r"""
"asdsad \   
    asdasd";
'asdsad \
    asdasd';
u8"test string";
u"test string";
u"test string";
L"test string";
"test \" string";
"test ' string";
"test \' string";
"test \n string";
"\xff";
"test" "string";
"test""string";
"test"
""", [
        ['STRING', '"asdsad \\   \n    asdasd"'],
        ['STRING', "'asdsad \\\n    asdasd'"],
        ['IDENTIFIER', 'u8'],
        ['STRING', '"test string"'],
        ['IDENTIFIER', 'u'],
        ['STRING', '"test string"'],
        ['IDENTIFIER', 'u'],
        ['STRING', '"test string"'],
        ['IDENTIFIER', 'L'],
        ['STRING', '"test string"'],
        ['STRING', '"test \\" string"'],
        ['STRING', '"test \' string"'],
        ['STRING', '"test \\\' string"'],
        ['STRING', '"test \\n string"'],
        ['STRING', '"\\xff"'],
        ['STRING', '"test"'],
        ['STRING', '"string"'],
        ['STRING', '"test"'],
        ['STRING', '"string"'],
        ['STRING', '"test"'],
    ])

    def test_strings2(self):
        self.lex(r"""
    "string";
        char* s1 = "asdjlsajdlksad""asdsajdlsad";       //comment6
    char* s2 = "asdjlsajdlksad"  "asdsajdlsad";         // \
                                                        single line comment \
        with escapes
    char* s3 = " asdsaldjkas \"";
    char* s4 = " asdsaldjkas \" zxclzxclk \" asljda";
    char* s5 = " asdsaldjkas \' zxclzxclk \" asljda";
    char* s6 = " asdsaldjkas \"\"\" zxclzxclk \'\'\' ; asljda";
    char* s7 = u8"test";
""", [
        ['STRING', '"string"'],
        ['IDENTIFIER', 'char'],
        ['IDENTIFIER', 's1'],
        ['STRING', '"asdjlsajdlksad"'],
        ['STRING', '"asdsajdlsad"'],
        ['COMMENT', '//comment6\n'],
        ['IDENTIFIER', 'char'],
        ['IDENTIFIER', 's2'],
        ['STRING', '"asdjlsajdlksad"'],
        ['STRING', '"asdsajdlsad"'],
        ['COMMENT', '// \\\n                                                        single line comment \\\n        with escapes\n'],
        ['IDENTIFIER', 'char'],
        ['IDENTIFIER', 's3'],
        ['STRING', '" asdsaldjkas \\""'],
        ['IDENTIFIER', 'char'],
        ['IDENTIFIER', 's4'],
        ['STRING', '" asdsaldjkas \\" zxclzxclk \\" asljda"'],
        ['IDENTIFIER', 'char'],
        ['IDENTIFIER', 's5'],
        ['STRING', '" asdsaldjkas \\\' zxclzxclk \\" asljda"'],
        ['IDENTIFIER', 'char'],
        ['IDENTIFIER', 's6'],
        ['STRING', '" asdsaldjkas \\"\\"\\" zxclzxclk \\\'\\\'\\\' ; asljda"'],
        ['IDENTIFIER', 'char'],
        ['IDENTIFIER', 's7'],
        ['IDENTIFIER', 'u8'],
        ['STRING', '"test"'],
    ])

    def test_chars(self):
        self.lex(r"""
'a';
u8'a';
u'a';
U'a';
'\'';
'\"';
'\\';
'\n';
'\f';
'\U0001f34c';
'\13';
'\x1234';
'\u213';
u'ą';
""", [
        ['STRING', "'a'"],
        ['IDENTIFIER', 'u8'],
        ['STRING', "'a'"],
        ['IDENTIFIER', 'u'],
        ['STRING', "'a'"],
        ['IDENTIFIER', 'U'],
        ['STRING', "'a'"],
        ['STRING', "'\\''"],
        ['STRING', '\'\\"\''],
        ['STRING', "'\\\\'"],
        ['STRING', "'\\n'"],
        ['STRING', "'\\f'"],
        ['STRING', "'\\U0001f34c'"],
        ['STRING', "'\\13'"],
        ['STRING', "'\\x1234'"],
        ['STRING', "'\\u213'"],
        ['IDENTIFIER', 'u'],
        ['STRING', "'ą'"],
    ])

    def test_numbers(self):
        self.lex(r"""
1239183;
-1239183;
0xAB08902;
-0xAB08902;
0Xab08902;
-0Xab08902;
0b0101001;
-0b0101001;
0B0101001;
-0B0101001;
0231273;
-0231273;
""", [
        ['NUMBER', '1239183'],
        ['NUMBER', '1239183'],
        ['NUMBER', '0xAB08902'],
        ['NUMBER', '0xAB08902'],
        ['NUMBER', '0Xab08902'],
        ['NUMBER', '0Xab08902'],
        ['NUMBER', '0b0101001'],
        ['NUMBER', '0b0101001'],
        ['NUMBER', '0B0101001'],
        ['NUMBER', '0B0101001'],
        ['NUMBER', '0231273'],
        ['NUMBER', '0231273'],
    ], self.default_filtered_tokens + ("NUMBER",))

    def test_floats(self):
        self.lex(r"""
double       e = 0x2ABDEFabcdef;
double
    f = 017.048509495;
double     -g = 0b1010010;
double     g = 0b1010010;
-017.048509495;
017.048509495;
-017.048509495e-12329123;
017.048509495e-12329123;
-0x123.fp34;
0x123.fp34;
-0x123.fP34;
0x123.fP34;
-0x123.fe1p123;
0x123.fe1p123;
-0x123.fe1p123;
0x123.fe1p123;
-.1;
.1;
-1.;
1.;
-0x1.ep+3;
0x1.ep+3;
-0X183083;
0X183083;
-0x213213.1231212'31e21p-2;
0x213213.1231212'31e21p-2;
-123123.123e2;
123123.123e2;
""", [
        ['IDENTIFIER', 'double'],
        ['IDENTIFIER', 'e'],
        ['NUMBER', '0x2ABDEFabcdef'],
        ['IDENTIFIER', 'double'],
        ['IDENTIFIER', 'f'],
        ['NUMBER', '017.048509495'],
        ['IDENTIFIER', 'double'],
        ['IDENTIFIER', 'g'],
        ['NUMBER', '0b1010010'],
        ['IDENTIFIER', 'double'],
        ['IDENTIFIER', 'g'],
        ['NUMBER', '0b1010010'],
        ['NUMBER', '017.048509495'],
        ['NUMBER', '017.048509495'],
        ['NUMBER', '017.048509495e-12329123'],
        ['NUMBER', '017.048509495e-12329123'],
        ['NUMBER', '0x123.fp34'],
        ['NUMBER', '0x123.fp34'],
        ['NUMBER', '0x123.fP34'],
        ['NUMBER', '0x123.fP34'],
        ['NUMBER', '0x123.fe1p123'],
        ['NUMBER', '0x123.fe1p123'],
        ['NUMBER', '0x123.fe1p123'],
        ['NUMBER', '0x123.fe1p123'],
        ['NUMBER', '1'],
        ['NUMBER', '1'],
        ['NUMBER', '1.'],
        ['NUMBER', '1.'],
        ['NUMBER', '0x1.ep+3'],
        ['NUMBER', '0x1.ep+3'],
        ['NUMBER', '0X183083'],
        ['NUMBER', '0X183083'],
        ['NUMBER', "0x213213.1231212'31e21p-2"],
        ['NUMBER', "0x213213.1231212'31e21p-2"],
        ['NUMBER', '123123.123e2'],
        ['NUMBER', '123123.123e2'],
    ], self.default_filtered_tokens + ("NUMBER",))

    def test_longs(self):
        self.lex(r"""
-123213092183ul;
123213092183ul;
-123213092183ull;
123213092183ull;
-123213092183llu;
123213092183llu;
-123213092183uLL;
123213092183uLL;
-123213092183LLU;
123213092183LLU;
-1232'13092183LLU;
1232'13092183LLU;
-1232'1309'2183LLU;
1232'1309'2183LLU;
-1232'1309'218'3LLU;
1232'1309'218'3LLU;
""", [
        ['NUMBER', '123213092183ul'],
        ['NUMBER', '123213092183ul'],
        ['NUMBER', '123213092183ull'],
        ['NUMBER', '123213092183ull'],
        ['NUMBER', '123213092183llu'],
        ['NUMBER', '123213092183llu'],
        ['NUMBER', '123213092183uLL'],
        ['NUMBER', '123213092183uLL'],
        ['NUMBER', '123213092183LLU'],
        ['NUMBER', '123213092183LLU'],
        ['NUMBER', "1232'13092183LLU"],
        ['NUMBER', "1232'13092183LLU"],
        ['NUMBER', "1232'1309'2183LLU"],
        ['NUMBER', "1232'1309'2183LLU"],
        ['NUMBER', "1232'1309'218'3LLU"],
        ['NUMBER', "1232'1309'218'3LLU"],
    ], self.default_filtered_tokens + ("NUMBER",))

    def test_comments(self):
        self.lex(r"""
    /*comment1*/
    /* comment2*/
    /* comment3 */
    /*
     *
        comment4
    _+}{|":?><~!@#$%&*()_+`123567890-=[];'\,./
     * */

    /* comment 5 \*\// */

// comment5
char* s2 = "asdjlsajdlksad"  "asdsajdlsad";         // \
                                   single line comment \
        with escapes
char statement;
""", [
        ['COMMENT', '/*comment1*/'],
        ['COMMENT', '/* comment2*/'],
        ['COMMENT', '/* comment3 */'],
        ['COMMENT', '/*\n     *\n        comment4\n    _+}{|":?><~!@#$%&*()_+`123567890-=[];\'\\,./\n     * */'],
        ['COMMENT', '/* comment 5 \\*\\// */'],
        ['COMMENT', '// comment5\n'],
        ['IDENTIFIER', 'char'],
        ['IDENTIFIER', 's2'],
        ['STRING', '"asdjlsajdlksad"'],
        ['STRING', '"asdsajdlsad"'],
        ['COMMENT', '// \\\n                                   single line comment \\\n        with escapes\n'],
        ['IDENTIFIER', 'char'],
        ['IDENTIFIER', 'statement'],
    ])

    # https://en.cppreference.com/w/cpp/language/pack_indexing
    def test_cpp_templates(self):
        self.lex(r"""
template<typename... Ts>
constexpr auto f(Ts&&... ts) {
    return sizeof...(Ts);
}

template<typename T, T::t t = 0>
int f() {
    std::cout << t << std::endl;
    ns1::ns2::type v;
    ns1::ns2::type2<int> v2;
    ns1::ns2::type3<int, double> v3;
}
""", [
        ['IDENTIFIER', 'template'],
        ['IDENTIFIER', 'typename'],
        ['IDENTIFIER', 'Ts'],
        ['IDENTIFIER', 'constexpr'],
        ['IDENTIFIER', 'auto'],
        ['IDENTIFIER', 'f'],
        ['IDENTIFIER', 'Ts'],
        ['IDENTIFIER', 'ts'],
        ['IDENTIFIER', 'return'],
        ['IDENTIFIER', 'sizeof'],
        ['IDENTIFIER', 'Ts'],
        ['IDENTIFIER', 'template'],
        ['IDENTIFIER', 'typename'],
        ['IDENTIFIER', 'T'],
        ['IDENTIFIER', 'T'],
        ['IDENTIFIER', 't'],
        ['IDENTIFIER', 't'],
        ['IDENTIFIER', 'int'],
        ['IDENTIFIER', 'f'],
        ['IDENTIFIER', 'std'],
        ['IDENTIFIER', 'cout'],
        ['IDENTIFIER', 't'],
        ['IDENTIFIER', 'std'],
        ['IDENTIFIER', 'endl'],
        ['IDENTIFIER', 'ns1'],
        ['IDENTIFIER', 'ns2'],
        ['IDENTIFIER', 'type'],
        ['IDENTIFIER', 'v'],
        ['IDENTIFIER', 'ns1'],
        ['IDENTIFIER', 'ns2'],
        ['IDENTIFIER', 'type2'],
        ['IDENTIFIER', 'int'],
        ['IDENTIFIER', 'v2'],
        ['IDENTIFIER', 'ns1'],
        ['IDENTIFIER', 'ns2'],
        ['IDENTIFIER', 'type3'],
        ['IDENTIFIER', 'int'],
        ['IDENTIFIER', 'double'],
        ['IDENTIFIER', 'v3'],
    ])

    # https://en.cppreference.com/w/cpp/language/requires
    def test_cpp_concepts(self):
        self.lex(r"""
template<typename T>
concept C = requires(T x) {
    {x.count()} -> std::same_as<int>;
    requires Same<T*, decltype(&x)>
};
""", [
        ['IDENTIFIER', 'template'],
        ['IDENTIFIER', 'typename'],
        ['IDENTIFIER', 'T'],
        ['IDENTIFIER', 'concept'],
        ['IDENTIFIER', 'C'],
        ['IDENTIFIER', 'requires'],
        ['IDENTIFIER', 'T'],
        ['IDENTIFIER', 'x'],
        ['IDENTIFIER', 'x'],
        ['IDENTIFIER', 'count'],
        ['IDENTIFIER', 'std'],
        ['IDENTIFIER', 'same_as'],
        ['IDENTIFIER', 'int'],
        ['IDENTIFIER', 'requires'],
        ['IDENTIFIER', 'Same'],
        ['IDENTIFIER', 'T'],
        ['IDENTIFIER', 'decltype'],
        ['IDENTIFIER', 'x'],
    ])

    def test_cpp_class(self):
        self.lex(r"""
using namespace std;

auto f() -> std::string;

class test {
public:
    int operator ""_tx(int);
    int a = 123_tx;
};
""", [
        ['IDENTIFIER', 'using'],
        ['IDENTIFIER', 'namespace'],
        ['IDENTIFIER', 'std'],
        ['IDENTIFIER', 'auto'],
        ['IDENTIFIER', 'f'],
        ['IDENTIFIER', 'std'],
        ['IDENTIFIER', 'string'],
        ['IDENTIFIER', 'class'],
        ['IDENTIFIER', 'test'],
        ['IDENTIFIER', 'public'],
        ['IDENTIFIER', 'int'],
        ['IDENTIFIER', 'operator'],
        ['STRING', '""'],
        ['IDENTIFIER', '_tx'],
        ['IDENTIFIER', 'int'],
        ['IDENTIFIER', 'int'],
        ['IDENTIFIER', 'a'],
        ['IDENTIFIER', '_tx'],
    ])

    def test_cpp_attrs(self):
        self.lex(r"""
[[using test: atr1]] [[atr2]]
int f[[atr3]]();
""", [
        ['IDENTIFIER', 'using'],
        ['IDENTIFIER', 'test'],
        ['IDENTIFIER', 'atr1'],
        ['IDENTIFIER', 'atr2'],
        ['IDENTIFIER', 'int'],
        ['IDENTIFIER', 'f'],
        ['IDENTIFIER', 'atr3'],
    ])

    # https://en.cppreference.com/w/cpp/language/noexcept_spec
    def test_cpp_noexpect(self):
        self.lex(r"""
void f() noexpect(true) {}
""", [
        ['IDENTIFIER', 'void'],
        ['IDENTIFIER', 'f'],
        ['IDENTIFIER', 'noexpect'],
        ['IDENTIFIER', 'true'],
    ])

    # https://en.cppreference.com/w/cpp/language/coroutines
    def test_cpp_coroutines(self):
        self.lex(r"""
task<> test() {
    co_await test2();
}
""", [
        ['IDENTIFIER', 'task'],
        ['IDENTIFIER', 'test'],
        ['IDENTIFIER', 'co_await'],
        ['IDENTIFIER', 'test2'],
    ])

class GasLexerTest(LexerTest):
    lexer_cls = GasLexer
    default_filtered_tokens = ("SPECIAL", "COMMENT", "STRING", "IDENTIFIER", "SPECIAL", "ERROR")

    def test_comments_m68k(self):
        self.lex(r"""
# comment 1
#comment 2
    clrl d1 | comment 3
    clrl d0 |comment 4
| comment 4

    clrl d2 # comment 3

#if defined(C1) || !defined(C2)
	addql #4,%sp
label:
	movel	#-IDNENT,%sp@(IDENT)| comment 5
// /linux/v6.10.7/source/arch/m68k/ifpsp060/src/fplsp.S
    test # comment 6
# endif

#define macro(x) inst &IDENT,%pc@(ident); inst x
""", [
        ['COMMENT', '# comment 1\n'],
        ['COMMENT', '#comment 2\n'],
        ['IDENTIFIER', 'clrl'],
        ['IDENTIFIER', 'd1'],
        ['COMMENT', '| comment 3\n'],
        ['IDENTIFIER', 'clrl'],
        ['IDENTIFIER', 'd0'],
        ['COMMENT', '|comment 4\n'],
        ['COMMENT', '| comment 4\n'],
        ['IDENTIFIER', 'clrl'],
        ['IDENTIFIER', 'd2'],
        ['COMMENT', '# comment 3\n'],
        ['SPECIAL', '#if'],
        ['IDENTIFIER', 'defined'],
        ['IDENTIFIER', 'C1'],
        ['IDENTIFIER', 'defined'],
        ['IDENTIFIER', 'C2'],
        ['IDENTIFIER', 'addql'],
        ['IDENTIFIER', 'sp'],
        ['IDENTIFIER', 'label'],
        ['IDENTIFIER', 'movel'],
        ['IDENTIFIER', 'IDNENT'],
        ['IDENTIFIER', 'sp'],
        ['IDENTIFIER', 'IDENT'],
        ['COMMENT', '| comment 5\n'],
        ['COMMENT', '// /linux/v6.10.7/source/arch/m68k/ifpsp060/src/fplsp.S\n'],
        ['IDENTIFIER', 'test'],
        ['COMMENT', '# comment 6\n'],
        ['SPECIAL', '# endif'],
        ['SPECIAL', '#define'],
        ['IDENTIFIER', 'macro'],
        ['IDENTIFIER', 'x'],
        ['IDENTIFIER', 'inst'],
        ['IDENTIFIER', 'IDENT'],
        ['IDENTIFIER', 'pc'],
        ['IDENTIFIER', 'ident'],
        ['IDENTIFIER', 'inst'],
        ['IDENTIFIER', 'x'],
    ], lexer_options={"arch": "m68k"})

    def test_comments_sparc(self):
        self.lex(r"""
#define F(i) 		\
	.type	i,@function;

    std	t1, [0x00];

/*comment default */
//comment default2
    .type identifier,#function
label:
        sethi   %hi(IDENT), %g0 !test comment
        wrpr %g1, %sp   ! test comment
# comment
#comment
        sethi   %hi(IDENT_1 | IDENT_2), %l0
""", [
        ['SPECIAL', '#define'],
        ['IDENTIFIER', 'F'],
        ['IDENTIFIER', 'i'],
        ['IDENTIFIER', 'type'],
        ['IDENTIFIER', 'i'],
        ['IDENTIFIER', 'function'],
        ['IDENTIFIER', 'std'],
        ['IDENTIFIER', 't1'],
        ['COMMENT', '/*comment default */'],
        ['COMMENT', '//comment default2\n'],
        ['IDENTIFIER', 'type'],
        ['IDENTIFIER', 'identifier'],
        ['IDENTIFIER', 'function'],
        ['IDENTIFIER', 'label'],
        ['IDENTIFIER', 'sethi'],
        ['IDENTIFIER', 'hi'],
        ['IDENTIFIER', 'IDENT'],
        ['IDENTIFIER', 'g0'],
        ['COMMENT', '!test comment\n'],
        ['IDENTIFIER', 'wrpr'],
        ['IDENTIFIER', 'g1'],
        ['IDENTIFIER', 'sp'],
        ['COMMENT', '! test comment\n'],
        ['COMMENT', '# comment\n'],
        ['COMMENT', '#comment\n'],
        ['IDENTIFIER', 'sethi'],
        ['IDENTIFIER', 'hi'],
        ['IDENTIFIER', 'IDENT_1'],
        ['IDENTIFIER', 'IDENT_2'],
        ['IDENTIFIER', 'l0'],
    ], lexer_options={"arch": "sparc"})

    def test_comments_arm32(self):
        self.lex(r"""
// comment default
/* comment default2 */
test:
    bic	r0, r1, #10
    # comment 1
    #comment 1
"""
+ "\t# comment 1" + r"""
	moveq	r0, #IDENTIFIER @ Comment
# comment 2
#comment 2
    push {r0}
    add \addr, \addr, \tmp  @comment3
    ldr r1, =TEST3
	ldr TEST, [sp, IDENT(i)];
	.long   PMD_TYPE_SECT | \
		PMD_BIT4
    stmfd	sp!, {r0, r1, r2, r3}
    eor RT0, d, b;
""", [
        ['COMMENT', '// comment default\n'],
        ['COMMENT', '/* comment default2 */'],
        ['IDENTIFIER', 'test'],
        ['IDENTIFIER', 'bic'],
        ['IDENTIFIER', 'r0'],
        ['IDENTIFIER', 'r1'],
        ['NUMBER', '10'],
        ['COMMENT', '# comment 1\n'],
        ['COMMENT', '#comment 1\n'],
        ['COMMENT', '# comment 1\n'],
        ['IDENTIFIER', 'moveq'],
        ['IDENTIFIER', 'r0'],
        ['IDENTIFIER', 'IDENTIFIER'],
        ['COMMENT', '@ Comment\n'],
        ['COMMENT', '# comment 2\n'],
        ['COMMENT', '#comment 2\n'],
        ['IDENTIFIER', 'push'],
        ['IDENTIFIER', 'r0'],
        ['IDENTIFIER', 'add'],
        ['IDENTIFIER', 'addr'],
        ['IDENTIFIER', 'addr'],
        ['IDENTIFIER', 'tmp'],
        ['COMMENT', '@comment3\n'],
        ['IDENTIFIER', 'ldr'],
        ['IDENTIFIER', 'r1'],
        ['IDENTIFIER', 'TEST3'],
        ['IDENTIFIER', 'ldr'],
        ['IDENTIFIER', 'TEST'],
        ['IDENTIFIER', 'sp'],
        ['IDENTIFIER', 'IDENT'],
        ['IDENTIFIER', 'i'],
        ['IDENTIFIER', 'long'],
        ['IDENTIFIER', 'PMD_TYPE_SECT'],
        ['IDENTIFIER', 'PMD_BIT4'],
        ['IDENTIFIER', 'stmfd'],
        ['IDENTIFIER', 'sp'],
        ['IDENTIFIER', 'r0'],
        ['IDENTIFIER', 'r1'],
        ['IDENTIFIER', 'r2'],
        ['IDENTIFIER', 'r3'],
        ['IDENTIFIER', 'eor'],
        ['IDENTIFIER', 'RT0'],
        ['IDENTIFIER', 'd'],
        ['IDENTIFIER', 'b'],
    ], self.default_filtered_tokens + ("NUMBER",), {"arch": "arm32"})

    def test_comments_generic(self):
        self.lex(r"""
/* comment
 * more comment
 * more comment
 */
    mov r0, r1  //test
    mov x0, #IDENT
    stp     x1, x2, [sp, #-4]!
#if defined(IDENT1) || defined(IDENT2)
#endif
""", [
        ['COMMENT', '/* comment\n * more comment\n * more comment\n */'],
        ['IDENTIFIER', 'mov'],
        ['IDENTIFIER', 'r0'],
        ['PUNCTUATION', ','],
        ['IDENTIFIER', 'r1'],
        ['COMMENT', '//test\n'],
        ['IDENTIFIER', 'mov'],
        ['IDENTIFIER', 'x0'],
        ['PUNCTUATION', ','],
        ['PUNCTUATION', '#'],
        ['IDENTIFIER', 'IDENT'],
        ['IDENTIFIER', 'stp'],
        ['IDENTIFIER', 'x1'],
        ['PUNCTUATION', ','],
        ['IDENTIFIER', 'x2'],
        ['PUNCTUATION', ','],
        ['PUNCTUATION', '['],
        ['IDENTIFIER', 'sp'],
        ['PUNCTUATION', ','],
        ['PUNCTUATION', '#'],
        ['PUNCTUATION', '-'],
        ['NUMBER', '4'],
        ['PUNCTUATION', ']'],
        ['PUNCTUATION', '!'],
        ['SPECIAL', '#if'],
        ['IDENTIFIER', 'defined'],
        ['PUNCTUATION', '('],
        ['IDENTIFIER', 'IDENT1'],
        ['PUNCTUATION', ')'],
        ['PUNCTUATION', '||'],
        ['IDENTIFIER', 'defined'],
        ['PUNCTUATION', '('],
        ['IDENTIFIER', 'IDENT2'],
        ['PUNCTUATION', ')'],
        ['SPECIAL', '#endif'],
    ], self.default_filtered_tokens + ("PUNCTUATION", "NUMBER"))

    def test_comments_preproc(self):
        self.lex(r"""
 # error "test"
#warning "test"
#include "test.h"
#include <test.h>
#if defined(T1) || defined(T2)
#endif
""", [
        ['SPECIAL', '# error "test"\n'],
        ['SPECIAL', '#warning "test"\n'],
        ['SPECIAL', '#include "test.h"'],
        ['SPECIAL', '#include <test.h>'],
        ['SPECIAL', '#if'],
        ['IDENTIFIER', 'defined'],
        ['IDENTIFIER', 'T1'],
        ['IDENTIFIER', 'defined'],
        ['IDENTIFIER', 'T2'],
        ['SPECIAL', '#endif'],
    ])

    def test_comments_literals(self):
        self.lex(r"""
.byte 12, 0b1010, 0B1010, 0x34, 0123, 0X45, 'a, '\b
.ascii "asdsad\"zxczc"
.float 0f-12321321030982394324\
        21321432432.234324324E-14
.float 0f-123.123213e+13
.float 0e-123.123213e+13
""", [
        ['IDENTIFIER', 'byte'],
        ['NUMBER', '12'],
        ['NUMBER', '0b1010'],
        ['NUMBER', '0B1010'],
        ['NUMBER', '0x34'],
        ['NUMBER', '0123'],
        ['NUMBER', '0X45'],
        ['STRING', "'a"],
        ['STRING', "'\\b"],
        ['IDENTIFIER', 'ascii'],
        ['STRING', '"asdsad\\"zxczc"'],
        ['IDENTIFIER', 'float'],
        ['NUMBER', '0f-12321321030982394324\\\n        21321432432.234324324E-14'],
        ['IDENTIFIER', 'float'],
        ['NUMBER', '0f-123.123213e+13'],
        ['IDENTIFIER', 'float'],
        ['NUMBER', '0e-123.123213e+13'],
    ], self.default_filtered_tokens + ("NUMBER",))


