"""The province data file. It is data, so it is checked as data."""

from weather.db.provinces import PROVINCES


def test_there_are_exactly_81_provinces():
    assert len(PROVINCES) == 81


def test_no_province_name_is_repeated():
    names = [name for name, _, _ in PROVINCES]
    assert len(set(names)) == 81


def test_no_two_provinces_share_coordinates():
    """Duplicated coordinates would collide on the unique constraint and
    silently drop a province at seed time."""
    coords = [(lat, lon) for _, lat, lon in PROVINCES]
    assert len(set(coords)) == 81


def test_coordinates_fall_within_turkey():
    """A sanity bound: a typo that flips a sign or drops a digit lands
    the point in the sea or another continent."""
    for name, lat, lon in PROVINCES:
        assert 35.0 <= lat <= 43.0, f"{name} latitude {lat}"
        assert 25.0 <= lon <= 45.0, f"{name} longitude {lon}"
