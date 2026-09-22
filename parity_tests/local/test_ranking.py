import json
import subprocess
import sys

import pytest
from PTT import parse_title
from RTN import RTN, parse
from RTN.fetch import check_fetch, fetch_audio, fetch_hdr, language_handler
from RTN.models import DefaultRanking, ParsedData, SettingsModel, Torrent
from RTN.ranker import (
    calculate_audio_rank,
    calculate_channels_rank,
    calculate_extra_ranks,
    calculate_hdr_rank,
    calculate_preferred_langs,
)


def test_audio_language_input_name():
    data = ParsedData(raw_title="Amelie", audio_languages=["fr-CA"])
    assert data.audio_languages == ["fr-CA"]
    for by_alias in (False, True):
        output = data.model_dump(by_alias=by_alias)
        assert output["audio_languages"] == ["fr-CA"]
        assert "languages" not in output
        assert ParsedData.model_validate(output) == data
    assert ParsedData.model_validate_json(data.model_dump_json()) == data


def test_removed_input_names_do_not_populate_metadata():
    with pytest.raises(ValueError):
        ParsedData(raw_title="Amelie", languages=["fr-FR"], _3d=True)


def test_audio_language_updates_use_the_result_field():
    data = ParsedData(raw_title="Amelie", audio_languages=["fr-CA"])
    data.audio_languages.append("en-US")
    assert data.audio_languages == ["fr-CA", "en-US"]
    data.audio_languages = ["ja-JP"]
    assert data.audio_languages == ["ja-JP"]
    assert data.model_dump()["audio_languages"] == ["ja-JP"]
    assert ParsedData(raw_title="Other").audio_languages == []


def test_audio_language_schema_and_settings_are_separate():
    for mode in ("validation", "serialization"):
        fields = ParsedData.model_json_schema(mode=mode)["properties"]
        assert "audio_languages" in fields
        assert "subtitle_languages" in fields
        assert "languages" not in fields
        assert "_3d" not in fields
    settings = SettingsModel(languages={"required": ["fr"]})
    assert settings.model_dump()["languages"]["required"] == ["fr"]
    assert "audio_languages" not in settings.model_dump()


@pytest.mark.parametrize(
    "title, expected",
    [
        ("Amelie.2001.1080p.VFQ.BluRay", {"audio_languages": ["fr-CA"]}),
        ("Amelie.2001.1080p.VFF.BluRay", {"audio_languages": ["fr-FR"]}),
        ("Amelie.2001.1080p.VOF.BluRay", {"audio_languages": ["fr-FR"]}),
        (
            "Naruto.S01E01.1080p.JAPANESE.VOSTFR",
            {"audio_languages": ["ja-JP"], "subtitle_languages": ["fr-FR"]},
        ),
        (
            "Naruto.S01E01.1080p.JAPANESE.VOSTA",
            {"audio_languages": ["ja-JP"], "subtitle_languages": ["en-US"]},
        ),
        ("Naruto.S01E01.1080p.MULTi", {"audio_languages": ["multi"]}),
        (
            "Naruto.S01E01.1080p.Multi-Subs",
            {"audio_languages": [], "subtitle_languages": ["multi"]},
        ),
        ("Dune.2021.2160p.BluRay.DTS-HD.MA.7.1.4", {"audio": ["DTS-HD MA"], "channels": ["7.1.4"]}),
        ("Dune.2021.1080p.BluRay.HE-AACv2", {"audio": ["HE-AACv2"]}),
        ("Dune.2021.2160p.BluRay.HDR10", {"hdr": ["HDR10"]}),
        ("Dune.2021.2160p.BluRay.HLG", {"hdr": ["HLG"]}),
        ("Dune.2021.2160p.BluRay.DV.Profile.8.1", {"dolby_vision_profiles": ["8.1"]}),
        ("Avatar.2009.1080p.BluRay.3D", {"three_d": True}),
        ("Dune.2021.1080p.EXTENDED.REMASTERED", {"extended": True, "remastered": True}),
        ("Better.Call.Saul.S03E04.CONVERT.720p.WEB.h264-TBS", {"converted": True}),
    ],
)
def test_metadata_round_trip(title, expected):
    data = parse(title)
    for field, value in expected.items():
        assert getattr(data, field, None) == value
    assert ParsedData.model_validate_json(data.model_dump_json()) == data
    assert ParsedData.model_validate(data.model_dump(by_alias=True)) == data
    torrent = Torrent(raw_title=title, infohash="a" * 40, data=data)
    assert Torrent.model_validate_json(torrent.model_dump_json()).data == data


@pytest.mark.parametrize("field", ["3d", "three_d"])
def test_three_d_input_names(field):
    data = ParsedData(raw_title="Avatar", **{field: True})
    assert data.three_d is True
    assert data.model_dump(by_alias=True)["3d"] is True
    data.three_d = False
    assert data.three_d is False


@pytest.mark.parametrize(
    "language, preference, matches",
    [
        ("fr-CA", "fr", True),
        ("fr-FR", "fr", True),
        ("fr-CA", "fr-CA", True),
        ("fr-CA", "fr-FR", False),
        ("fr", "fr-CA", False),
        ("fr", "fr", True),
        ("FR-ca", "fr-ca", True),
        ("en-GB", "en", True),
        ("zh-Hant-TW", "zh", True),
        ("zh-Hant-TW", "zh-Hant", True),
        ("zh-Hant-TW", "zh-Hans", False),
        ("es-419", "es", True),
        ("multi", "fr", False),
        ("multi", "multi", True),
    ],
)
@pytest.mark.parametrize("policy", ["required", "allowed", "exclude", "preferred"])
def test_regional_language_policies(language, preference, matches, policy):
    data = ParsedData(raw_title="Amelie", audio_languages=[language])
    settings = SettingsModel(
        options={"allow_english_in_languages": False}, languages={policy: [preference]}
    )
    if policy == "preferred":
        assert calculate_preferred_langs(data, settings) == (10000 if matches else 0)
    else:
        if policy == "allowed":
            settings.languages.exclude = [language]
        denied = language_handler(data, settings, set())
        assert denied is (matches if policy == "exclude" else not matches)


@pytest.mark.parametrize("language", ["en-US", "en-GB", "en"])
def test_english_exception(language):
    data = ParsedData(raw_title="Dune", audio_languages=[language, "fr-FR"])
    settings = SettingsModel(languages={"exclude": ["fr"]})
    assert language_handler(data, settings, set()) is False
    settings.languages.required = ["ja"]
    assert language_handler(data, settings, set()) is True


@pytest.mark.parametrize(
    "group, language",
    [("anime", "ja-JP"), ("non_anime", "fr-CA"), ("common", "es-419"), ("all", "uk-UA")],
)
def test_language_groups(group, language):
    settings = SettingsModel(
        options={"allow_english_in_languages": False}, languages={"exclude": [group]}
    )
    assert (
        language_handler(ParsedData(raw_title="Dune", audio_languages=[language]), settings, set())
        is True
    )


@pytest.mark.parametrize(
    "audio, key",
    [
        ("DTS-HD MA", "dts_lossless"),
        ("DTS-HD HRA", "dts_lossy"),
        ("DTS-HD", "dts_hd"),
        ("DTS-X", "dts_x"),
        ("HE-AAC", "aac"),
        ("HE-AACv2", "aac"),
    ],
)
def test_detailed_audio_rank_and_filter(audio, key):
    data = ParsedData(raw_title="Dune", audio=[audio])
    settings = SettingsModel(
        custom_ranks={"audio": {key: {"fetch": False, "use_custom_rank": True, "rank": 123}}}
    )
    assert calculate_audio_rank(data, settings, DefaultRanking()) == 123
    failed_keys = set()
    assert fetch_audio(data, settings, failed_keys) is True
    assert failed_keys == {f"audio_{key}"}
    assert data.audio == [audio]


@pytest.mark.parametrize(
    "audio, key, legacy", [("DTS-HD", "dts_hd", "dts_lossy"), ("DTS-X", "dts_x", "dts_lossless")]
)
def test_legacy_dts_policies(audio, key, legacy):
    data = ParsedData(raw_title="Dune", audio=[audio])
    settings = SettingsModel(
        custom_ranks={"audio": {legacy: {"fetch": False, "use_custom_rank": True, "rank": 123}}}
    )
    assert calculate_audio_rank(data, settings, DefaultRanking()) == 123
    assert fetch_audio(data, settings, set()) is True
    restored = SettingsModel.model_validate_json(settings.model_dump_json())
    assert calculate_audio_rank(data, restored, DefaultRanking()) == 123
    assert fetch_audio(data, restored, set()) is True
    rank_model = DefaultRanking(**{legacy: 456})
    assert calculate_audio_rank(data, SettingsModel(), rank_model) == 456
    explicit_model = DefaultRanking(**{legacy: 456, key: 0})
    assert calculate_audio_rank(data, SettingsModel(), explicit_model) == 0
    overridden = SettingsModel(
        custom_ranks={"audio": {legacy: {"fetch": False}, key: {"fetch": True}}}
    )
    assert fetch_audio(data, overridden, set()) is False


@pytest.mark.parametrize(
    "hdr, key", [("HDR10", "hdr"), ("HLG", "hdr"), ("HDR10+", "hdr10plus"), ("DV", "dolby_vision")]
)
def test_detailed_hdr_rank_and_filter(hdr, key):
    data = ParsedData(raw_title="Dune", hdr=[hdr])
    settings = SettingsModel(
        custom_ranks={"hdr": {key: {"fetch": False, "use_custom_rank": True, "rank": 321}}}
    )
    assert calculate_hdr_rank(data, settings, DefaultRanking()) == 321
    failed_keys = set()
    assert fetch_hdr(data, settings, failed_keys) is True
    assert failed_keys == {f"hdr_{key}"}


@pytest.mark.parametrize("channels", ["5.1.2", "5.1.4", "7.1.2", "7.1.4", "9.1.6"])
def test_height_channels_ranking(channels):
    settings = SettingsModel(
        custom_ranks={"audio": {"surround": {"use_custom_rank": True, "rank": 456}}}
    )
    assert (
        calculate_channels_rank(
            ParsedData(raw_title="Dune", channels=[channels]), settings, DefaultRanking()
        )
        == 456
    )


def test_three_d_filter_and_rank_without_hdr_or_seasons():
    data = parse("Avatar.2009.1080p.BluRay.3D")
    assert calculate_extra_ranks(data, SettingsModel(), DefaultRanking()) == -10000
    for speed_mode in (True, False):
        accepted, reasons = check_fetch(data, SettingsModel(), speed_mode)
        assert accepted is False
        assert "extras_three_d" in reasons


def test_convert_filter_and_rank():
    data = parse("Better.Call.Saul.S03E04.CONVERT.720p.WEB.h264-TBS")
    assert data.converted is True
    assert calculate_extra_ranks(data, SettingsModel(), DefaultRanking()) == -1000
    for speed_mode in (True, False):
        accepted, reasons = check_fetch(data, SettingsModel(), speed_mode)
        assert accepted is False
        assert "extras_converted" in reasons


def test_metadata_lists_are_independent():
    first = parse("Naruto.S01E01.1080p.JAPANESE.VOSTFR")
    first.subtitle_languages.append("en-US")
    first.dolby_vision_profiles.append("8.1")
    second = parse(first.raw_title)
    assert second.subtitle_languages == ["fr-FR"]
    assert second.dolby_vision_profiles == []


def test_unknown_hdr_does_not_raise():
    data = ParsedData(raw_title="Dune", hdr=["unknown"])
    assert fetch_hdr(data, SettingsModel(), set()) is False
    assert calculate_hdr_rank(data, SettingsModel(), DefaultRanking()) == 0


def test_translated_languages_preserve_subtitles():
    data = parse("Naruto.S01E01.1080p.JAPANESE.VOSTFR", translate_langs=True)
    raw = parse_title(data.raw_title, translate_languages=True)
    assert data.audio_languages == raw["audio_languages"]
    assert data.subtitle_languages == raw["subtitle_languages"]


def test_rank_preserves_metadata():
    title = "Dune.2021.1080p.VFQ.VOSTA.BluRay.DTS-HD.MA.7.1.4.DV.Profile.8.1"
    torrent = RTN(SettingsModel()).rank(title, "a" * 40)
    assert torrent.data == parse(title)


def test_cli_preserves_metadata():
    title = "Avatar.2009.1080p.JAPANESE.VOSTFR.BluRay.3D.DV.Profile.8.1"
    result = subprocess.run(
        [sys.executable, "-m", "RTN.cli", "parse", title],
        capture_output=True,
        text=True,
        check=True,
    )
    data = json.loads(result.stdout)
    assert data["subtitle_languages"] == ["fr-FR"]
    assert data["dolby_vision_profiles"] == ["8.1"]
    assert data["3d"] is True
