from datetime import datetime

import pytest

from app.tid import OSLO, hilsen, norsk_dato


@pytest.mark.parametrize(
    ("time", "forventet"),
    [(4, "God natt"), (5, "God morgen"), (9, "God morgen"), (10, "God dag"), (18, "God kveld")],
)
def test_hilsen(time, forventet):
    assert hilsen(datetime(2026, 11, 3, time, 0, tzinfo=OSLO)) == forventet


def test_norsk_dato():
    assert norsk_dato(datetime(2026, 11, 3, tzinfo=OSLO)) == "tirsdag 3. november"
    assert norsk_dato(datetime(2026, 2, 1, tzinfo=OSLO)) == "søndag 1. februar"
