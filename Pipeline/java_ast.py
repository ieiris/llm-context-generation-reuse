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
"""
import re

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

_WS = re.compile(r"\s+")


# --- helpers -----------------------------------------------------------------

def parse(content):
    """Parse Java source text. Returns (tree, src_bytes); node offsets are byte offsets in src."""
    src = content.encode("utf-8")
    return _PARSER.parse(src), src


def node_text(node, src):
    return src[node.start_byte:node.end_byte].decode("utf-8")


def type_name(node, src):
    """Type name without type arguments and whitespace: `Base<String>` -> `Base`,
    `javax.swing.JPanel` -> `javax.swing.JPanel`, `Outer<A>.Inner` -> `Outer.Inner`."""
    parts = []
    pos = node.start_byte
    for start, end in _type_argument_spans(node):
        parts.append(src[pos:start])
        pos = end
    parts.append(src[pos:node.end_byte])
    return _WS.sub("", b"".join(parts).decode("utf-8"))


def _type_argument_spans(node):
    """Byte spans of the outermost type_arguments nodes inside `node`, in source order."""
    spans = []
    stack = [node]
    while stack:
        cur = stack.pop()
        if cur.type == "type_arguments":
            spans.append((cur.start_byte, cur.end_byte))
            continue
        stack.extend(cur.children)
    return sorted(spans)


# --- A1: class header ----------------------------------------------------------

def extract_package(root, src):
    """Package name, "" if there is no package declaration (as regex)."""
    for child in root.named_children:
        if child.type == "package_declaration":
            for sub in child.named_children:
                if sub.type in ("scoped_identifier", "identifier"):
                    return _WS.sub("", node_text(sub, src))
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
    """Types of a super_interfaces / extends_interfaces node (children of its type_list)."""
    for child in node.named_children:
        if child.type == "type_list":
            return child.named_children
    return []


def extract_parent(type_node, src):
    """Superclass name without type arguments, or None.

    Interface `extends Bar, Baz` -> "Bar" (regex compatibility, decision 9: the other
    super-interfaces are lost; to be revisited in stage B).
    """
    superclass = type_node.child_by_field_name("superclass")
    if superclass is not None:
        return type_name(superclass.named_children[0], src)
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

    `filename` is unused (as in the regex version); kept so the two are interchangeable.
    """
    tree, src = parse(content)
    root = tree.root_node
    type_node = find_main_type(root)
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
