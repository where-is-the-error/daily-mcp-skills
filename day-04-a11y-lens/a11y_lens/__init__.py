"""a11y-lens — 브라우저 없이 HTML 을 접근성 트리로 바꾸고 위반을 WCAG 조항에 붙인다."""

from __future__ import annotations

__version__ = "0.1.0"

from .accname import accessible_name, role_of, selector_of
from .audit import audit_page, audit_site, render_page, render_plan, render_site
from .htmltree import parse, parse_file
from .rules import RULES, audit_document
from .snapshot import build

__all__ = [
    "__version__",
    "parse",
    "parse_file",
    "build",
    "RULES",
    "audit_document",
    "audit_page",
    "audit_site",
    "render_page",
    "render_site",
    "render_plan",
    "accessible_name",
    "role_of",
    "selector_of",
]
