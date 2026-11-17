"""Tests for Pipeline/java_ast.py, stage A2: fields, constants, assets.

Same structure as test_java_ast.py (A1):
1. EXPECTED: fields / constants / assets for every sample in java_samples/a2/, written by hand.
2. Regex comparison: AST must equal Context_gen.analyze_java_file on every sample, except the
   intentional fixes listed in KNOWN_DEVIATIONS (where the regex output is pinned too).
3. Dict order: insertion order goes into the JSON, so it is compared too (not only as sets).

Regex compatibility kept on purpose (decision 17.11, to be removed one by one in B4):
`int a, b;` keeps one declarator (the first one with an initializer, otherwise the last one) with
the type text up to its name (`int a,`); one-letter names are dropped; modifiers other than the
leading static / final stay in the type (`volatile int`); a constant needs the order
`public static final`; its value is cut at the first `;` (even inside a string) and to 60 chars.
"""
import os

import pytest

import Context_gen
import java_ast

HERE = os.path.dirname(os.path.abspath(__file__))
SAMPLES_DIR = os.path.join(HERE, "java_samples", "a2")
A1_SAMPLES_DIR = os.path.join(HERE, "java_samples", "a1")
A2_FIELDS = ("fields", "constants", "assets")

pytestmark = pytest.mark.filterwarnings("ignore::java_ast.JavaParseWarning")


def _a2(fields=None, constants=None, assets=None):
    return {"fields": fields or {}, "constants": constants or {}, "assets": assets or []}


def _c(type_, value):
    return {"type": type_, "value": value}


EXPECTED = {
    # Package-private field and local variable are not fields (regex rule: an access modifier
    # is required). Types are kept as written (qualified names, type arguments, arrays).
    "BasicFields.java": _a2({
        "score": "int", "playerName": "String", "running": "boolean", "speed": "double",
        "instances": "int", "names": "List<String>", "counts": "Map<String, Integer>",
        "levels": "int[]", "grid": "String[][]", "background": "java.awt.Color"}),
    # regex compat: one declarator per declaration, type = text up to its name.
    "MultiDeclarators.java": _a2({
        "curWidth": "int curX, curY,", "levelWidth": "int", "curJumpHeight": "float jumpHeight,",
        "ii": "int hh,", "py": "int px,"}),
    # regex compat: one-letter names and the name `String` are dropped (`u, v` -> `v` -> dropped).
    "ShortNames.java": _a2({"ab": "int"}),
    # regex compat: modifiers after the access modifier, except a leading static / final / static,
    # stay in the type.
    "ModifiersInType.java": _a2({
        "running": "volatile boolean", "cache": "transient int", "ORDER_FS": "int",
        "finalFirst": "int", "staticFirst": "int", "staticTransient": "transient int",
        "ticks": "volatile long"}),
    # Constants: `public static final` in this order, with an initializer. One-letter X is a
    # constant but not a field. Value: raw text up to the first `;` ("a;b" -> "a), max 60 chars.
    "Constants.java": _a2(
        {"MAX": "int", "NAME": "String", "SIZES": "int[]", "LONG_TEXT": "String",
         "MULTI_LINE": "String", "ORDER": "int", "HIDDEN": "int", "NO_INIT": "int", "SEP": "String"},
        {"MAX": _c("int", "100"), "NAME": _c("String", '"ApoGame"'),
         "SIZES": _c("int[]", "{16, 32, 64}"), "X": _c("int", "5"),
         "LONG_TEXT": _c("String", '"This value is longer than sixty characters, so it is cut of'),
         "MULTI_LINE": _c("String", '"first part, " +\n        "second part"'),
         "SEP": _c("String", '"a')}),
    # Interface fields without written modifiers are skipped (regex compat, B4).
    "InterfaceConstants.java": _a2({"HEIGHT": "int"}, {"HEIGHT": _c("int", "480")}),
    # regex compat: fields of nested, enum, anonymous and local classes go to the main class;
    # a repeated name keeps its first position and the last type (`count`: long).
    "NestedAndAnonymous.java": _a2(
        {"count": "long", "label": "String", "next": "Node", "LIMIT": "int", "level": "int",
         "ticks": "int", "done": "boolean"},
        {"LIMIT": _c("int", "8")}),
    # Enum constants are not fields.
    "EnumFields.java": _a2({"size": "int", "UNIT": "String"}, {"UNIT": _c("String", '"px"')}),
    # regex compat: only the first declarator, only with an initializer; value up to the first `;`.
    "MultiConstants.java": _a2({"MIN": "int", "SECOND": "int FIRST,"},
                               {"MIN": _c("int", "1, MAX = 9")}),
    # Assets: string literals whose whole text ends in an asset extension (case-sensitive),
    # no repeats, order of first occurrence.
    "Assets.java": _a2({"player": "String", "sounds": "String[]"}, assets=[
        "images/player.png", "sounds/jump.wav", "sounds/coin.mp3", "fonts/main.ttf",
        "tiles.gif", "photo.jpg"]),

    # --- intentional fixes (KNOWN_DEVIATIONS) ---
    "WildcardField.java": _a2({"numbers": "List<? extends Number>", "plain": "int"}),
    "AnnotationAfterModifier.java": _a2({"before": "int", "after": "int", "OLD_LIMIT": "int"},
                                        {"OLD_LIMIT": _c("int", "3")}),
    "CommentInDeclaration.java": _a2({"width": "int", "height": "int", "DELAY": "int"},
                                     {"DELAY": _c("int", "20")}),
    "FieldInComment.java": _a2({"real": "int"}),
    "FieldInString.java": _a2({"real": "int"}),
    "SecondTopLevel.java": _a2({"mine": "int"}),
    "ConstantTypes.java": _a2(
        {"SKY": "java.awt.Color", "SCORES": "Map<String, Integer>", "TABLE": "int[]"},
        {"SKY": _c("java.awt.Color", "java.awt.Color.BLUE"),
         "SCORES": _c("Map<String, Integer>", "null"), "TABLE": _c("int[]", "{1, 2}")}),
    # The chosen declarator has C-style brackets: the type gets them (`int[]`).
    "CStyleArray.java": _a2({"grid": "int[]", "data": "int[]", "cols": "int[]"}),
    "AssetsInComments.java": _a2({"sprite": "String"}, assets=["images/new.png"]),
    "AnonymousInInitializer.java": _a2({"task": "Runnable", "counter": "int", "after": "int"}),
}

# Intentional fixes of regex bugs (A2-n in .andrei/results/compat_report.md). "regex" pins what
# the regex parser returns today, so a change in regex behaviour is noticed too.
KNOWN_DEVIATIONS = {
    "WildcardField.java": {
        "regex": _a2({"plain": "int"}),
        "reason": "FIELD_PAT type class [\\w<>\\[\\].,\\s] has no `?`: the wildcard field is lost",
    },
    "AnnotationAfterModifier.java": {
        "regex": _a2({"before": "int"}),
        "reason": "FIELD_PAT / CONST_PAT cannot pass `@` after the access modifier",
    },
    "CommentInDeclaration.java": {
        "regex": _a2(),
        "reason": "FIELD_PAT / CONST_PAT cannot pass a comment inside the declaration",
    },
    "FieldInComment.java": {
        "regex": _a2({"ghost": "int", "GHOST_MAX": "int", "oldName": "String", "real": "int"},
                     {"GHOST_MAX": _c("int", "1")}),
        "reason": "FIELD_PAT / CONST_PAT match declarations inside comments",
    },
    "FieldInString.java": {
        "regex": _a2({"real": "int", "fake": "int", "FAKE_MAX": "int"},
                     {"FAKE_MAX": _c("int", "9")}),
        "reason": "FIELD_PAT / CONST_PAT match declarations inside string literals",
    },
    "SecondTopLevel.java": {
        "regex": _a2({"mine": "int", "theirs": "int", "HELPER_MAX": "int"},
                     {"HELPER_MAX": _c("int", "4")}),
        "reason": "FIELD_PAT / CONST_PAT run over the whole file: fields of the second top-level type",
    },
    "ConstantTypes.java": {
        "regex": _a2({"SKY": "java.awt.Color", "SCORES": "Map<String, Integer>"}),
        "reason": "CONST_PAT type class [\\w<>\\[\\]] has no `.`, `,`, space; `x[]` loses field and constant",
    },
    "CStyleArray.java": {
        "regex": _a2(),
        "reason": "FIELD_PAT needs `=` or `;` right after the name: `name[]` loses the field",
    },
    "AssetsInComments.java": {
        "regex": _a2({"sprite": "String"},
                     assets=["images/old.png", "sounds/beep.wav", "images/new.png"]),
        "reason": "ASSET_PAT runs over the whole text, comments included",
    },
    "AnonymousInInitializer.java": {
        "regex": _a2({"task": "Runnable", "after": "int"}),
        "reason": "FIELD_PAT initializer [^;]+ swallows the anonymous class up to its first `;`",
    },
}

def _read(directory, name):
    with open(os.path.join(directory, name), encoding="utf-8") as f:
        return f.read()


def _pick(result):
    return None if result is None else {k: result[k] for k in A2_FIELDS}


def _ordered(d):
    """Dicts and lists with their order (JSON output keeps insertion order)."""
    return {k: list(v.items()) if isinstance(v, dict) else v for k, v in d.items()}


def test_every_sample_has_expectation():
    assert sorted(os.listdir(SAMPLES_DIR)) == sorted(EXPECTED)
    assert set(KNOWN_DEVIATIONS) <= set(EXPECTED)


@pytest.mark.parametrize("name", sorted(EXPECTED))
def test_expected(name):
    ast = _pick(java_ast.analyze_java_file_ast(_read(SAMPLES_DIR, name), name))
    assert _ordered(ast) == _ordered(EXPECTED[name])


@pytest.mark.parametrize("name", sorted(EXPECTED))
def test_matches_regex_except_known_deviations(name):
    content = _read(SAMPLES_DIR, name)
    regex = _pick(Context_gen.analyze_java_file(content, name))
    ast = _pick(java_ast.analyze_java_file_ast(content, name))
    if name in KNOWN_DEVIATIONS:
        assert _ordered(regex) == _ordered(KNOWN_DEVIATIONS[name]["regex"]), "regex behaviour changed"
        assert ast != regex
    else:
        assert _ordered(ast) == _ordered(regex)


@pytest.mark.parametrize("name", sorted(os.listdir(A1_SAMPLES_DIR)))
def test_a1_samples_match_regex(name):
    # A1 samples: where both parsers return a module (headers: test_java_ast.py), the A2 fields
    # agree. Nested classes, a second top-level type without fields, generics, broken code.
    content = _read(A1_SAMPLES_DIR, name)
    regex = _pick(Context_gen.analyze_java_file(content, name))
    ast = _pick(java_ast.analyze_java_file_ast(content, name))
    if regex is not None and ast is not None:
        assert _ordered(ast) == _ordered(regex)


@pytest.mark.parametrize("name", sorted(EXPECTED))
def test_dict_shape(name):
    content = _read(SAMPLES_DIR, name)
    assert list(java_ast.analyze_java_file_ast(content, name)) == list(
        Context_gen.analyze_java_file(content, name))


def test_asset_pattern_is_the_regex_one():
    assert java_ast.ASSET_PAT.pattern == Context_gen.ASSET_PAT.pattern


def test_non_ascii_before_fields():
    # Node offsets are bytes; text before a field must not shift the extracted names / values.
    content = ('class Foo {\n    // Größe: ünïcödé\n    private String name = "Äpfel";\n'
               '    public static final String TITLE = "Spiel für alle";\n}\n')
    ast = java_ast.analyze_java_file_ast(content, "Foo.java")
    assert ast["fields"] == {"name": "String", "TITLE": "String"}
    assert ast["constants"] == {"TITLE": {"type": "String", "value": '"Spiel für alle"'}}


# Comments are removed, the whitespace around them is kept and collapsed (as clean_type does).
@pytest.mark.parametrize("decl, expected", [
    ("private List</* c */ String> names;", {"names": "List< String>"}),
    ("private List</* c */String> items;", {"items": "List<String>"}),
    ("private int /* a */ aa, /* b */ bb;", {"bb": "int aa,"}),
    ("private Map<String,\n        Integer> map;", {"map": "Map<String, Integer>"}),
    ("private static final transient int st;", {"st": "transient int"}),
])
def test_field_type_text(decl, expected):
    content = "class Foo {\n    " + decl + "\n}\n"
    assert java_ast.analyze_java_file_ast(content, "Foo.java")["fields"] == expected


def test_constant_value_without_semicolon_in_broken_code():
    # No `;` after the initializer: the value ends with the initializer node (no crash).
    content = "class Foo {\n    public static final int MAX = 5\n}\n"
    ast = java_ast.analyze_java_file_ast(content, "Foo.java")
    assert ast["constants"] == {"MAX": {"type": "int", "value": "5"}}
