import pytest
from PTT import parse_title


@pytest.mark.parametrize(
    "marker,language",
    [
        ("VOF", "fr-FR"),
        ("VFQ", "fr-CA"),
        ("VFF", "fr-FR"),
        ("VF", "fr-FR"),
        ("TRUEFRENCH", "fr-FR"),
        ("MULTI", "multi"),
    ],
)
@pytest.mark.parametrize("case", [str.upper, str.lower, str.title])
@pytest.mark.parametrize("separator", [".", " ", "_"])
@pytest.mark.parametrize("first", [False, True])
@pytest.mark.parametrize("bracketed", [False, True])
@pytest.mark.parametrize("subtitle_marker", ["Multi-Subs", "Multiple.Subtitles", "MSUB"])
def test_audio_markers_do_not_inherit_a_multiple_subtitles_role(
    marker, language, case, separator, first, bracketed, subtitle_marker
):
    tokens = f"{marker} {subtitle_marker}" if first else f"{subtitle_marker} {marker}"
    tokens = case(tokens).replace(" ", separator)
    if bracketed:
        tokens = f"[{tokens}]"
    result = parse_title(f"Example.S02E03.1080p.{tokens}.WEB-DL.x264-GRP")
    assert result["audio_languages"] == [language]
    assert result["subtitle_languages"] == ["multi"]
    assert result["title"] == "Example"
    assert result["seasons"] == [2]
    assert result["episodes"] == [3]
    assert result["group"] == "GRP"


@pytest.mark.parametrize("tokens", ["MULTI SUBFRENCH", "SUBFRENCH MULTI"])
@pytest.mark.parametrize("case", [str.upper, str.lower, str.title])
@pytest.mark.parametrize("separator", [".", " ", "_"])
def test_multi_and_subfrench_are_separate_markers(tokens, case, separator):
    result = parse_title("Example.2024.1080p." + case(tokens).replace(" ", separator) + ".BluRay")
    assert result["audio_languages"] == ["multi"]
    assert result["subtitle_languages"] == ["fr-FR"]


@pytest.mark.parametrize(
    "marker,language", [("VOF", "fr-FR"), ("VFQ", "fr-CA"), ("VFF", "fr-FR"), ("MULTI", "multi")]
)
@pytest.mark.parametrize(
    "template",
    ["[Subs {marker}]", "Subs: {marker}", "[Subtitles: {marker}]", "{marker}.srt", "{marker}.ass"],
)
def test_explicit_subtitle_context_keeps_precedence(marker, language, template):
    result = parse_title("Example.S02E03.1080p." + template.format(marker=marker))
    assert result["audio_languages"] == []
    assert result["subtitle_languages"] == [language]


@pytest.mark.parametrize(
    "tokens,audio,subtitles",
    [
        ("Multi-Subs English", [], ["multi", "en-US"]),
        ("Multi-Subs French", [], ["multi", "fr-FR"]),
        ("[Subs English French] VOF", ["fr-FR"], ["en-US", "fr-FR"]),
        ("[Audio VOF] [Subs English French]", ["fr-FR"], ["en-US", "fr-FR"]),
        ("Multi-Subs Subs: VFQ", [], ["multi", "fr-CA"]),
    ],
)
def test_plain_language_lists_and_separate_labels_are_preserved(tokens, audio, subtitles):
    result = parse_title("Example.S02E03.1080p." + tokens)
    assert result["audio_languages"] == audio
    assert result["subtitle_languages"] == subtitles


@pytest.mark.parametrize(
    "marker,language", [("VOF", "fr-FR"), ("VFQ", "fr-CA"), ("VFF", "fr-FR"), ("MULTI", "multi")]
)
@pytest.mark.parametrize(
    "template",
    [
        "Multi-Subs[{marker}]",
        "Multi-Subs: {marker}",
        "Multi-Subs {{{marker}}}",
        "Multiple-Subtitles({marker})",
    ],
)
def test_multi_subtitle_lists_keep_their_explicit_role(marker, language, template):
    result = parse_title("Example.2024.1080p." + template.format(marker=marker))
    assert result["audio_languages"] == []
    assert result["subtitle_languages"] == list(dict.fromkeys(["multi", language]))


def test_multi_subtitle_list_does_not_consume_separate_audio():
    result = parse_title("Example.2024.1080p.Multi-Subs[English French] VOF")
    assert result["audio_languages"] == ["fr-FR"]
    assert result["subtitle_languages"] == ["multi", "en-US", "fr-FR"]
