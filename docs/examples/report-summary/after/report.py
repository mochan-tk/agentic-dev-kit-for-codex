"""Render nonblank names in their input order; no I/O or external services."""


def render_report(names):
    return "\n".join(name.strip() for name in names if name.strip())
