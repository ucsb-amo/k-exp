# Configuration file for the Sphinx documentation builder.
#
# For the full list of built-in configuration values, see the documentation:
# https://www.sphinx-doc.org/en/master/usage/configuration.html

# -- Project information -----------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#project-information

project = 'k-exp'
copyright = '2024, Jared E Pagett'
author = 'Jared E Pagett'
release = '0.0'

# -- General configuration ---------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#general-configuration

extensions = ['sphinx.ext.napoleon',
              'sphinx.ext.autodoc',
              'sphinx.ext.autosummary',
              'sphinx.ext.coverage',
              'sphinx.ext.viewcode']

templates_path = ['_templates']
exclude_patterns = []

# python setup
import os
import sys
sys.path.insert(0, os.path.abspath('../..'))

# -- Options for HTML output -------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#options-for-html-output

html_theme = 'classic'
html_static_path = ['_static']
