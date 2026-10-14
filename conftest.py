"""Pytest configuration for the KabayaniTrack project.

The pinned Django 5.0 release is not fully compatible with Python 3.14:
``BaseContext.__copy__`` does ``duplicate = copy(super())``, which no longer
produces an object with a settable ``dicts`` attribute, so any test that
inspects ``response.context`` raises ``AttributeError``.  Replacing that one
method with an equivalent implementation that works on Python 3.14 keeps the
test client's template instrumentation functional.
"""

import pytest


def _base_context_copy(self):
    duplicate = self.__class__.__new__(self.__class__)
    duplicate.__dict__.update(self.__dict__)
    duplicate.dicts = self.dicts[:]
    return duplicate


@pytest.fixture(autouse=True)
def _patch_context_copy():
    from django.template.context import BaseContext

    if not getattr(BaseContext.__copy__, "_kabayan_patched", False):
        _base_context_copy._kabayan_patched = True
        BaseContext.__copy__ = _base_context_copy
    yield
