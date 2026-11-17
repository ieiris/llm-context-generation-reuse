"""Tests for Pipeline/java_ast.py, stage A4: `calls` of methods and constructors.

Same structure as test_java_ast_a3.py:
1. EXPECTED: the `calls` of every method entry of every sample in java_samples/a4/ (keys in order),
   written by hand.
2. Regex comparison: AST `calls` must equal Context_gen.analyze_java_file, except the intentional
   fixes in KNOWN_DEVIATIONS (where the regex output is pinned too). The samples of A1-A3 are
   compared as well (common keys).
3. The receiver filter is the one of Context_gen.extract_method_calls.

Regex compatibility kept on purpose (decisions 17.11, removed later in stage B):
the receiver is the last name before the method (`this.x.foo()` -> `x.foo`, `System.out.println`
-> `out.println`), `X.class.foo()` -> `class.foo`; no entry for chains `a().foo()`, `arr[i].foo()`,
`(x).foo()`, `new X().foo()`, calls without a receiver; `x`, `.`, name and `(` must be written
without anything in between (B5b); `new A.B(` -> `A.B` (B5b); receivers this / super / self / Math /
System / String / Integer / Boolean / Object are dropped (B5a); calls of nested, anonymous and local
classes and lambdas also go to the enclosing method (B3); overloads: the calls of the last one (B2).
Fixes (decision 17.11): calls in comments and string literals are not taken; the body ends where
the method ends (braces in comments, strings and characters do not count).
"""
import ast as pyast
import inspect
import os

import pytest

import Context_gen
import java_ast

HERE = os.path.dirname(os.path.abspath(__file__))
SAMPLES_DIR = os.path.join(HERE, "java_samples", "a4")
OTHER_SAMPLE_DIRS = [os.path.join(HERE, "java_samples", d) for d in ("a1", "a2", "a3")]

pytestmark = pytest.mark.filterwarnings("ignore::java_ast.JavaParseWarning")


EXPECTED = {
    # Receiver = last name before the method; chains, arrays, parentheses, `new X()`, literals and
    # calls without a receiver give no entry; this / super are filtered.
    "ReceiverForms.java": [
        ("self", []),
        ("size", ["names.size"]),
        ("forms", ["names.clear", "next.size", "other.size", "out.println"]),
    ],
    # Math / System / String / Integer / Boolean / Object / self as receiver names are dropped, even
    # when they are variables.
    "FilteredReceivers.java": [
        ("filtered", ["b.booleanValue", "i.intValue", "o.hashCode", "s.length"]),
        ("objectVariable", []),
    ],
    # regex compat (B5b): a class literal gives the receiver `class`.
    "ClassLiteralCall.java": [
        ("open", ["class.getResourceAsStream"]),
        ("names", ["class.getName"]),
    ],
    # regex compat (B5b): a line break, space, comment or type arguments between the parts lose
    # the call.
    "SplitCall.java": [
        ("split", ["list.indexOf"]),
    ],
    # regex compat (B5b): `new A.B(` is taken for a call `A.B` (last two parts of the type name).
    "QualifiedNew.java": [
        ("rect", ["Rectangle2D.Float"]),
        ("all", ["Rectangle2D.Double", "awt.Point"]),
    ],
    # The calls of anonymous and local classes and lambdas are also in the enclosing method (B3);
    # `run` is the one of the anonymous Thread (same name: last value). `Outer.this.stop()` is
    # filtered as `this.stop`.
    "NestedCalls.java": [
        ("run", ["h.tick"]),
        ("start", ["h.count", "h.reset", "h.tick", "t.start"]),
        ("value", ["h.count"]),
        ("stop", []),
        ("tick", ["Thread.yield"]),
        ("count", []),
        ("reset", []),
    ],
    # Constructors of the same arity and overloads: the calls of the last one; the abstract
    # `render(int)` overwrites `render()` with an empty list.
    "OverloadAndAbstractCalls.java": [
        ("OverloadAndAbstractCalls_constructor_0", ["sb.append"]),
        ("OverloadAndAbstractCalls_constructor_1", ["sb.setLength"]),
        ("add", ["sb.insert"]),
        ("render", []),
    ],
    # Unique and sorted as Python strings (upper case before `_` before lower case).
    "DuplicateAndOrder.java": [
        ("move", []),
        ("jump", []),
        ("order", ["Alpha.move", "Zeta.move", "_x.move", "beta.jump", "player.jump", "player.move"]),
    ],
    # `this(...)` / `super(...)` are not calls; `super.run()` is filtered.
    "ConstructorCalls.java": [
        ("ConstructorCalls_constructor_0", ["log.append"]),
        ("ConstructorCalls_constructor_1", ["log.append"]),
        ("run", ["log.setLength"]),
    ],
    # Field initializers and initializer blocks belong to no method.
    "NonMethodCode.java": [
        ("size", []),
    ],
    # Fix A4-1: calls in comments (also javadoc inside the body) are not taken.
    "CallInComment.java": [
        ("clean", ["items.add"]),
        ("count", ["items.size"]),
    ],
    # Fix A4-2: braces in comments do not move the end of the body.
    "BraceInComment.java": [
        ("close", ["sb.trimToSize"]),
        ("think", ["sb.append"]),
        ("render", ["sb.reverse"]),
        ("reset", ["sb.setLength"]),
    ],
    # Fix A4-3: `x.y(` inside a string literal is not a call.
    "CallInString.java": [
        ("help", ["sb.append"]),
    ],
    # Fix A4-4: braces in string and character literals do not move the end of the body.
    "BraceInString.java": [
        ("open", ["sb.append"]),
        ("close", ["sb.append", "sb.reverse"]),
        ("last", ["sb.setLength"]),
    ],
}

# Samples where the calls differ on purpose; "regex" pins the regex output.
KNOWN_DEVIATIONS = {
    "CallInComment.java": {
        "regex": [("clean", ["debug.dump", "items.add", "items.clear", "old.remove"]),
                  ("count", ["items.size", "out.println"])],
        "reason": "CALL_PAT runs over the raw body text, comments included",
    },
    "BraceInComment.java": {
        "regex": [("close", []),
                  ("think", ["sb.append", "sb.reverse", "sb.setLength"]),
                  ("render", ["sb.reverse"]),
                  ("reset", ["sb.setLength"])],
        "reason": "extract_block counts the braces of comments: `/* } */` ends `close` early, "
                  "`//if (x > 0) {` makes `think` run to the end of the class",
    },
    "CallInString.java": {
        "regex": [("help", ["list.add", "player.jump", "sb.append"])],
        "reason": "CALL_PAT runs over string literals",
    },
    "BraceInString.java": {
        "regex": [("open", ["sb.append", "sb.reverse", "sb.setLength"]),
                  ("close", ["sb.append"]),
                  ("last", ["sb.setLength"])],
        "reason": "extract_block counts the braces of string and character literals (unbalanced: "
                  "the first 800 characters)",
    },
}

# A1-A3 samples where the calls of a common key differ on purpose (none so far).
OTHER_KNOWN_DEVIATIONS = {}


def _read(directory, name):
    with open(os.path.join(directory, name), encoding="utf-8") as f:
        return f.read()


def _methods(parse, directory, name):
    result = parse(_read(directory, name), name)
    return None if result is None else result["methods"]


def _calls(methods):
    return [(k, e["calls"]) for k, e in methods.items()]


def test_every_sample_has_expectation():
    assert sorted(os.listdir(SAMPLES_DIR)) == sorted(EXPECTED)
    assert set(KNOWN_DEVIATIONS) <= set(EXPECTED)


@pytest.mark.parametrize("name", sorted(EXPECTED))
def test_expected(name):
    assert _calls(_methods(java_ast.analyze_java_file_ast, SAMPLES_DIR, name)) == EXPECTED[name]


@pytest.mark.parametrize("name", sorted(EXPECTED))
def test_matches_regex_except_known_deviations(name):
    regex = _calls(_methods(Context_gen.analyze_java_file, SAMPLES_DIR, name))
    ast = _calls(_methods(java_ast.analyze_java_file_ast, SAMPLES_DIR, name))
    if name in KNOWN_DEVIATIONS:
        assert regex == KNOWN_DEVIATIONS[name]["regex"], "regex behaviour changed"
        assert ast != regex
    else:
        assert ast == regex


@pytest.mark.parametrize("name", sorted(EXPECTED))
def test_calls_shape(name):
    for key, entry in _methods(java_ast.analyze_java_file_ast, SAMPLES_DIR, name).items():
        calls = entry["calls"]
        assert isinstance(calls, list) and all(isinstance(c, str) for c in calls), key
        assert calls == sorted(set(calls)), key
        assert all(c.count(".") == 1 for c in calls), key


def _other_samples():
    return [(d, n) for d in OTHER_SAMPLE_DIRS for n in sorted(os.listdir(d))]


def _sample_id(directory, name):
    return f"{os.path.basename(directory)}/{name}"


@pytest.mark.parametrize("directory, name", _other_samples(),
                         ids=[_sample_id(d, n) for d, n in _other_samples()])
def test_a1_a3_samples_match_regex(directory, name):
    # Keys that both parsers have get the same calls (which keys exist is checked in A3).
    regex = _methods(Context_gen.analyze_java_file, directory, name)
    ast = _methods(java_ast.analyze_java_file_ast, directory, name)
    if regex is None or ast is None:
        return
    common = [k for k in ast if k in regex]
    got = [(k, ast[k]["calls"]) for k in common]
    want = [(k, regex[k]["calls"]) for k in common]
    known = OTHER_KNOWN_DEVIATIONS.get(_sample_id(directory, name))
    if known is not None:
        assert want == known["regex"], "regex behaviour changed"
        assert got != want
    else:
        assert got == want


def _regex_filter_tuple():
    """The tuple of receivers in Context_gen.extract_method_calls (`if obj not in (...)`)."""
    tree = pyast.parse(inspect.getsource(Context_gen.extract_method_calls))
    tuples = [n for n in pyast.walk(tree) if isinstance(n, pyast.Tuple)
              and all(isinstance(e, pyast.Constant) for e in n.elts)]
    assert len(tuples) == 1
    return tuple(e.value for e in tuples[0].elts)


def test_call_filter_is_the_regex_one():
    assert java_ast.REGEX_CALL_FILTER == _regex_filter_tuple()


@pytest.mark.parametrize("receiver", list(java_ast.REGEX_CALL_FILTER) + ["other", "Thread", "self2"])
def test_call_filter_behaviour(receiver):
    # Both parsers drop exactly the same receiver names (a parameter of that name, so it is a call
    # on an identifier; `this` / `super` are keywords and need no parameter).
    param = "" if receiver in ("this", "super") else f"String {receiver}"
    content = (f"public class Foo {{\n    public void run({param}) {{\n"
               f"        {receiver}.trim();\n    }}\n}}\n")
    regex = Context_gen.analyze_java_file(content, "Foo.java")["methods"]["run"]["calls"]
    ast = java_ast.analyze_java_file_ast(content, "Foo.java")["methods"]["run"]["calls"]
    assert ast == regex
    assert ast == ([] if receiver in java_ast.REGEX_CALL_FILTER else [f"{receiver}.trim"])


@pytest.mark.parametrize("call, expected", [
    ("super.x.foo();", ["x.foo"]),            # field of super: the field name
    ("a.b.c.foo();", ["c.foo"]),
    ("Outer.this.foo();", []),                # `this` as the last part: filtered
    ("new a.b.C().foo();", ["b.C"]),          # the qualified `new`, not the call on it
    ("x.foo().bar();", ["x.foo"]),            # chain: only the first call
    ("x.foo(y.bar());", ["x.foo", "y.bar"]),  # call in the arguments
    ("x.foo\n(1);", []),                      # line break before `(`
])
def test_receiver_forms_inline(call, expected):
    content = f"public class Foo {{\n    public void run() {{\n        {call}\n    }}\n}}\n"
    regex = Context_gen.analyze_java_file(content, "Foo.java")["methods"]["run"]["calls"]
    ast = java_ast.analyze_java_file_ast(content, "Foo.java")["methods"]["run"]["calls"]
    assert ast == expected
    assert ast == regex


def test_non_ascii_body():
    # Byte offsets of tree-sitter vs characters: a non-ASCII string or comment before the calls.
    content = ("public class Foo {\n    public void run(StringBuilder sb) {\n"
               "        // Größe\n        sb.append(\"Größe\");\n        sb.reverse();\n    }\n}\n")
    regex = Context_gen.analyze_java_file(content, "Foo.java")["methods"]["run"]["calls"]
    ast = java_ast.analyze_java_file_ast(content, "Foo.java")["methods"]["run"]["calls"]
    assert ast == regex == ["sb.append", "sb.reverse"]
