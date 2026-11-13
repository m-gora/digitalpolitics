"""Gliederung registry: the party unit hierarchy as deployment configuration.

The Gliederung tree changes rarely and is not user-editable application
data, so it ships as a YAML file (injected via ConfigMap, path from
DPP_GLIEDERUNGEN_FILE) and is the single source of truth for district
slugs, display names, and hierarchy. The database does not store
districts: campaigns and initiatives reference district slugs as plain
strings, and the write-time scope check (which is built from this
registry) keeps invalid slugs out of the database. See arch-02/adr-03.

File format:

    gliederungen:
      - slug: lv-berlin
        name: LV Berlin
      - slug: bv-friedrichshain-kreuzberg
        name: BV Friedrichshain-Kreuzberg
        parent: lv-berlin
"""

import os
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

import yaml


class GliederungConfigError(Exception):
    """Raised for a malformed or inconsistent Gliederung config file."""


DEFAULT_CONFIG_PATH = "config/gliederungen.yaml"


@dataclass(frozen=True)
class Gliederung:
    slug: str
    name: str
    parent_slug: str | None


@dataclass(frozen=True)
class Registry:
    """Immutable in-memory view of the Gliederung config file."""

    by_slug: dict[str, Gliederung] = field(default_factory=dict)

    def _require(self, slug: str) -> Gliederung:
        entry = self.by_slug.get(slug)
        if entry is None:
            raise KeyError(f"Unknown Gliederung slug: {slug!r}")
        return entry

    def exists(self, slug: str) -> bool:
        return slug in self.by_slug

    def name(self, slug: str) -> str:
        return self._require(slug).name

    def parent(self, slug: str) -> str | None:
        return self._require(slug).parent_slug

    def children(self, slug: str) -> list[str]:
        return [child.slug for child in self.by_slug.values() if child.parent_slug == slug]

    def roots(self) -> list[str]:
        return [entry.slug for entry in self.by_slug.values() if entry.parent_slug is None]

    def expand(self, slug: str) -> frozenset[str]:
        """The slug itself plus all descendants — the arch-02 inheritance rule
        ("access to a district implies access to everything beneath it"),
        computed from the config instead of the database."""
        expanded = {slug}
        frontier = [slug]
        while frontier:
            current = frontier.pop()
            for child in self.children(current):
                if child not in expanded:
                    expanded.add(child)
                    frontier.append(child)
        return frozenset(expanded)

    def all_slugs(self) -> frozenset[str]:
        return frozenset(self.by_slug)

    def ordered(self) -> list[tuple[str, str, int]]:
        """Depth-first (slug, name, depth) order for dropdowns and tree views."""
        result: list[tuple[str, str, int]] = []

        def visit(slug: str, depth: int) -> None:
            entry = self._require(slug)
            result.append((entry.slug, entry.name, depth))
            for child in self.children(slug):
                visit(child, depth + 1)

        for root in self.roots():
            visit(root, 0)
        return result

    def names_for_search(self) -> dict[str, str]:
        """slug -> lowercase display name, for campaign search over districts."""
        return {slug: entry.name.lower() for slug, entry in self.by_slug.items()}


def load_file(path: str | os.PathLike[str]) -> Registry:
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    entries = raw.get("gliederungen")
    if not isinstance(entries, list) or not entries:
        raise GliederungConfigError(f"{path}: 'gliederungen' list is missing or empty")

    registry = Registry()
    for item in entries:
        slug = (item.get("slug") or "").strip()
        name = (item.get("name") or "").strip()
        parent = (item.get("parent") or "").strip() or None
        if not slug or not name:
            raise GliederungConfigError(f"{path}: every Gliederung needs 'slug' and 'name'")
        if slug in registry.by_slug:
            raise GliederungConfigError(f"{path}: duplicate slug {slug!r}")
        registry.by_slug[slug] = Gliederung(slug=slug, name=name, parent_slug=parent)

    for entry in registry.by_slug.values():
        if entry.parent_slug is not None and entry.parent_slug not in registry.by_slug:
            raise GliederungConfigError(
                f"{path}: {entry.slug!r} references unknown parent {entry.parent_slug!r}"
            )

    # Cycle guard: every entry must appear in the depth-first walk from the roots.
    if len(registry.ordered()) != len(registry.by_slug):
        raise GliederungConfigError(f"{path}: parent chain contains a cycle")
    return registry


def configured_path() -> str:
    return os.environ.get("DPP_GLIEDERUNGEN_FILE", DEFAULT_CONFIG_PATH)


@lru_cache(maxsize=1)
def get_registry() -> Registry:
    """Load (once per process) the registry from DPP_GLIEDERUNGEN_FILE.

    Defaults to the bundled config/gliederungen.yaml for local development;
    tests point DPP_GLIEDERUNGEN_FILE at a fixture file before importing dpp.
    """
    return load_file(configured_path())


def expand(group: str) -> frozenset[str]:
    """Expand a user group into district slugs (arch-02 inheritance).

    Recognized group values: "all" (every district), or a Gliederung slug
    (that district plus all descendants). Unknown groups contribute nothing.
    """
    registry = get_registry()
    if group.strip().lower() == "all":
        return registry.all_slugs()
    if registry.exists(group.strip()):
        return registry.expand(group.strip())
    return frozenset()
