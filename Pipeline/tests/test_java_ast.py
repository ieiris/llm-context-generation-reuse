"""Tests for Pipeline/java_ast.py (tree-sitter parser), stage A1: class header.

Three kinds of checks:
1. EXPECTED: the five A1 fields for every sample, written by hand.
2. Regex comparison: AST must equal Context_gen.analyze_java_file on every sample, except the
   intentional fixes listed in KNOWN_DEVIATIONS (where the regex output is pinned too).
   Any other difference fails the test.
3. Shape: same keys, same key order and same value types as the regex dict.
"""
import os

import pytest

import Context_gen
import java_ast

SAMPLES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "java_samples", "a1")
A1_FIELDS = ("module", "package", "type", "parent", "implements")


def _header(module, package, type_, parent, implements):
    return {"module": module, "package": package, "type": type_,
            "parent": parent, "implements": implements}


# Expected AST output (A1 fields only). None = file has no top-level type.
EXPECTED = {
    "SimpleClass.java":          _header("SimpleClass", "org.example.game", "class", None, []),
    "NoPackage.java":            _header("NoPackage", "", "class", None, []),
    "AbstractChild.java":        _header("AbstractChild", "org.example.game", "abstract class",
                                         "Base", ["Runnable", "KeyListener"]),
    "AbstractPublicOrder.java":  _header("AbstractPublicOrder", "org.example.game", "abstract class",
                                         "Base", []),
    "Shape.java":                _header("Shape", "org.example.geom", "abstract interface", None, []),
    # Decision 9: interface `extends Shape, Comparable<...>` -> parent = first one (regex compatibility).
    "ExtendingInterface.java":   _header("ExtendingInterface", "org.example.geom", "abstract interface",
                                         "Shape", []),
    "Color.java":                _header("Color", "org.example.ui", "enum", None, ["Runnable"]),
    "MultilineImplements.java":  _header("MultilineImplements", "org.example.ui", "abstract class",
                                         "JComponent", ["MouseListener", "KeyListener"]),
    "QualifiedParent.java":      _header("QualifiedParent", "org.example.ui", "class",
                                         "javax.swing.JPanel", ["java.io.Serializable"]),
    # Decision 10: type arguments are dropped in parent and implements.
    "GenericParent.java":        _header("GenericParent", "org.example.util", "class",
                                         "ArrayList", ["Comparable"]),
    "GenericBound.java":         _header("GenericBound", "org.example.util", "class", "Base", []),
    "CommentMentionsClass.java": _header("CommentMentionsClass", "org.example.game", "class", "Base", []),
    "NestedClass.java":          _header("NestedClass", "org.example.game", "class", None, []),
    "TwoTopLevel.java":          _header("TwoTopLevel", "org.example.game", "class", None, []),
    "OneLetter.java":            _header("A", "org.example.game", "class", "Base", []),
    "Annotated.java":            _header("Annotated", "org.example.ui", "class", "JPanel", []),
    "NoType.java":               None,
    "Broken.java":               _header("Broken", "org.example.game", "class", "Base", ["Runnable"]),
}

# Intentional fixes of regex bugs: the only samples where AST may differ from regex.
# "regex" pins what the regex parser returns today (A1 fields, or None), so a change in regex
# behaviour is noticed too. Keep in sync with .andrei/results/compat_report.md.
KNOWN_DEVIATIONS = {
    "AbstractPublicOrder.java": {
        "regex": _header("AbstractPublicOrder", "org.example.game", "class", "Base", []),
        "reason": "CLASS_PAT keeps only the last modifier, so `abstract public` loses `abstract`",
    },
    "GenericParent.java": {
        "regex": _header("GenericParent", "org.example.util", "class", "ArrayList", []),
        "reason": "IMPLEMENTS_PAT cannot pass `<`, so `implements Comparable<...>` gives []",
    },
    "GenericBound.java": {
        "regex": _header("GenericBound", "org.example.util", "class", "Comparable", []),
        "reason": "EXTENDS_PAT takes the first `extends` in the file: the type parameter bound",
    },
    "CommentMentionsClass.java": {
        "regex": _header("Helper", "org.example.game", "class", "nothing", []),
        "reason": "CLASS_PAT and EXTENDS_PAT match words inside the javadoc",
    },
    "NestedClass.java": {
        "regex": _header("NestedClass", "org.example.game", "class", "Thread", ["Runnable"]),
        "reason": "EXTENDS_PAT / IMPLEMENTS_PAT match the nested class header",
    },
    "TwoTopLevel.java": {
        "regex": _header("TwoTopLevel", "org.example.game", "class", "Base", ["Runnable"]),
        "reason": "EXTENDS_PAT / IMPLEMENTS_PAT match the second top-level type",
    },
    "OneLetter.java": {
        "regex": None,
        "reason": "CLASS_PAT requires a name of 2+ chars starting with A-Z, so the file is dropped",
    },
}


def _read(name):
    with open(os.path.join(SAMPLES_DIR, name), encoding="utf-8") as f:
        return f.read()


def _a1(result):
    return None if result is None else {k: result[k] for k in A1_FIELDS}


def test_every_sample_has_expectation():
    assert sorted(os.listdir(SAMPLES_DIR)) == sorted(EXPECTED)
    assert set(KNOWN_DEVIATIONS) <= set(EXPECTED)


@pytest.mark.parametrize("name", sorted(EXPECTED))
def test_expected_header(name):
    assert _a1(java_ast.analyze_java_file_ast(_read(name), name)) == EXPECTED[name]


@pytest.mark.parametrize("name", sorted(EXPECTED))
def test_matches_regex_except_known_deviations(name):
    content = _read(name)
    regex = _a1(Context_gen.analyze_java_file(content, name))
    ast = _a1(java_ast.analyze_java_file_ast(content, name))
    if name in KNOWN_DEVIATIONS:
        assert regex == KNOWN_DEVIATIONS[name]["regex"], "regex behaviour changed"
        assert ast != regex
    else:
        assert ast == regex


@pytest.mark.parametrize("name", sorted(n for n, e in EXPECTED.items() if e is not None))
def test_dict_shape(name):
    content = _read(name)
    ast = java_ast.analyze_java_file_ast(content, name)
    regex = Context_gen.analyze_java_file(content, name)
    if regex is not None:
        assert list(ast) == list(regex)  # same keys, same order (order goes into the JSON)
    assert list(ast) == ["module", "package", "type", "parent", "implements",
                         "fields", "constants", "assets", "methods"]
    assert isinstance(ast["module"], str) and ast["module"]
    assert isinstance(ast["package"], str)
    assert isinstance(ast["type"], str)
    assert ast["parent"] is None or isinstance(ast["parent"], str)
    assert isinstance(ast["implements"], list)
    assert all(isinstance(i, str) for i in ast["implements"])
    # Not filled until A2-A5, but already of the regex types.
    assert ast["fields"] == {} and ast["constants"] == {}
    assert ast["assets"] == [] and ast["methods"] == {}


def test_empty_source_returns_none():
    assert java_ast.analyze_java_file_ast("", "Empty.java") is None


def test_non_ascii_before_declaration():
    # Node offsets are bytes; text before the class must not shift the extracted names.
    content = "// Комментарий: ünïcödé\npackage a.b;\npublic class Foo extends Bar implements Baz {}\n"
    assert _a1(java_ast.analyze_java_file_ast(content, "Foo.java")) == _header(
        "Foo", "a.b", "class", "Bar", ["Baz"])


@pytest.mark.parametrize("decl, expected", [
    ("class X extends Map<String, List<Integer>> {}", "Map"),
    ("class X extends Outer<A>.Inner<B> {}", "Outer.Inner"),
    ("class X extends a.b.C<D> {}", "a.b.C"),
])
def test_type_arguments_are_dropped(decl, expected):
    assert java_ast.analyze_java_file_ast(decl, "X.java")["parent"] == expected
