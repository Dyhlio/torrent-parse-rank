import pytest
from PTT import parse_title


@pytest.mark.parametrize(
    "marker,tag", [("Malay", "ms-MY"), ("Malayalam", "ml-IN"), ("MAL", "ml-IN")]
)
@pytest.mark.parametrize("case", [str, str.lower, str.upper])
@pytest.mark.parametrize(
    "template",
    [
        "Example.2024.1080p.{marker}.WEB-DL.x264-GRP",
        "Example.S02E03.1080p.{marker}.WEB-DL.x264-GRP",
        "Example.S01.COMPLETE.1080p.{marker}.WEB-DL.x264-GRP",
    ],
)
def test_malay_and_malayalam_are_distinct_audio_languages(marker, tag, case, template):
    result = parse_title(template.format(marker=case(marker)))
    assert result["audio_languages"] == [tag]
    assert result["subtitle_languages"] == []
    assert result["title"] == "Example"
    assert result["quality"] == "WEB-DL"
    assert result["codec"] == "avc"
    assert result["group"] == "GRP"


@pytest.mark.parametrize(
    "marker,tag", [("Malay", "ms-MY"), ("Malayalam", "ml-IN"), ("MAL", "ml-IN")]
)
@pytest.mark.parametrize("extension", ["srt", "ass", "vtt"])
def test_malay_and_malayalam_subtitle_files(marker, tag, extension):
    result = parse_title(f"Example.S02E03.{marker}.{extension}")
    assert result["audio_languages"] == []
    assert result["subtitle_languages"] == [tag]


@pytest.mark.parametrize(
    "marker,tag", [("Malay", "ms-MY"), ("Malayalam", "ml-IN"), ("MAL", "ml-IN")]
)
@pytest.mark.parametrize("role", ["Audio", "Subs"])
def test_explicit_malay_and_malayalam_roles(marker, tag, role):
    result = parse_title(f"Example.S02E03.1080p.WEB-DL [{role}: {marker}]")
    assert result["audio_languages"] == ([tag] if role == "Audio" else [])
    assert result["subtitle_languages"] == ([tag] if role == "Subs" else [])


def test_malay_and_malayalam_can_coexist():
    result = parse_title("Example.2024.1080p.Malay.Malayalam.WEB-DL.x264-GRP")
    assert result["audio_languages"] == ["ms-MY", "ml-IN"]


@pytest.mark.parametrize(
    "title", ["The Malay Archipelago.2024.1080p.WEB-DL", "Malay.2024.1080p.WEB-DL"]
)
def test_malay_in_title_is_not_an_audio_language(title):
    assert parse_title(title)["audio_languages"] == []
