import copy
import json
import sys

import pytest

import compare_contexts as cc


def context_module():
    """A small module in the Context JSON format produced by Context_gen.py."""
    return {
        "module": "Foo",
        "package": "game.foo",
        "type": "class",
        "parent": "Base",
        "implements": ["Runnable", "Serializable"],
        "fields": {"x": "int", "name (from Base)": "String"},
        "constants": {"MAX": {"type": "int", "value": "10"}},
        "assets": ["a.png", "b.png"],
        "methods": {
            "Foo_constructor_0": {
                "abstract": False, "modifiers": ["public"], "return_type": "",
                "params": [], "signature": "public Foo()", "javadoc": "",
                "calls": [], "logic_hints": [], "values_hint": [],
            },
            "run": {
                "abstract": False, "modifiers": ["public"], "return_type": "void",
                "params": ["int a", "String b"], "signature": "public void run(int a, String b)",
                "javadoc": "Runs.", "calls": ["x.foo", "y.bar"],
                "logic_hints": ["this.x = a"], "values_hint": ["100", "200"],
            },
        },
    }


def ctx():
    return {"Foo": context_module(), "Bar": {**context_module(), "module": "Bar"}}


def diffs_of(old, new):
    return [(d.category, d.kind, d.where) for d in cc.compare_contexts(old, new)]


# ---------------------------------------------------------------- compare_contexts

def test_identical_objects_have_no_diffs():
    assert cc.compare_contexts(ctx(), ctx()) == []


def test_module_removed_and_added():
    old, new = ctx(), ctx()
    del new["Bar"]
    new["Baz"] = context_module()
    assert diffs_of(old, new) == [
        (cc.MODULE_CATEGORY, "removed", "Bar"),
        (cc.MODULE_CATEGORY, "added", "Baz"),
    ]


def test_method_removed():
    old, new = ctx(), ctx()
    del new["Foo"]["methods"]["run"]
    d = cc.compare_contexts(old, new)
    assert [(x.category, x.kind, x.where) for x in d] == [
        ("methods[*]", "removed", "Foo.methods[run]")]
    assert d[0].n_removed == 1


def test_scalar_change_in_method():
    old, new = ctx(), ctx()
    new["Foo"]["methods"]["run"]["return_type"] = "int"
    d = cc.compare_contexts(old, new)
    assert [(x.category, x.kind, x.where) for x in d] == [
        ("methods[*].return_type", "changed", "Foo.methods[run].return_type")]
    assert d[0].detail == '"void" -> "int"'


def test_list_order_only_is_not_a_content_diff():
    old, new = ctx(), ctx()
    new["Foo"]["methods"]["run"]["calls"] = ["y.bar", "x.foo"]
    new["Foo"]["assets"] = ["b.png", "a.png"]
    assert diffs_of(old, new) == [
        ("assets", "order", "Foo.assets"),
        ("methods[*].calls", "order", "Foo.methods[run].calls"),
    ]


def test_list_items_differ_counts_added_and_removed():
    old, new = ctx(), ctx()
    new["Foo"]["methods"]["run"]["calls"] = ["x.foo", "z.baz", "w.qux"]
    (d,) = cc.compare_contexts(old, new)
    assert (d.category, d.kind) == ("methods[*].calls", "items")
    assert (d.n_removed, d.n_added) == (1, 2)
    assert d.detail == '- ["y.bar"] + ["w.qux", "z.baz"]'


def test_list_duplicates_are_counted_as_multiset():
    old, new = ctx(), ctx()
    new["Foo"]["methods"]["run"]["calls"] = ["x.foo", "y.bar", "y.bar"]
    (d,) = cc.compare_contexts(old, new)
    assert (d.kind, d.n_removed, d.n_added) == ("items", 0, 1)


def test_values_hint_different_set_is_items_not_order():
    old, new = ctx(), ctx()
    new["Foo"]["methods"]["run"]["values_hint"] = ["100", "300"]
    assert diffs_of(old, new) == [
        ("methods[*].values_hint", "items", "Foo.methods[run].values_hint")]


def test_params_are_ordered():
    old, new = ctx(), ctx()
    new["Foo"]["methods"]["run"]["params"] = ["String b", "int a"]
    assert diffs_of(old, new) == [
        ("methods[*].params", "changed", "Foo.methods[run].params")]


def test_record_missing_and_extra_keys():
    old, new = ctx(), ctx()
    del new["Foo"]["methods"]["run"]["javadoc"]
    new["Foo"]["methods"]["run"]["called_by"] = []
    (d,) = cc.compare_contexts(old, new)
    assert (d.category, d.kind, d.where) == ("methods[*]", "keys", "Foo.methods[run]")
    assert d.detail == "missing ['javadoc']; extra ['called_by']"


def test_record_key_order():
    old, new = ctx(), ctx()
    m = new["Foo"]
    new["Foo"] = {"package": m["package"], **{k: v for k, v in m.items() if k != "package"}}
    assert diffs_of(old, new) == [(cc.MODULE_CATEGORY, "key_order", "Foo")]


def test_entity_order_in_map():
    old, new = ctx(), ctx()
    new["Foo"]["methods"] = dict(reversed(list(new["Foo"]["methods"].items())))
    assert diffs_of(old, new) == [("methods[*]", "key_order", "Foo.methods")]


def test_top_level_module_order():
    old = ctx()
    new = dict(reversed(list(ctx().items())))
    assert diffs_of(old, new) == [(cc.MODULE_CATEGORY, "key_order", "(top level)")]


def test_type_change():
    old, new = ctx(), ctx()
    new["Foo"]["parent"] = None
    (d,) = cc.compare_contexts(old, new)
    assert (d.category, d.kind) == ("parent", "type")
    assert d.detail.startswith("str -> null")


def test_fields_and_constants_are_entity_maps():
    old, new = ctx(), ctx()
    new["Foo"]["fields"]["x"] = "long"
    new["Foo"]["fields"]["y"] = "int"
    new["Foo"]["constants"]["MAX"]["value"] = "20"
    assert diffs_of(old, new) == [
        ("fields[*]", "added", "Foo.fields[y]"),
        ("fields[*]", "changed", "Foo.fields[x]"),
        ("constants[*].value", "changed", "Foo.constants[MAX].value"),
    ]


def test_inherited_suffix_is_part_of_the_name():
    old, new = ctx(), ctx()
    f = new["Foo"]["fields"]
    f["name (from Other)"] = f.pop("name (from Base)")
    assert diffs_of(old, new) == [
        ("fields[*]", "removed", "Foo.fields[name (from Base)]"),
        ("fields[*]", "added", "Foo.fields[name (from Other)]"),
    ]


def test_functional_and_behavioral_maps():
    old = {"Foo": {"roles": ["ui"], "capabilities": {"run": {"signature": "s", "intent": "", "abstract": False}}}}
    new = copy.deepcopy(old)
    new["Foo"]["capabilities"]["run"]["abstract"] = True
    assert diffs_of(old, new) == [
        ("capabilities[*].abstract", "changed", "Foo.capabilities[run].abstract")]

    old = {"Foo": {"methods_execution": {"run": {"calls": ["a.b"], "logic_hints": [], "values_hint": []}}}}
    new = copy.deepcopy(old)
    new["Foo"]["methods_execution"]["stop"] = {"calls": [], "logic_hints": [], "values_hint": []}
    assert diffs_of(old, new) == [
        ("methods_execution[*]", "added", "Foo.methods_execution[stop]")]


def test_top_level_must_be_object():
    with pytest.raises(ValueError):
        cc.compare_contexts([], {})


def test_count_methods():
    assert cc.count_methods(ctx()) == 4
    structural = {"Foo": {"module": "Foo", "method_signatures": ["void a()", "void b()"]}}
    assert cc.count_methods(structural) == 2


# ---------------------------------------------------------------- tokens

def test_count_tokens_cl100k():
    assert cc.count_tokens("hello world") == 2


def test_missing_tiktoken_is_an_explicit_error(monkeypatch):
    monkeypatch.setattr(cc, "_ENCODER", None)
    monkeypatch.setitem(sys.modules, "tiktoken", None)  # makes `import tiktoken` fail
    with pytest.raises(SystemExit) as e:
        cc.count_tokens("x")
    assert "tiktoken is not installed" in str(e.value)


# ---------------------------------------------------------------- directories + report

def write_json(path, obj):
    path.write_text(json.dumps(obj, indent=2), encoding="utf-8")


def test_compare_dirs_pairs_by_name(tmp_path):
    old_dir, new_dir = tmp_path / "old", tmp_path / "new"
    old_dir.mkdir(), new_dir.mkdir()
    write_json(old_dir / "G_Context.json", ctx())
    write_json(new_dir / "G_Context.json", ctx())
    write_json(old_dir / "G_Structural.json", {})
    write_json(new_dir / "H_Structural.json", {})
    (new_dir / "notes.txt").write_text("ignored", encoding="utf-8")

    results, only_old, only_new = cc.compare_dirs(str(old_dir), str(new_dir))
    assert [r.name for r in results] == ["G_Context.json"]
    assert only_old == ["G_Structural.json"] and only_new == ["H_Structural.json"]
    r = results[0]
    assert r.identical_bytes and r.diffs == []
    assert r.modules == (2, 2) and r.methods == (4, 4)
    text = (old_dir / "G_Context.json").read_text(encoding="utf-8")
    assert r.tokens == (cc.count_tokens(text), cc.count_tokens(text))


def test_same_content_different_bytes(tmp_path):
    old_dir, new_dir = tmp_path / "old", tmp_path / "new"
    old_dir.mkdir(), new_dir.mkdir()
    write_json(old_dir / "G_Context.json", ctx())
    (new_dir / "G_Context.json").write_text(json.dumps(ctx()), encoding="utf-8")  # no indent
    (r,), _, _ = cc.compare_dirs(str(old_dir), str(new_dir))
    assert not r.identical_bytes and r.diffs == []
    assert r.tokens[0] != r.tokens[1]


def test_crlf_and_lf_files_have_equal_tokens_and_no_diffs(tmp_path):
    old_dir, new_dir = tmp_path / "old", tmp_path / "new"
    old_dir.mkdir(), new_dir.mkdir()
    text = json.dumps(ctx(), indent=2)
    (old_dir / "G_Context.json").write_bytes(text.replace("\n", "\r\n").encode("utf-8"))
    (new_dir / "G_Context.json").write_bytes(text.encode("utf-8"))
    (r,), _, _ = cc.compare_dirs(str(old_dir), str(new_dir))
    assert not r.identical_bytes  # raw bytes differ ...
    assert r.diffs == []  # ... content does not
    assert r.tokens[0] == r.tokens[1] == cc.count_tokens(text)  # tokens are counted on LF text


def test_report_no_differences(tmp_path):
    d = tmp_path / "d"
    d.mkdir()
    write_json(d / "G_Context.json", ctx())
    results, only_old, only_new = cc.compare_dirs(str(d), str(d))
    report = cc.render_report("a", "b", results, only_old, only_new)
    assert "**Result: no differences**" in report
    assert "| G_Context.json | yes | 2 → 2 | 4 → 4 | 0 | 0 | 0 |" in report
    assert "**all Context**" in report


def test_report_lists_categories_and_caps_examples(tmp_path):
    old_dir, new_dir = tmp_path / "old", tmp_path / "new"
    old_dir.mkdir(), new_dir.mkdir()
    old, new = ctx(), ctx()
    for name in ("Foo", "Bar"):
        new[name]["methods"]["run"]["calls"] = ["x.foo", "z.baz"]
    write_json(old_dir / "G_Context.json", old)
    write_json(new_dir / "G_Context.json", new)
    results, only_old, only_new = cc.compare_dirs(str(old_dir), str(new_dir))
    report = cc.render_report("a", "b", results, only_old, only_new, max_examples=1)
    assert "**Result: 2 difference(s)** in 1 of 1 paired file(s)." in report
    assert "| `methods[*].calls` | list items differ | 2 | 2 | 2 |" in report
    assert "(1 of 2 shown)" in report
    assert '- `Foo.methods[run].calls`: - ["y.bar"] + ["z.baz"]' in report  # Foo first: old file order
    assert "Bar.methods[run].calls" not in report  # capped at 1 example


def test_cli_writes_report(tmp_path, capsys):
    d = tmp_path / "d"
    d.mkdir()
    write_json(d / "G_Context.json", ctx())
    out = tmp_path / "report.md"
    assert cc.main([str(d), str(d), "--out", str(out)]) == 0
    assert "**Result: no differences**" in out.read_text(encoding="utf-8")
    assert "Report written to" in capsys.readouterr().out


def test_cli_rejects_missing_directory(tmp_path):
    with pytest.raises(SystemExit) as e:
        cc.main([str(tmp_path / "nope"), str(tmp_path)])
    assert e.value.code == 2


def test_invalid_json_is_an_explicit_error(tmp_path):
    old_dir, new_dir = tmp_path / "old", tmp_path / "new"
    old_dir.mkdir(), new_dir.mkdir()
    (old_dir / "G_Context.json").write_text("{broken", encoding="utf-8")
    write_json(new_dir / "G_Context.json", {})
    with pytest.raises(SystemExit) as e:
        cc.compare_dirs(str(old_dir), str(new_dir))
    assert "cannot parse" in str(e.value)
