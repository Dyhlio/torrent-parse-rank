import json
from pathlib import Path

import pytest
from PTT import parse_title
from RTN import parse
from torrent_parse_rank_native import ptt_parse_many

CASES = json.loads(Path(__file__).with_name("releases.json").read_text(encoding="utf8"))["cases"]


@pytest.mark.parametrize("case", CASES, ids=lambda case: case["input"])
def test_reference_contract(case):
    assert parse_title(case["input"]) == case["expected"]
    parsed = parse(case["input"])
    for field in (
        "audio_languages",
        "subtitle_languages",
        "audio",
        "channels",
        "hdr",
        "dolby_vision_profiles",
    ):
        assert getattr(parsed, field) == case["expected"].get(field, [])


@pytest.mark.parametrize("translated", [False, True])
def test_batch_matches_scalar_in_input_order(translated):
    titles = [case["input"] for case in CASES]
    assert ptt_parse_many(titles, translated) == [
        parse_title(title, translated) for title in titles
    ]
