"""Bare-bones setup.py for editable install support."""
from setuptools import setup

setup(
    use_scm_version=True,
    setup_requires=['setuptools_scm'],
)
