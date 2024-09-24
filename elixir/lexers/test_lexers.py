import unittest
from .lexers import DTSLexer, KconfigLexer, CLexer, GasLexer

class LexerTest(unittest.TestCase):
    default_filtered_tokens = ("SPECIAL", "COMMENT", "STRING", "IDENTIFIER", "SPECIAL", "ERROR")

    def lex(self, code, expected, filtered_tokens=None):
        if filtered_tokens is None:
            filtered_tokens = self.default_filtered_tokens

        code = code.lstrip()
        tokens = [[type.name, token, span, line] for type, token, span, line in self.lexer_cls(code).lex()]
        tokens = [t for t in tokens if t[0] in filtered_tokens]
        print()
        for t in tokens: print(t, end=",\n")
        self.assertEqual(tokens, expected)

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
        ['SPECIAL', '#include <file.dtsi>', (0, 20), 1],
        ['SPECIAL', '#include "file2.dtsi"', (21, 42), 2],
        ['SPECIAL', '#error error message asldjlksajdlksad\n', (43, 81), 3],
        ['SPECIAL', '#warning   warning message alsjdlkasjdlksajd\n', (81, 126), 4],
        ['SPECIAL', '#define', (126, 133), 5],
        ['IDENTIFIER', 'MACRO', (134, 139), 5],
        ['IDENTIFIER', 'arg', (140, 143), 5],
        ['IDENTIFIER', 'arg', (153, 156), 5],
        ['SPECIAL', '#if', (164, 167), 6],
        ['IDENTIFIER', 'property', (178, 186), 8],
        ['IDENTIFIER', 'MACRO', (198, 203), 9],
        ['IDENTIFIER', 'test', (204, 208), 9],
        ['SPECIAL', '#endif', (213, 219), 11],
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
        ['SPECIAL', '/include/', (0, 9), 1],
        ['STRING', '"file.dtsi"', (10, 21), 1],
        ['SPECIAL', '/dts-v1/', (22, 30), 2],
        ['SPECIAL', '/memreserve/', (32, 44), 3],
        ['IDENTIFIER', 'test_label', (64, 74), 5],
        ['IDENTIFIER', 'test-node', (76, 85), 5],
        ['IDENTIFIER', 'test-prop2', (96, 106), 6],
        ['IDENTIFIER', 'test-prop', (125, 134), 8],
        ['SPECIAL', '/delete-node/', (146, 159), 9],
        ['IDENTIFIER', 'test-node', (160, 169), 9],
        ['SPECIAL', '/delete-node/', (175, 188), 10],
        ['IDENTIFIER', 'test_label', (190, 200), 10],
        ['SPECIAL', '/delete-property/', (206, 223), 11],
        ['IDENTIFIER', 'test-prop', (224, 233), 11],
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
        ['IDENTIFIER', '_test_label', (8, 19), 2],
        ['IDENTIFIER', 'id,test._+asd-2', (29, 44), 2],
        ['IDENTIFIER', 'property,name', (65, 78), 3],
        ['IDENTIFIER', 'p,r.o_p+e?r#t-y,name', (95, 115), 4],
        ['IDENTIFIER', 'way_too_long_label_123219380921830218309218309213', (135, 184), 5],
        ['IDENTIFIER', 'node', (191, 195), 5],
        ['IDENTIFIER', '234', (196, 199), 5],
        ['IDENTIFIER', 'compatible', (214, 224), 6],
        ['STRING', '"asd,zxc"', (227, 236), 6],
        ['IDENTIFIER', 'test', (256, 260), 8],
        ['IDENTIFIER', 'way_too_long_label_123219380921830218309218309213', (268, 317), 8],
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
        ['IDENTIFIER', 'test', (8, 12), 2],
        ['IDENTIFIER', 'node', (14, 18), 2],
        ['IDENTIFIER', 'test_address', (19, 31), 2],
        ['IDENTIFIER', 'test2', (45, 50), 4],
        ['IDENTIFIER', 'node', (52, 56), 4],
        ['IDENTIFIER', 'MACRO_ADDRESS', (57, 70), 4],
    ])

    def test_values_with_labels(self):
        self.lex(r"""
/ {
    prop1 = label1: <0 label2: 0x21323>;
    prop2 = [1 2 3 label3: 4];
    prop3 = label4: "val" label5: ;
};
""", [
        ['PUNCTUATION', '/', (0, 1), 1],
        ['PUNCTUATION', '{', (2, 3), 1],
        ['IDENTIFIER', 'prop1', (8, 13), 2],
        ['PUNCTUATION', '=', (14, 15), 2],
        ['IDENTIFIER', 'label1', (16, 22), 2],
        ['PUNCTUATION', ':', (22, 23), 2],
        ['PUNCTUATION', '<', (24, 25), 2],
        ['NUMBER', '0', (25, 26), 2],
        ['IDENTIFIER', 'label2', (27, 33), 2],
        ['PUNCTUATION', ':', (33, 34), 2],
        ['NUMBER', '0x21323', (35, 42), 2],
        ['PUNCTUATION', '>', (42, 43), 2],
        ['PUNCTUATION', ';', (43, 44), 2],
        ['IDENTIFIER', 'prop2', (49, 54), 3],
        ['PUNCTUATION', '=', (55, 56), 3],
        ['PUNCTUATION', '[', (57, 58), 3],
        ['NUMBER', '1', (58, 59), 3],
        ['NUMBER', '2', (60, 61), 3],
        ['NUMBER', '3', (62, 63), 3],
        ['IDENTIFIER', 'label3', (64, 70), 3],
        ['PUNCTUATION', ':', (70, 71), 3],
        ['NUMBER', '4', (72, 73), 3],
        ['PUNCTUATION', ']', (73, 74), 3],
        ['PUNCTUATION', ';', (74, 75), 3],
        ['IDENTIFIER', 'prop3', (80, 85), 4],
        ['PUNCTUATION', '=', (86, 87), 4],
        ['IDENTIFIER', 'label4', (88, 94), 4],
        ['PUNCTUATION', ':', (94, 95), 4],
        ['STRING', '"val"', (96, 101), 4],
        ['IDENTIFIER', 'label5', (102, 108), 4],
        ['PUNCTUATION', ':', (108, 109), 4],
        ['PUNCTUATION', ';', (110, 111), 4],
        ['PUNCTUATION', '}', (112, 113), 5],
        ['PUNCTUATION', ';', (113, 114), 5],
    ], self.default_filtered_tokens + ('PUNCTUATION', 'NUMBER'))

    def test_references(self):
        self.lex(r"""
/ {
    interrupt-parent = < &{/node@c2342/another_node@address(2)/node3} >;
    property2 = <&{/node@c2342/another_node@address(2)}>;
    power-domains = <&power DEVICE_DOMAIN>;
};
""", [
        ['IDENTIFIER', 'interrupt-parent', (8, 24), 2],
        ['IDENTIFIER', 'node', (32, 36), 2],
        ['IDENTIFIER', 'c2342', (37, 42), 2],
        ['IDENTIFIER', 'another_node', (43, 55), 2],
        ['IDENTIFIER', 'address', (56, 63), 2],
        ['IDENTIFIER', 'node3', (67, 72), 2],
        ['IDENTIFIER', 'property2', (81, 90), 3],
        ['IDENTIFIER', 'node', (97, 101), 3],
        ['IDENTIFIER', 'c2342', (102, 107), 3],
        ['IDENTIFIER', 'another_node', (108, 120), 3],
        ['IDENTIFIER', 'address', (121, 128), 3],
        ['IDENTIFIER', 'power-domains', (139, 152), 4],
        ['IDENTIFIER', 'power', (157, 162), 4],
        ['IDENTIFIER', 'DEVICE_DOMAIN', (163, 176), 4],
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
        ['PUNCTUATION', '/', (0, 1), 1],
        ['PUNCTUATION', '{', (2, 3), 1],
        ['IDENTIFIER', 'prop1', (8, 13), 2],
        ['PUNCTUATION', '=', (14, 15), 2],
        ['PUNCTUATION', '<', (16, 17), 2],
        ['NUMBER', '0', (17, 18), 2],
        ['NUMBER', '0x21323', (19, 26), 2],
        ['PUNCTUATION', '>', (26, 27), 2],
        ['PUNCTUATION', ';', (27, 28), 2],
        ['IDENTIFIER', 'prop2', (33, 38), 3],
        ['PUNCTUATION', '=', (39, 40), 3],
        ['PUNCTUATION', '[', (41, 42), 3],
        ['NUMBER', '1', (42, 43), 3],
        ['NUMBER', '2', (44, 45), 3],
        ['NUMBER', '3', (46, 47), 3],
        ['NUMBER', '4', (48, 49), 3],
        ['PUNCTUATION', ']', (49, 50), 3],
        ['PUNCTUATION', ';', (50, 51), 3],
        ['IDENTIFIER', 'prop3', (56, 61), 4],
        ['PUNCTUATION', '=', (62, 63), 4],
        ['STRING', '"val"', (64, 69), 4],
        ['PUNCTUATION', ',', (69, 70), 4],
        ['STRING', '"val4"', (71, 77), 4],
        ['PUNCTUATION', ';', (78, 79), 4],
        ['IDENTIFIER', 'prop4', (84, 89), 5],
        ['PUNCTUATION', '=', (90, 91), 5],
        ['PUNCTUATION', '<', (92, 93), 5],
        ['PUNCTUATION', '~', (93, 94), 5],
        ['NUMBER', '1', (94, 95), 5],
        ['PUNCTUATION', '+', (95, 96), 5],
        ['NUMBER', '2', (96, 97), 5],
        ['PUNCTUATION', '-', (97, 98), 5],
        ['NUMBER', '3', (98, 99), 5],
        ['PUNCTUATION', '*', (99, 100), 5],
        ['NUMBER', '4', (100, 101), 5],
        ['PUNCTUATION', '/', (101, 102), 5],
        ['NUMBER', '5', (102, 103), 5],
        ['PUNCTUATION', '%', (103, 104), 5],
        ['NUMBER', '6', (104, 105), 5],
        ['PUNCTUATION', '&', (105, 106), 5],
        ['NUMBER', '7', (106, 107), 5],
        ['PUNCTUATION', '|', (107, 108), 5],
        ['NUMBER', '8', (108, 109), 5],
        ['PUNCTUATION', '^', (109, 110), 5],
        ['NUMBER', '9', (110, 111), 5],
        ['PUNCTUATION', '<', (111, 112), 5],
        ['PUNCTUATION', '<', (112, 113), 5],
        ['NUMBER', '10', (113, 115), 5],
        ['PUNCTUATION', '>', (115, 116), 5],
        ['PUNCTUATION', '>', (116, 117), 5],
        ['NUMBER', '11', (117, 119), 5],
        ['PUNCTUATION', '>', (119, 120), 5],
        ['PUNCTUATION', ';', (120, 121), 5],
        ['IDENTIFIER', 'prop5', (126, 131), 6],
        ['PUNCTUATION', ';', (131, 132), 6],
        ['PUNCTUATION', '}', (133, 134), 7],
        ['PUNCTUATION', ';', (134, 135), 7],
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
        ['COMMENT', '//license info\n', (0, 15), 1],
        ['IDENTIFIER', 'interrupts', (23, 33), 3],
        ['IDENTIFIER', 'NAME', (37, 41), 3],
        ['IDENTIFIER', 'TYPE', (46, 50), 3],
        ['COMMENT', '/* comment 1 */', (53, 68), 3],
        ['IDENTIFIER', 'NAME', (78, 82), 4],
        ['IDENTIFIER', 'TYPE', (87, 91), 4],
        ['COMMENT', '// comemnt2\n', (94, 106), 4],
        ['COMMENT', '/* long\n    * coment\n    * asdasd\n    */', (110, 150), 5],
    ], self.default_filtered_tokens)


class KconfigLexer(LexerTest):
    lexer_cls = KconfigLexer

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

    # comment 6""", [
            ['COMMENT', '# comment1\n', (0, 11), 1],
            ['SPECIAL', 'config', (11, 17), 2],
            ['IDENTIFIER', '64BIT', (18, 23), 2],
            ['COMMENT', '# comment2\n', (24, 35), 2],
            ['SPECIAL', 'bool', (39, 43), 3],
            ['COMMENT', '# comment3\n', (44, 55), 3],
            ['SPECIAL', 'default', (59, 66), 4],
            ['STRING', '"# asd"', (67, 74), 4],
            ['SPECIAL', 'default', (79, 86), 5],
            ['SPECIAL', 'shell', (89, 94), 5],
            ['SPECIAL', '\\#)', (96, 99), 5],
            ['SPECIAL', 'help', (104, 108), 6],
            ['COMMENT', '        asdasdsajdlakjd # not a comment\n\n        asdasdsajdlakjd # not a comment\n\n        # comment 5\n\n', (109, 212), 7],
            ['COMMENT', '# comment 6\n', (216, 228), 13],
        ])


    def test_keywords(self):
        self.lex(r""",
menu "menu name"

visible if y

choice
    prompt "test prompt"
    default y

conifg 86CONIFG
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

endmenu""", [
        ['SPECIAL', 'menu', (2, 6), 2],
        ['STRING', '"menu name"', (7, 18), 2],
        ['SPECIAL', 'visible', (20, 27), 4],
        ['SPECIAL', 'if', (28, 30), 4],
        ['SPECIAL', 'y', (31, 32), 4],
        ['SPECIAL', 'choice', (34, 40), 6],
        ['SPECIAL', 'prompt', (45, 51), 7],
        ['STRING', '"test prompt"', (52, 65), 7],
        ['SPECIAL', 'default', (70, 77), 8],
        ['SPECIAL', 'y', (78, 79), 8],
        ['SPECIAL', 'conifg', (81, 87), 10],
        ['IDENTIFIER', '86CONIFG', (88, 96), 10],
        ['SPECIAL', 'bool', (101, 105), 11],
        ['STRING', '"text"', (106, 112), 11],
        ['SPECIAL', 'prompt', (117, 123), 12],
        ['STRING', '"prompt"', (124, 132), 12],
        ['SPECIAL', 'default', (137, 144), 13],
        ['SPECIAL', 'y', (145, 146), 13],
        ['SPECIAL', 'tristate', (151, 159), 14],
        ['STRING', '"test"', (160, 166), 14],
        ['SPECIAL', 'def_bool', (171, 179), 15],
        ['IDENTIFIER', 'TEST_bool', (180, 189), 15],
        ['SPECIAL', 'depends', (194, 201), 16],
        ['SPECIAL', 'on', (202, 204), 16],
        ['IDENTIFIER', 'TEST', (205, 209), 16],
        ['SPECIAL', 'select', (214, 220), 17],
        ['IDENTIFIER', 'TEST2', (221, 226), 17],
        ['SPECIAL', 'imply', (231, 236), 18],
        ['IDENTIFIER', 'TEST3', (237, 242), 18],
        ['SPECIAL', 'range', (247, 252), 19],
        ['SPECIAL', 'if', (259, 261), 19],
        ['IDENTIFIER', 'CONFIG_512', (262, 272), 19],
        ['SPECIAL', 'help', (277, 281), 20],
        ['COMMENT', '        help text\n\n        more help text\n\n', (282, 325), 21],
        ['SPECIAL', 'endmenu', (325, 332), 25],
    ])

    def test_conditions(self):
        self.lex(r"""
config TEST
    select TEST1 if TEST2 = TEST3
    select TEST2 if TEST5 != TEST6
    select TEST7 if TEST8 < TEST9
    select TEST10 if TEST11 > TEST12
    select TEST13 if TEST14 <=  TEST15
    select TEST16    if TEST17   >= TEST3
    select TEST17 if (TEST18 = TEST19)

    select TEST20 if !(TEST21 = TEST22)
    select TEST23 if TEST24 && TEST25
    select TEST26 if TEST27 || TEST28""", [
        ['SPECIAL', 'config', (0, 6), 1],
        ['IDENTIFIER', 'TEST', (7, 11), 1],
        ['SPECIAL', 'select', (16, 22), 2],
        ['IDENTIFIER', 'TEST1', (23, 28), 2],
        ['SPECIAL', 'if', (29, 31), 2],
        ['IDENTIFIER', 'TEST2', (32, 37), 2],
        ['PUNCTUATION', '=', (38, 39), 2],
        ['IDENTIFIER', 'TEST3', (40, 45), 2],
        ['SPECIAL', 'select', (50, 56), 3],
        ['IDENTIFIER', 'TEST2', (57, 62), 3],
        ['SPECIAL', 'if', (63, 65), 3],
        ['IDENTIFIER', 'TEST5', (66, 71), 3],
        ['PUNCTUATION', '!', (72, 73), 3],
        ['PUNCTUATION', '=', (73, 74), 3],
        ['IDENTIFIER', 'TEST6', (75, 80), 3],
        ['SPECIAL', 'select', (85, 91), 4],
        ['IDENTIFIER', 'TEST7', (92, 97), 4],
        ['SPECIAL', 'if', (98, 100), 4],
        ['IDENTIFIER', 'TEST8', (101, 106), 4],
        ['PUNCTUATION', '<', (107, 108), 4],
        ['IDENTIFIER', 'TEST9', (109, 114), 4],
        ['SPECIAL', 'select', (119, 125), 5],
        ['IDENTIFIER', 'TEST10', (126, 132), 5],
        ['SPECIAL', 'if', (133, 135), 5],
        ['IDENTIFIER', 'TEST11', (136, 142), 5],
        ['PUNCTUATION', '>', (143, 144), 5],
        ['IDENTIFIER', 'TEST12', (145, 151), 5],
        ['SPECIAL', 'select', (156, 162), 6],
        ['IDENTIFIER', 'TEST13', (163, 169), 6],
        ['SPECIAL', 'if', (170, 172), 6],
        ['IDENTIFIER', 'TEST14', (173, 179), 6],
        ['PUNCTUATION', '<', (180, 181), 6],
        ['PUNCTUATION', '=', (181, 182), 6],
        ['IDENTIFIER', 'TEST15', (184, 190), 6],
        ['SPECIAL', 'select', (195, 201), 7],
        ['IDENTIFIER', 'TEST16', (202, 208), 7],
        ['SPECIAL', 'if', (212, 214), 7],
        ['IDENTIFIER', 'TEST17', (215, 221), 7],
        ['PUNCTUATION', '>', (224, 225), 7],
        ['PUNCTUATION', '=', (225, 226), 7],
        ['IDENTIFIER', 'TEST3', (227, 232), 7],
        ['SPECIAL', 'select', (237, 243), 8],
        ['IDENTIFIER', 'TEST17', (244, 250), 8],
        ['SPECIAL', 'if', (251, 253), 8],
        ['PUNCTUATION', '(', (254, 255), 8],
        ['IDENTIFIER', 'TEST18', (255, 261), 8],
        ['PUNCTUATION', '=', (262, 263), 8],
        ['IDENTIFIER', 'TEST19', (264, 270), 8],
        ['PUNCTUATION', ')', (270, 271), 8],
        ['SPECIAL', 'select', (277, 283), 10],
        ['IDENTIFIER', 'TEST20', (284, 290), 10],
        ['SPECIAL', 'if', (291, 293), 10],
        ['PUNCTUATION', '!', (294, 295), 10],
        ['PUNCTUATION', '(', (295, 296), 10],
        ['IDENTIFIER', 'TEST21', (296, 302), 10],
        ['PUNCTUATION', '=', (303, 304), 10],
        ['IDENTIFIER', 'TEST22', (305, 311), 10],
        ['PUNCTUATION', ')', (311, 312), 10],
        ['SPECIAL', 'select', (317, 323), 11],
        ['IDENTIFIER', 'TEST23', (324, 330), 11],
        ['SPECIAL', 'if', (331, 333), 11],
        ['IDENTIFIER', 'TEST24', (334, 340), 11],
        ['PUNCTUATION', '&', (341, 342), 11],
        ['PUNCTUATION', '&', (342, 343), 11],
        ['IDENTIFIER', 'TEST25', (344, 350), 11],
        ['SPECIAL', 'select', (355, 361), 12],
        ['IDENTIFIER', 'TEST26', (362, 368), 12],
        ['SPECIAL', 'if', (369, 371), 12],
        ['IDENTIFIER', 'TEST27', (372, 378), 12],
        ['PUNCTUATION', '|', (379, 380), 12],
        ['PUNCTUATION', '|', (380, 381), 12],
        ['IDENTIFIER', 'TEST28', (382, 388), 12],
    ], self.default_filtered_tokens + ("PUNCTUATION",))

    def test_macros(self):
        self.lex(r"""
conifg TEST
    depends on $(shell,cat file | grep -vi "option 2")
    depends on $(info,info to print)
    depends on $(warning-if,a != b,warning to print)
    depends on $(error-if,a != b,warning to print)
    depends on $(filename)
    depends on $(lineno)
""", [
        ['SPECIAL', 'conifg', (0, 6), 1],
        ['IDENTIFIER', 'TEST', (7, 11), 1],
        ['SPECIAL', 'depends', (16, 23), 2],
        ['SPECIAL', 'on', (24, 26), 2],
        ['PUNCTUATION', '$', (27, 28), 2],
        ['PUNCTUATION', '(', (28, 29), 2],
        ['SPECIAL', 'shell', (29, 34), 2],
        ['PUNCTUATION', ',', (34, 35), 2],
        ['SPECIAL', 'cat', (35, 38), 2],
        ['SPECIAL', 'file', (39, 43), 2],
        ['PUNCTUATION', '|', (44, 45), 2],
        ['SPECIAL', 'grep', (46, 50), 2],
        ['PUNCTUATION', '-', (51, 52), 2],
        ['SPECIAL', 'vi', (52, 54), 2],
        ['STRING', '"option 2"', (55, 65), 2],
        ['PUNCTUATION', ')', (65, 66), 2],
        ['SPECIAL', 'depends', (71, 78), 3],
        ['SPECIAL', 'on', (79, 81), 3],
        ['PUNCTUATION', '$', (82, 83), 3],
        ['PUNCTUATION', '(', (83, 84), 3],
        ['SPECIAL', 'info', (84, 88), 3],
        ['PUNCTUATION', ',', (88, 89), 3],
        ['SPECIAL', 'info', (89, 93), 3],
        ['SPECIAL', 'to', (94, 96), 3],
        ['SPECIAL', 'print', (97, 102), 3],
        ['PUNCTUATION', ')', (102, 103), 3],
        ['SPECIAL', 'depends', (108, 115), 4],
        ['SPECIAL', 'on', (116, 118), 4],
        ['PUNCTUATION', '$', (119, 120), 4],
        ['PUNCTUATION', '(', (120, 121), 4],
        ['SPECIAL', 'warning-if', (121, 131), 4],
        ['PUNCTUATION', ',', (131, 132), 4],
        ['SPECIAL', 'a', (132, 133), 4],
        ['PUNCTUATION', '!', (134, 135), 4],
        ['PUNCTUATION', '=', (135, 136), 4],
        ['SPECIAL', 'b', (137, 138), 4],
        ['PUNCTUATION', ',', (138, 139), 4],
        ['SPECIAL', 'warning', (139, 146), 4],
        ['SPECIAL', 'to', (147, 149), 4],
        ['SPECIAL', 'print', (150, 155), 4],
        ['PUNCTUATION', ')', (155, 156), 4],
        ['SPECIAL', 'depends', (161, 168), 5],
        ['SPECIAL', 'on', (169, 171), 5],
        ['PUNCTUATION', '$', (172, 173), 5],
        ['PUNCTUATION', '(', (173, 174), 5],
        ['SPECIAL', 'error-if', (174, 182), 5],
        ['PUNCTUATION', ',', (182, 183), 5],
        ['SPECIAL', 'a', (183, 184), 5],
        ['PUNCTUATION', '!', (185, 186), 5],
        ['PUNCTUATION', '=', (186, 187), 5],
        ['SPECIAL', 'b', (188, 189), 5],
        ['PUNCTUATION', ',', (189, 190), 5],
        ['SPECIAL', 'warning', (190, 197), 5],
        ['SPECIAL', 'to', (198, 200), 5],
        ['SPECIAL', 'print', (201, 206), 5],
        ['PUNCTUATION', ')', (206, 207), 5],
        ['SPECIAL', 'depends', (212, 219), 6],
        ['SPECIAL', 'on', (220, 222), 6],
        ['PUNCTUATION', '$', (223, 224), 6],
        ['PUNCTUATION', '(', (224, 225), 6],
        ['SPECIAL', 'filename', (225, 233), 6],
        ['PUNCTUATION', ')', (233, 234), 6],
        ['SPECIAL', 'depends', (239, 246), 7],
        ['SPECIAL', 'on', (247, 249), 7],
        ['PUNCTUATION', '$', (250, 251), 7],
        ['PUNCTUATION', '(', (251, 252), 7],
        ['SPECIAL', 'lineno', (252, 258), 7],
        ['PUNCTUATION', ')', (258, 259), 7],
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
        ['SPECIAL', 'config', (0, 6), 1],
        ['SPECIAL', 'help', (11, 15), 2],
        ['COMMENT', '     help test lasdlkajdk sadlksajd\n     lsajdlad\n\n     salkdjaldlksajd\n\n     "\n     asdlkajsdlkjsadlajdsk\n\n     salkdjlsakdj\'\n', (16, 143), 3],
        ['SPECIAL', 'config', (143, 149), 12],
        ['SPECIAL', 'select', (154, 160), 13],
        ['IDENTIFIER', 'TEST', (161, 165), 13],
        ['SPECIAL', 'config', (166, 172), 14],
        ['SPECIAL', '---help---', (177, 187), 15],
        ['COMMENT', '     help test lasdlkajdk sadlksajd\n     lsajdlad\n\n     salkdjaldlksajd\n        \n', (188, 269), 16],
        ['SPECIAL', 'config', (269, 275), 21],
        ['SPECIAL', 'select', (280, 286), 22],
        ['IDENTIFIER', 'TEST', (287, 291), 22],
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
        ['SPECIAL', 'config', (0, 6), 1],
        ['SPECIAL', 'bool', (11, 15), 2],
        ['SPECIAL', 'default', (20, 27), 3],
        ['SPECIAL', 'y', (28, 29), 3],
        ['SPECIAL', 'config', (31, 37), 5],
        ['SPECIAL', 'tristate', (42, 50), 6],
        ['SPECIAL', 'default', (55, 62), 7],
        ['SPECIAL', 'm', (63, 64), 7],
        ['SPECIAL', 'config', (66, 72), 9],
        ['SPECIAL', 'hex', (77, 80), 10],
        ['SPECIAL', 'default', (82, 89), 11],
        ['IDENTIFIER', '0xdfffffff00000000', (90, 108), 11],
        ['SPECIAL', 'config', (110, 116), 13],
        ['SPECIAL', 'string', (121, 127), 14],
        ['SPECIAL', 'default', (132, 139), 15],
        ['STRING', '"string \\" test # \\# zxc"', (140, 165), 15],
        ['SPECIAL', 'config', (167, 173), 17],
        ['SPECIAL', 'int', (178, 181), 18],
        ['SPECIAL', 'default', (186, 193), 19],
    ])

class CLexerTest(unittest.TestCase):
    lexer_cls = CLexer

    # comments with escapes
    # weird numbers
    # string concat
    # newline escapes in macros
    # includes, warnings, errors, pragmas

class GasLexerTest(unittest.TestCase):
    lexer_cls = GasLexer

    # comments in differetnt arch with doubles pipes and hashses
    # different literals
    # flonums
    # char thing
    # preproc, comments and hash literals
    # test this u-boot/v2024.07/source/arch/arm/cpu/armv7/psci.S#L147


