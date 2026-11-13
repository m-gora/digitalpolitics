from pathlib import Path

from fastapi.templating import Jinja2Templates

import dpp.gliederungen as gliederungen

TEMPLATES_DIR = Path(__file__).parent / "templates"

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


class _GliederungHelper:
    """Jinja global exposing the Gliederung config registry to templates:
    gliederungen.name(slug), gliederungen.exists(slug), gliederungen.ordered().
    Delegates to the (lru_cached) registry so tests and deployments pick up
    their configured file; see dpp.gliederungen."""

    def ordered(self):
        return gliederungen.get_registry().ordered()

    def name(self, slug: str) -> str:
        return gliederungen.get_registry().name(slug)

    def exists(self, slug: str) -> bool:
        return gliederungen.get_registry().exists(slug)


templates.env.globals["gliederungen"] = _GliederungHelper()
