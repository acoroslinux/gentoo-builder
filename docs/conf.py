"""Sphinx configuration for Gentoo-Builder documentation."""
from __future__ import annotations

import os
import sys
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

project = "Gentoo-Builder"
author = "AçorOS Linux Team"
release = "1.0.0"
version = "1.0"
current_year = datetime.now().year
copyright = f"2026-{current_year}, {author}"

extensions = [
    "sphinx.ext.autodoc",
    "sphinx.ext.autosummary",
    "sphinx.ext.doctest",
    "sphinx.ext.intersphinx",
    "sphinx.ext.napoleon",
    "sphinx.ext.viewcode",
    "sphinx.ext.todo",
    "sphinx_rtd_theme",
    "myst_parser",
]

autosummary_generate = True

autodoc_default_options = {
    "members": True,
    "member-order": "bysource",
    "undoc-members": True,
    "show-inheritance": True,
}

autodoc_member_order = "bysource"
autodoc_typehints = "description"

napoleon_google_docstring = True
napoleon_numpy_docstring = True
napoleon_include_init_with_doc = False
napoleon_include_private_with_doc = False
napoleon_include_special_with_doc = True
napoleon_use_admonition_for_examples = True
napoleon_use_admonition_for_notes = True
napoleon_use_admonition_for_references = False
napoleon_use_ivar = False
napoleon_use_param = True
napoleon_use_rtype = True
napoleon_preprocess_types = False
napoleon_type_aliases = None
napoleon_attr_annotations = True

templates_path = ["_templates"]
exclude_patterns = ["_build", "Thumbs.db", ".DS_Store"]
source_suffix = {
    ".rst": "restructuredtext",
    ".md": "markdown",
}
master_doc = "index"
language = "en"

html_theme = "sphinx_rtd_theme"
html_title = project
html_static_path = ["_static"]
html_theme_options = {
    "logo_only": False,
    "style_nav_header_background": "#7A5B95",  # Gentoo Purple
    "prev_next_buttons_location": "bottom",
    "style_external_links": False,
    "collapse_navigation": True,
    "sticky_navigation": True,
    "navigation_depth": 4,
    "includehidden": True,
    "titles_only": False,
}

html_show_sourcelink = True
html_show_sphinx = True
html_show_copyright = True
htmlhelp_basename = "GentooBuilderDocs"
html_use_opensearch = ""
html_search_language = "en"
html_search_options = {"type": "default"}

latex_elements = {
    "papersize": "letterpaper",
    "pointsize": "10pt",
    "preamble": "",
    "figure_align": "htbp",
}

latex_documents = [
    ("index", "GentooBuilder.tex", "Gentoo-Builder Documentation", author, "manual"),
]

man_pages = [
    ("index", "gentoobuilder", "Gentoo-Builder Documentation", [author], 1),
]

texinfo_documents = [
    (
        "index",
        "GentooBuilder",
        "Gentoo-Builder Documentation",
        author,
        "GentooBuilder",
        "Gentoo-Builder documentation.",
        "Miscellaneous",
    ),
]

intersphinx_mapping = {
    "python": ("https://docs.python.org/3", None),
}

todo_include_todos = True
license = "MIT"

def setup(app):
    """Setup the Sphinx app with custom CSS."""
    app.add_css_file("custom.css")
