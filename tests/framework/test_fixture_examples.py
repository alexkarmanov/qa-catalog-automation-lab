"""Teaching examples for fixture lifecycles (the ``tally`` fixture in the root conftest) and the markers ``change`` / ``check``."""
from __future__ import annotations

import pytest

pytestmark = [pytest.mark.framework]


@pytest.mark.check
@pytest.mark.parametrize("attribute,expected", [("entries", ["opening balance"]), ("closed", False)], ids=["entries", "closed-flag"])
def test_tally_fixture_defaults(tally, attribute, expected):
    assert getattr(tally, attribute) == expected


@pytest.mark.change
def test_tally_can_be_changed_inside_a_test(tally):
    tally.entries.append("adjustment")
    assert tally.entries == ["opening balance", "adjustment"]
    assert tally.closed is False  # only the changed attribute differs


@pytest.mark.change
def test_fixture_object_is_recreated_for_every_test(tally):
    # Passes regardless of test order: a changed object in another test never leaks into this one.
    assert (tally.entries, tally.closed) == (["opening balance"], False)


@pytest.mark.change
def test_close_clears_the_entries_and_marks_the_tally_closed(tally):
    tally.close()
    assert (tally.entries, tally.closed) == ([], True)
