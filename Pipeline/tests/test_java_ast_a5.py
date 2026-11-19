"""Tests for Pipeline/java_ast.py, stage A5: `logic_hints` and `values_hint` of methods and
constructors.

Same structure as test_java_ast_a4.py:
1. EXPECTED: (key, logic_hints, values_hint) of every method entry of every sample in
   java_samples/a5/ (keys in order), written by hand.
2. Regex comparison: AST must equal Context_gen.analyze_java_file, except the intentional fixes in
   KNOWN_DEVIATIONS (where the regex output is pinned too). The samples of A1-A4 are compared as
   well (common keys).
3. The patterns are the ones of Context_gen.

Regex compatibility kept on purpose (rule of stage A: seen by the model and found in the games;
removed later in stage B11): `this.f == x` gives the hint `f = = x) {`; `Outer.this.f = ...` is
taken; the expression is the raw text after `=` up to `;` or the line end, at most 60 characters
(a `;` in a string literal cuts it); non-overlapping matches (`this.a == 1 || this.a == 2` and
`this.a = this.b = 0` give one hint); numbers also from string literals and from the parts of a
decimal number (`1000.0` -> `1000`, `0.004` -> `004`), not from literals with a suffix (`100f`).
Fixes: nothing from comments (A5-1, decision 19.11) or string literals; the body ends where the
method ends (decision 17.11, as A4-2); `this . f = 1` and `this.f /* c */ = 1` are taken (A5-n).
"""
import os

import pytest

import Context_gen
import java_ast

HERE = os.path.dirname(os.path.abspath(__file__))
SAMPLES_DIR = os.path.join(HERE, "java_samples", "a5")
OTHER_SAMPLE_DIRS = [os.path.join(HERE, "java_samples", d) for d in ("a1", "a2", "a3", "a4")]

pytestmark = pytest.mark.filterwarnings("ignore::java_ast.JavaParseWarning")


EXPECTED = {
    # Only `this.f = ...` of known fields (with an access modifier and at least two letters, A2);
    # a local variable or a field without `this.` is not a hint. Numbers have 2-5 digits.
    "AssignBasic.java": [
        ("AssignBasic_constructor_1", ["name = name", "score = 0"], []),
        ("reset", ["alive = true", "score = local + start * 2"], ["10"]),
        ("getScore", [], []),
    ],
    # regex compat (B11): `this.f == x` is taken for an assignment; `!=`, `<=`, `+=` are not.
    "AssignEqCompare.java": [
        ("check", ["state = = s) {"], []),
        ("step", [], ["20"]),
    ],
    # regex compat (B11): the expression is cut at 60 characters, only its first line is taken,
    # a line break right after `=` is skipped; the text runs past the expression (`) > 0) {`).
    "AssignLongAndMultiline.java": [
        ("build", ['message = "a very long message that is longer than sixty characters fo',
                   "total = a +", "count = a * 100"], ["100"]),
        ("ifAssign", ["count = this.total) > 0) {", "total = 0"], []),
    ],
    # regex compat (B11): non-overlapping matches. The `this.step` / `this.second` / `this.first`
    # inside the text of the previous match are skipped, also when the previous field (`tmp`,
    # package-private) is not a known field.
    "AssignConsumed.java": [
        ("inRange", ["step = = 5) || (this.step == 6) || (this.step == 7)"], []),
        ("chain", ["first = this.second = 0"], []),
        ("unknownFirst", [], []),
    ],
    # regex compat (B11): `Outer.this.f = ...` from an anonymous class; the anonymous `run` and the
    # enclosing `start` both get it (B3).
    "AssignOuterThis.java": [
        ("start", ["running = true", "rounds = 10"], ["10"]),
        ("run", ["running = true", "rounds = 10"], ["10"]),
    ],
    # Compound assignments, increments, array elements, fields of fields, other objects: no hint.
    "AssignNotTaken.java": [
        ("update", [], ["20"]),
    ],
    # Fix A5-n: spaces around the dot or a comment before `=` (regex cannot see these).
    "AssignSpacing.java": [
        ("set", ["speed = s", "level = s * 10"], ["10"]),
    ],
    # Fix A5-1: assignments and numbers in comments are not taken.
    "AssignInComment.java": [
        ("resize", ["width = w", "height = h"], []),
    ],
    # Fix A5-n: `this.f = ...` inside a string literal is not a hint (its number is a value, B11);
    # regex compat (B11): a `;` inside a string literal cuts the expression.
    "AssignInString.java": [
        ("init", ['code = "x'], ["42"]),
        ("log", ["help = s"], []),
    ],
    # At most 4 hints, repeats kept.
    "MoreThanFour.java": [
        ("init", ["alpha = 1", "alpha = 1", "beta = 2", "gamma = 3"], []),
    ],
    # values_hint: no repeats, order of first occurrence, at most 6 (decision 11); regex compat
    # (B11): parts of decimal numbers, string literals, no literals with a suffix / hex / `1_000`;
    # an octal `010` is taken as written; 6 digits and one digit are not numbers.
    "Numbers.java": [
        ("dedup", [], ["50", "10", "300"]),
        ("decimals", [], ["1000", "25", "004"]),
        ("suffixes", [], ["010"]),
        ("signs", [], ["100", "200"]),
        ("firstSix", [], ["11", "22", "33", "44", "55", "66"]),
    ],
    # Fix (decision 17.11, as A4-2): `{` in a comment does not move the end of the body.
    "BodyEnd.java": [
        ("think", ["level = 1"], []),
        ("render", ["level = 42"], ["42"]),
    ],
}

# Samples where the hints / values differ on purpose; "regex" pins the regex output.
KNOWN_DEVIATIONS = {
    "AssignInComment.java": {
        "regex": [("resize", ["width = 640", "height = 480", "width = w", "height = h"],
                   ["640", "480", "200"])],
        "reason": "ASSIGN_PAT and NUMERIC_PAT run over the raw body text, comments included (A5-1)",
    },
    "AssignInString.java": {
        "regex": [("init", ['code = 42")', 'code = "x'], ["42"]),
                  ("log", ["help = s"], [])],
        "reason": "ASSIGN_PAT runs over string literals (A5-n)",
    },
    "AssignSpacing.java": {
        "regex": [("set", [], ["10"])],
        "reason": "ASSIGN_PAT needs `this.f` written together and only whitespace before `=` (A5-n)",
    },
    "BodyEnd.java": {
        "regex": [("think", ["level = 1", "level = 42"], ["42"]),
                  ("render", ["level = 42"], ["42"])],
        "reason": "extract_block counts the brace of `//if (level > 0) {`: `think` runs to the end "
                  "of the class",
    },
}

# A1-A4 samples where logic_hints / values_hint of a common key differ on purpose (none so far).
OTHER_KNOWN_DEVIATIONS = {}


def _read(directory, name):
    with open(os.path.join(directory, name), encoding="utf-8") as f:
        return f.read()


def _methods(parse, directory, name):
    result = parse(_read(directory, name), name)
    return None if result is None else result["methods"]


def _bodies(methods):
    return [(k, e["logic_hints"], e["values_hint"]) for k, e in methods.items()]


def test_every_sample_has_expectation():
    assert sorted(os.listdir(SAMPLES_DIR)) == sorted(EXPECTED)
    assert set(KNOWN_DEVIATIONS) <= set(EXPECTED)


@pytest.mark.parametrize("name", sorted(EXPECTED))
def test_expected(name):
    assert _bodies(_methods(java_ast.analyze_java_file_ast, SAMPLES_DIR, name)) == EXPECTED[name]


@pytest.mark.parametrize("name", sorted(EXPECTED))
def test_matches_regex_except_known_deviations(name):
    regex = _bodies(_methods(Context_gen.analyze_java_file, SAMPLES_DIR, name))
    ast = _bodies(_methods(java_ast.analyze_java_file_ast, SAMPLES_DIR, name))
    if name in KNOWN_DEVIATIONS:
        assert regex == KNOWN_DEVIATIONS[name]["regex"], "regex behaviour changed"
        assert ast != regex
    else:
        assert ast == regex


@pytest.mark.parametrize("name", sorted(EXPECTED))
def test_shape(name):
    for key, entry in _methods(java_ast.analyze_java_file_ast, SAMPLES_DIR, name).items():
        hints, values = entry["logic_hints"], entry["values_hint"]
        assert isinstance(hints, list) and all(isinstance(h, str) for h in hints), key
        assert len(hints) <= 4 and all(" = " in h for h in hints), key
        assert isinstance(values, list) and all(isinstance(v, str) for v in values), key
        assert len(values) <= 6 and len(set(values)) == len(values), key
        assert all(v.isdigit() and 2 <= len(v) <= 5 for v in values), key


def _other_samples():
    return [(d, n) for d in OTHER_SAMPLE_DIRS for n in sorted(os.listdir(d))]


def _sample_id(directory, name):
    return f"{os.path.basename(directory)}/{name}"


@pytest.mark.parametrize("directory, name", _other_samples(),
                         ids=[_sample_id(d, n) for d, n in _other_samples()])
def test_a1_a4_samples_match_regex(directory, name):
    # Keys that both parsers have get the same hints and values (which keys exist: A3).
    regex = _methods(Context_gen.analyze_java_file, directory, name)
    ast = _methods(java_ast.analyze_java_file_ast, directory, name)
    if regex is None or ast is None:
        return
    common = [k for k in ast if k in regex]
    got = [(k, ast[k]["logic_hints"], ast[k]["values_hint"]) for k in common]
    want = [(k, regex[k]["logic_hints"], regex[k]["values_hint"]) for k in common]
    known = OTHER_KNOWN_DEVIATIONS.get(_sample_id(directory, name))
    if known is not None:
        assert want == known["regex"], "regex behaviour changed"
        assert got != want
    else:
        assert got == want


def test_patterns_are_the_regex_ones():
    assert Context_gen.ASSIGN_PAT.pattern == r"(this\.\w+)" + java_ast._ASSIGN_TAIL.pattern
    assert java_ast.NUMERIC_PAT.pattern == Context_gen.NUMERIC_PAT.pattern


def _run(body, fields="private int score;\n    private String name;\n"):
    content = f"public class Foo {{\n    {fields}\n    public void run(int v) {{\n{body}\n    }}\n}}\n"
    regex = Context_gen.analyze_java_file(content, "Foo.java")["methods"]["run"]
    ast = java_ast.analyze_java_file_ast(content, "Foo.java")["methods"]["run"]
    return ((regex["logic_hints"], regex["values_hint"]), (ast["logic_hints"], ast["values_hint"]))


@pytest.mark.parametrize("body, hints, values", [
    ("this.score = v;", ["score = v"], []),
    ("this.score=v;", ["score = v"], []),                       # no spaces
    ("this.score = v; this.name = null;", ["score = v", "name = null"], []),  # same line
    ("if (this.score == 10) { }", ["score = = 10) { }"], ["10"]),
    ("this.score = this.score + 15;", ["score = this.score + 15"], ["15"]),
    ("this.unknown = 25;", [], ["25"]),                         # not a field of the class
    ("for (this.score = 0; this.score < 50; this.score++) { }", ["score = 0"], ["50"]),
    ("Runnable r = () -> this.score = 70;", ["score = 70"], ["70"]),
    ("this.score = 12345 + 123456;", ["score = 12345 + 123456"], ["12345"]),
])
def test_inline_forms(body, hints, values):
    regex, ast = _run(body, "private int score;\n    private String name;\n    int unknown;\n")
    assert ast == (hints, values)
    assert ast == regex


def test_non_ascii_body():
    # Byte offsets of tree-sitter vs characters: non-ASCII text before and inside the expression.
    regex, ast = _run('        // Größe 77\n        this.name = "Größe 88 ü";\n        this.score = 99;')
    assert ast == (['name = "Größe 88 ü"', "score = 99"], ["88", "99"])
    assert regex == (['name = "Größe 88 ü"', "score = 99"], ["77", "88", "99"])   # A5-1


def test_abstract_method_has_none():
    content = ("public abstract class Foo {\n    private int score;\n"
               "    public abstract void run(int v);\n}\n")
    entry = java_ast.analyze_java_file_ast(content, "Foo.java")["methods"]["run"]
    assert entry["logic_hints"] == [] and entry["values_hint"] == []
