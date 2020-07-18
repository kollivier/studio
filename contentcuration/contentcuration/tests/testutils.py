#!/usr/bin/env python
import sys

import pytest

# Mark the test class or function as a slow test, where we avoid running it
# in a normal test run due to its long running time.
# Use py.test --includeslowtests to run these kinds of tests.
slowtest = pytest.mark.skipif(
    "--includeslowtests" not in sys.argv,
    reason="Skipping because this test is a slow test."
)

from mixer.backend.django import mixer
from contentcuration.models import ContentNode

mixer.register(
    ContentNode,
    extra_fields=lambda: {'a': 1, 'b': 2, 'c': {'d': 3}}
)
