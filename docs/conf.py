# Configuration file for the Sphinx documentation builder.
#
# For the full list of built-in configuration values, see the documentation:
# https://www.sphinx-doc.org/en/master/usage/config.html

import os
import sys

# Add the parent directory to the path so we can import the package
sys.path.insert(0, os.path.abspath(".."))

# Project information
project = "FAIR EVA"
copyright = "2023, IFCA-Advanced-Computing"
author = "Fernando Aguilar Gómez, Pablo Orviz Fernández, Iván Palomo Llavona"
release = "1.5.0"

# General configuration
# https://www.sphinx-doc.org/en/master/usage/configuration.html#general-configuration

extensions = [
    "sphinx.ext.autodoc",
    "sphinx.ext.viewcode",
    "sphinx.ext.intersphinx",
    "myst_parser",
]

templates_path = ["_templates"]
exclude_patterns = ["_build", "Thumbs.db", ".DS_Store"]

# The master toctree document.
master_doc = "index"

# MyST Parser configuration for Markdown support
myst_enable_extensions = [
    "colon_fence",
    "dollarmath",
]

myst_url_schemes = ("http", "https", "ftp")

# Options for HTML output
# https://www.sphinx-doc.org/en/master/usage/html_options.html#options-for-html-output

html_theme = "sphinx_rtd_theme"
html_static_path = ["_static"]

# Language
language = "en"

# Intersphinx mapping
intersphinx_mapping = {
    "python": ("https://docs.python.org/3", None),
}
