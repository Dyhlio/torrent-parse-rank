import pytest
from PTT import parse_title


@pytest.mark.parametrize(
    "language,tag",
    [
        ("French", "fr-FR"),
        ("Japanese", "ja-JP"),
        ("fr-CA", "fr-CA"),
        ("pt-PT", "pt-PT"),
        ("pt-BR", "pt-BR"),
        ("es-419", "es-419"),
        ("zh-Hant-TW", "zh-Hant-TW"),
    ],
)
@pytest.mark.parametrize(
    "template",
    [
        "[Audio: English; Subs: {language}]",
        "Audio: English Subs: {language}",
        "English Subs: {language}",
        "[English Subs: {language}]",
    ],
)
@pytest.mark.parametrize("case", [str, str.lower, str.upper])
def test_subtitle_label_does_not_consume_preceding_audio(language, tag, template, case):
    result = parse_title(
        "Example.S02E03.1080p.WEB-DL " + case(template.format(language=language)) + " x264-GRP"
    )
    assert result["audio_languages"] == ["en-US"]
    assert result["subtitle_languages"] == [tag]
    assert result["title"] == "Example"
    assert result["seasons"] == [2]
    assert result["episodes"] == [3]
    assert result["quality"] == "WEB-DL"
    assert result["group"] == "GRP"


@pytest.mark.parametrize(
    "text",
    [
        "English Subs",
        "English SDH",
        "English Forced",
        "English SDH:",
        "English Forced:",
        "English Subs: SDH",
        "English Subs: Forced",
        "English Subs:",
        "[English Subs]",
        "[English SDH]",
        "[English (SDH)]",
        "English Subs.srt",
        "[Audio: English; Subs: French].srt",
    ],
)
def test_subtitle_annotations_and_files_keep_precedence(text):
    result = parse_title("Example.S02E03.1080p." + text)
    assert result["audio_languages"] == []
    assert "en-US" in result["subtitle_languages"]


@pytest.mark.parametrize(
    "text",
    [
        "[Audio: English] [Subs: French]",
        "[Audio: English; Subtitles: French]",
        "[Audio: English; Subs: [French]]",
        "English Subs[French]",
        "[Subs: French] [Audio: English]",
    ],
)
def test_separate_language_lists_keep_their_roles(text):
    result = parse_title("Example.S02E03.1080p." + text)
    assert result["audio_languages"] == ["en-US"]
    assert result["subtitle_languages"] == ["fr-FR"]
