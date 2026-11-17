"""Tree-sitter based Java parser: drop-in replacement for Context_gen.analyze_java_file.

analyze_java_file_ast(content, filename) returns the same dict (same keys, same key order,
same value types) as the regex parser, so the rest of Context_gen (flatten_inheritance,
split_contexts, subtypes, combine, slice) works unchanged.

Stage A of the migration: reproduce the regex rules, except for documented regex bugs
(see the test list KNOWN_DEVIATIONS in tests/test_java_ast.py).

Filled so far:
    A1  module, package, type, parent, implements
To do:
    A2  fields, constants, assets
    A3  methods and constructors (signatures, javadoc)
    A4  calls
    A5  logic_hints, values_hint

Parse errors: tree-sitter always returns a tree, even for broken code. If the tree has errors,
analyze_java_file_ast issues a JavaParseWarning (file name, line:column of each error). An error
inside the header of the main type (before its body) makes the header unreliable, so the file is
skipped (None), as the regex parser does when it cannot match a class. An error elsewhere (e.g. in
a method body) keeps the result. Strict mode: warnings.simplefilter("error", JavaParseWarning).
"""
import re
import warnings

import tree_sitter_java as tsj
from tree_sitter import Language, Parser

JAVA = Language(tsj.language())
_PARSER = Parser(JAVA)

# Top-level declarations the regex parser recognises (CLASS_PAT: class|interface|enum).
TYPE_DECLS = ("class_declaration", "interface_declaration", "enum_declaration")
TYPE_KEYWORDS = {
    "class_declaration": "class",
    "interface_declaration": "interface",
    "enum_declaration": "enum",
}

# Comments are "extras" in tree-sitter: they can appear between any two tokens, also inside
# type lists and qualified names.
COMMENT_TYPES = ("line_comment", "block_comment")
# Cut out of a type name: type arguments, comments, annotations (`@NonNull Bar` -> `Bar`).
_SKIPPED_IN_NAMES = ("type_arguments", "marker_annotation", "annotation") + COMMENT_TYPES

_WS = re.compile(r"\s+")

# How many error positions a warning lists before "...".
_MAX_LISTED_ERRORS = 5


class JavaParseWarning(UserWarning):
    """tree-sitter found syntax errors in a Java file."""


# --- helpers -----------------------------------------------------------------

def parse(content):
    """Parse Java source text. Returns (tree, src_bytes); node offsets are byte offsets in src."""
    src = content.encode("utf-8")
    return _PARSER.parse(src), src


def node_text(node, src):
    return src[node.start_byte:node.end_byte].decode("utf-8")


def type_name(node, src):
    """Type or package name without type arguments, comments, annotations and whitespace:
    `Base<String>` -> `Base`, `javax.swing.JPanel` -> `javax.swing.JPanel`,
    `Outer<A>.Inner` -> `Outer.Inner`, `@NonNull Bar` -> `Bar`, `a. /* x */ b` -> `a.b`."""
    parts = []
    pos = node.start_byte
    for start, end in _skipped_spans(node):
        parts.append(src[pos:start])
        pos = end
    parts.append(src[pos:node.end_byte])
    return _WS.sub("", b"".join(parts).decode("utf-8"))


def _skipped_spans(node):
    """Byte spans of the outermost nodes inside `node` that are not part of a name
    (_SKIPPED_IN_NAMES), in source order."""
    spans = []
    stack = [node]
    while stack:
        cur = stack.pop()
        if cur.type in _SKIPPED_IN_NAMES:
            spans.append((cur.start_byte, cur.end_byte))
            continue
        stack.extend(cur.children)
    return sorted(spans)


def _non_comment_children(node):
    return [c for c in node.named_children if c.type not in COMMENT_TYPES]


def parse_errors(root):
    """Syntax errors in the tree: list of (node, kind), kind "ERROR" (unexpected text) or
    "MISSING" (token inserted by the parser), in source order. ERROR nodes are not descended."""
    errors = []
    stack = [root]
    while stack:
        cur = stack.pop()
        if cur.is_error:
            errors.append((cur, "ERROR"))
            continue
        if cur.is_missing:
            errors.append((cur, "MISSING"))
            continue
        if cur.has_error:
            stack.extend(cur.children)
    return sorted(errors, key=lambda e: e[0].start_byte)


def _header_has_error(type_node, errors):
    """True if an error lies inside the header of `type_node` (from its start to its body)."""
    body = type_node.child_by_field_name("body")
    header_end = type_node.end_byte if body is None or body.is_missing else body.start_byte
    return any(type_node.start_byte <= node.start_byte < header_end for node, _ in errors)


def _warn_parse_errors(filename, errors, skipped):
    listed = ", ".join(f"{kind} at {node.start_point[0] + 1}:{node.start_point[1] + 1}"
                       for node, kind in errors[:_MAX_LISTED_ERRORS])
    more = ", ..." if len(errors) > _MAX_LISTED_ERRORS else ""
    tail = "; error in the class header, file skipped" if skipped else ""
    warnings.warn(f"{filename}: {len(errors)} parse error(s) ({listed}{more}){tail}",
                  JavaParseWarning, stacklevel=3)


# --- A1: class header ----------------------------------------------------------

def extract_package(root, src):
    """Package name, "" if there is no package declaration (as regex)."""
    for child in root.named_children:
        if child.type == "package_declaration":
            for sub in child.named_children:
                if sub.type in ("scoped_identifier", "identifier"):
                    return type_name(sub, src)  # drops comments inside `a. /* x */ b`
    return ""


def find_main_type(root):
    """First top-level class/interface/enum declaration, or None.

    Unlike regex (first `class|interface|enum Name` match anywhere in the text), comments,
    nested types and later top-level types are never picked up.
    """
    for child in root.named_children:
        if child.type in TYPE_DECLS:
            return child
    return None


def _modifier_keywords(type_node):
    for child in type_node.children:
        if child.type == "modifiers":
            return {m.type for m in child.children}
    return set()


def extract_type_kind(type_node):
    """"class" | "abstract class" | "abstract interface" | "enum" (as regex: an interface is
    always reported as abstract)."""
    kw = TYPE_KEYWORDS[type_node.type]
    if kw == "interface" or "abstract" in _modifier_keywords(type_node):
        return f"abstract {kw}"
    return kw


def _type_list(node):
    """Types of a super_interfaces / extends_interfaces node (children of its type_list),
    without the comments between them."""
    for child in node.named_children:
        if child.type == "type_list":
            return _non_comment_children(child)
    return []


def extract_parent(type_node, src):
    """Superclass name without type arguments, or None.

    Interface `extends Bar, Baz` -> "Bar" (regex compatibility, decision 9: the other
    super-interfaces are lost; to be revisited in stage B).
    """
    superclass = type_node.child_by_field_name("superclass")
    if superclass is not None:
        types = _non_comment_children(superclass)  # `extends /* base */ Bar`
        if types:
            return type_name(types[0], src)
    for child in type_node.children:
        if child.type == "extends_interfaces":
            types = _type_list(child)
            if types:
                return type_name(types[0], src)
    return None


def extract_implements(type_node, src):
    """Implemented interface names without type arguments (decision 10), [] if none."""
    interfaces = type_node.child_by_field_name("interfaces")
    if interfaces is None:
        return []
    return [type_name(t, src) for t in _type_list(interfaces)]


# --- entry point -----------------------------------------------------------------

def analyze_java_file_ast(content, filename):
    """Same contract as Context_gen.analyze_java_file: dict for the main type, or None.

    `filename` is only used in parse warnings (the regex version ignores it).
    On syntax errors issues a JavaParseWarning; returns None if an error is in the header of
    the main type (see the module docstring).
    """
    tree, src = parse(content)
    root = tree.root_node
    type_node = find_main_type(root)
    if root.has_error:
        errors = parse_errors(root)
        skipped = type_node is not None and _header_has_error(type_node, errors)
        _warn_parse_errors(filename, errors, skipped)
        if skipped:
            return None
    if type_node is None:
        return None

    name = type_node.child_by_field_name("name")
    return {
        "module":     node_text(name, src),
        "package":    extract_package(root, src),
        "type":       extract_type_kind(type_node),
        "parent":     extract_parent(type_node, src),
        "implements": extract_implements(type_node, src),
        "fields":     {},   # A2
        "constants":  {},   # A2
        "assets":     [],   # A2
        "methods":    {},   # A3-A5
    }
