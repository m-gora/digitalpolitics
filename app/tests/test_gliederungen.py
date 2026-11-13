"""Tests for the Gliederung config registry (dpp.gliederungen)."""

import pytest

import dpp.gliederungen as g


@pytest.fixture()
def registry(tmp_path):
    config = tmp_path / "gliederungen.yaml"
    config.write_text(
        """
gliederungen:
  - slug: lv-berlin
    name: LV Berlin
  - slug: bv-friedrichshain-kreuzberg
    name: BV Friedrichshain-Kreuzberg
    parent: lv-berlin
  - slug: bv-mitte
    name: BV Mitte
    parent: lv-berlin
  - slug: ov-kreuzberg
    name: OV Kreuzberg
    parent: bv-friedrichshain-kreuzberg
"""
    )
    return g.load_file(config)


def test_load_and_lookup(registry):
    assert registry.exists("lv-berlin")
    assert not registry.exists("lv-hamburg")
    assert registry.name("ov-kreuzberg") == "OV Kreuzberg"
    assert registry.parent("ov-kreuzberg") == "bv-friedrichshain-kreuzberg"


def test_expand_inherits_descendants(registry):
    assert registry.expand("lv-berlin") == frozenset(
        {"lv-berlin", "bv-friedrichshain-kreuzberg", "bv-mitte", "ov-kreuzberg"}
    )
    assert registry.expand("ov-kreuzberg") == frozenset({"ov-kreuzberg"})


def test_ordered_is_depth_first(registry):
    assert [(slug, depth) for slug, _, depth in registry.ordered()] == [
        ("lv-berlin", 0),
        ("bv-friedrichshain-kreuzberg", 1),
        ("ov-kreuzberg", 2),
        ("bv-mitte", 1),
    ]


def test_names_for_search_is_lowercased(registry):
    assert registry.names_for_search()["bv-mitte"] == "bv mitte"


def test_rejects_unknown_parent(tmp_path):
    config = tmp_path / "bad.yaml"
    config.write_text("gliederungen:\n  - slug: a\n    name: A\n    parent: missing\n")
    with pytest.raises(g.GliederungConfigError, match="unknown parent"):
        g.load_file(config)


def test_rejects_duplicate_slug(tmp_path):
    config = tmp_path / "bad.yaml"
    config.write_text("gliederungen:\n  - slug: a\n    name: A\n  - slug: a\n    name: A2\n")
    with pytest.raises(g.GliederungConfigError, match="duplicate slug"):
        g.load_file(config)


def test_rejects_cycle(tmp_path):
    config = tmp_path / "bad.yaml"
    config.write_text(
        "gliederungen:\n"
        "  - slug: a\n    name: A\n    parent: b\n"
        "  - slug: b\n    name: B\n    parent: a\n"
    )
    with pytest.raises(g.GliederungConfigError, match="cycle"):
        g.load_file(config)


def test_expand_module_function(registry, monkeypatch):
    # Point the module-level helpers at the fixture registry.
    monkeypatch.setattr(g, "get_registry", lambda: registry)
    assert g.expand("all") == registry.all_slugs()
    assert g.expand("bv-mitte") == frozenset({"bv-mitte"})
    assert g.expand("unknown-group") == frozenset()
    assert g.expand("") == frozenset()
