import pytest
import regex
from PTT import Parser, parse_title
from RTN import parse
from RTN.extras import get_lev_ratio
from RTN.fetch import fetch_other
from RTN.models import DefaultRanking, SettingsModel
from RTN.patterns import check_pattern, language_matches, normalize_title
from RTN.ranker import calculate_hdr_rank


@pytest.mark.parametrize(
    "language,preference,expected",
    [
        ("fr-CA", "fr", True),
        ("fr-CA", "fr-FR", False),
        ("zh-Hant-TW", "zh-Hant", True),
        ("multi", "fr", False),
    ],
)
def test_public_language_matching_uses_native_policy(language, preference, expected):
    assert language_matches(language, preference) is expected


@pytest.mark.parametrize(
    "pattern,flags,title,expected",
    [
        ("^two", regex.MULTILINE, "one\ntwo", True),
        ("one.two", regex.DOTALL, "one\ntwo", True),
        ("one # trailing comment", regex.VERBOSE, "one", True),
        ("one", 0, "ONE", False),
    ],
)
def test_regex_flags_survive_native_serialization(pattern, flags, title, expected):
    assert check_pattern([regex.compile(pattern, flags)], title) is expected


def test_unsupported_regex_flags_are_not_silently_discarded():
    with pytest.raises(ValueError, match="Unsupported"):
        check_pattern([regex.compile("word", regex.REVERSE)], "word")


def test_bit_depth_policy_uses_serialized_setting_name():
    data = parse("Example.2024.1080p.10bit")
    settings = SettingsModel()
    settings.custom_ranks.hdr.bit10.fetch = False
    assert fetch_other(data, settings, set()) is True
    settings.custom_ranks.hdr.bit10.fetch = True
    settings.custom_ranks.hdr.bit10.rank = 12345
    settings.custom_ranks.hdr.bit10.use_custom_rank = True
    assert calculate_hdr_rank(data, settings, DefaultRanking()) == 12345


def test_similarity_preserves_python_indel_metric():
    assert get_lev_ratio("Bleach", "Bleach Thousand Year Blood War", 0.0) == 0.33333333333333337
    assert normalize_title("Герой") == "герой"


def test_custom_callbacks_keep_native_contract_and_explicit_removals():
    parser = Parser()

    def callback(context):
        assert set(context) == {"title", "result", "matched"}
        assert "audio_languages" in context["matched"]
        assert "languages" not in context["matched"]
        context["result"].pop("subtitle_languages")

    parser.add_handler(callback)
    result = parser.parse("Example.2024.1080p.JAPANESE.VOSTFR", True)
    assert result["audio_languages"] == ["Japanese (Japan)"]
    assert "subtitle_languages" not in result


def test_language_occurrences_are_not_removed_globally():
    result = parse_title("www.example.nl - Example.2024.1080p.DUTCH")
    assert result["audio_languages"] == ["nl-NL"]
    result = parse_title("Example.2024.Sci-Fi.1080p.FINNISH")
    assert result["audio_languages"] == ["fi-FI"]


def test_metadata_context_retains_utf8_boundaries():
    assert isinstance(parse_title("WEB-DL[.mkv]K[trailer WEB-DL/WEB-DL 日本語. -")["title"], str)
