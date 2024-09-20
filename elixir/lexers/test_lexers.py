import unittest
from .lexers import DTSLexer

class DtsLexerTests(unittest.TestCase):
    default_filtered_tokens = ("SPECIAL", "COMMENT", "STRING", "IDENTIFIER", "SPECIAL", "ERROR")

    def lex(self, code, expected, filtered_tokens=default_filtered_tokens):
        code = code.lstrip()
        tokens = [[type.name, token, span, line] for type, token, span, line in DTSLexer(code).lex()]
        tokens = [t for t in tokens if t[0] in filtered_tokens]
        #print()
        #for t in tokens: print(t, end=",\n")
        self.assertEqual(tokens, expected)

    def test_preproc(self):
        self.lex("""
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
        self.lex("""
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
        self.lex("""
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
        self.lex("""
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
        self.lex("""
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
        self.lex("""
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
        self.lex("""
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
        self.lex("""
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

