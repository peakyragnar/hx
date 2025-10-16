from heretix_wel.timeliness import heuristic_is_timely


def test_timely_detection_positive():
    assert heuristic_is_timely("Who wins tonight's debate?")
    assert heuristic_is_timely("Earnings call is scheduled for 2024-11-05")


def test_timely_detection_negative():
    assert not heuristic_is_timely("Planck's constant remains unchanged.")
