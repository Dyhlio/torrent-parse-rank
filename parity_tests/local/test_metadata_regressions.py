import pytest
from PTT import parse_title


@pytest.mark.parametrize("marker", ["VOF", "vof", "Vof"])
@pytest.mark.parametrize("separator", [".", " ", "_", "-"])
@pytest.mark.parametrize("base", ["Example.2024", "Example.S02E03", "Example.S01"])
def test_original_french_audio(marker, separator, base):
    result = parse_title(f"{base}{separator}{marker}{separator}1080p.BluRay.x264-GRP")
    assert result["audio_languages"] == ["fr-FR"]
    assert result["subtitle_languages"] == []


@pytest.mark.parametrize("marker", ["VOFF", "AVOF", "VOF2"])
def test_original_french_requires_a_complete_token(marker):
    result = parse_title(f"Example.2024.{marker}.1080p.BluRay")
    assert result["audio_languages"] == []


@pytest.mark.parametrize(
    "subtitles,expected", [("VOSTFR", "fr-FR"), ("ENGSUB", "en-US"), ("Multi-Subs", "multi")]
)
def test_original_french_keeps_subtitle_roles(subtitles, expected):
    result = parse_title(f"Example.2024.1080p.VOF.{subtitles}")
    assert result["audio_languages"] == ["fr-FR"]
    assert result["subtitle_languages"] == [expected]


@pytest.mark.parametrize(
    "codec",
    [
        "DTS-HD.MA",
        "DTS.HD.MA",
        "DTS HD MA",
        "DTS:HD MA",
        "DTS-HD.Master.Audio",
        "DTS-HD.HRA",
        "DTS-HD",
    ],
)
@pytest.mark.parametrize(
    "source,expected",
    [
        ("", None),
        ("HDTV", "HDTV"),
        ("HD", "HDTV"),
        ("HDTVRip", "HDTVRip"),
        ("DVB", "HDTV"),
        ("WEB-DL", "WEB-DL"),
        ("BluRay", "BluRay"),
        ("HD.Rip", "HDRip"),
    ],
)
@pytest.mark.parametrize("first", [False, True])
def test_dts_hd_does_not_supply_a_video_source(codec, source, expected, first):
    markers = f"{source}.{codec}" if first else f"{codec}.{source}"
    result = parse_title(f"Example.2024.1080p.{markers}.x264-GRP")
    assert result.get("quality") == expected
    assert result["resolution"] == "1080p"
    assert result["codec"] == "avc"
    assert result["group"] == "GRP"
    assert result["title"] == "Example"


@pytest.mark.parametrize(
    "edition,field",
    [("EXTENDED", "extended"), ("REMASTERED", "remastered"), ("Remaster", "remastered")],
)
@pytest.mark.parametrize("prefix", ["", "IMAX.", "Directors.Cut."])
@pytest.mark.parametrize("separator", [".", " ", "_"])
def test_edition_flags_are_available_with_the_edition(edition, field, prefix, separator):
    result = parse_title(f"Example.2024.{prefix}{edition}.1080p.BluRay".replace(".", separator))
    assert result.get(field) is True


@pytest.mark.parametrize("edition", ["IMAX", "Theatrical", "Collectors.Edition"])
def test_other_editions_do_not_add_extended_or_remastered(edition):
    result = parse_title(f"Example.2024.{edition}.1080p.BluRay")
    assert not result.get("extended")
    assert not result.get("remastered")


def test_extended_and_remastered_can_coexist():
    result = parse_title("Example.2024.EXTENDED.REMASTERED.1080p.BluRay")
    assert result["edition"] == "Extended Edition"
    assert result.get("extended") is True
    assert result.get("remastered") is True


@pytest.mark.parametrize(
    "marker,audio,subtitles",
    [
        ("FRENCH", ["fr-FR"], []),
        ("VOF SUBFRENCH", ["fr-FR"], ["fr-FR"]),
        ("ENGLISH SUBFRENCH", ["en-US"], ["fr-FR"]),
    ],
)
@pytest.mark.parametrize("case", [str.upper, str.lower, str.title])
@pytest.mark.parametrize("separator", [".", " ", "_"])
@pytest.mark.parametrize("base", ["Example.2024", "Example.S02E03", "Example.S01"])
def test_french_markers_keep_audio_and_subtitles(marker, audio, subtitles, case, separator, base):
    title = f"{base}.1080p.{case(marker)}.BluRay.x264-GRP".replace(".", separator)
    result = parse_title(title)
    assert result["audio_languages"] == audio
    assert result["subtitle_languages"] == subtitles
    assert result["title"] == "Example"
    assert result["quality"] == "BluRay"
    assert result["group"] == "GRP"


@pytest.mark.parametrize(
    "title,expected",
    [
        ("The French Connection.1971.1080p.BluRay", "The French Connection"),
        ("The French Dispatch.2021.1080p.BluRay", "The French Dispatch"),
        ("French Kiss.1995.1080p.BluRay", "French Kiss"),
        ("[French-Team] Example.2024.1080p.BluRay", "Example"),
        ("Example.2024.1080p.WEB-DL.x264-French", "Example"),
    ],
)
def test_french_in_titles_and_groups_is_not_an_audio_marker(title, expected):
    result = parse_title(title)
    assert result["audio_languages"] == []
    assert result["subtitle_languages"] == []
    assert result["title"] == expected


@pytest.mark.parametrize(
    "marker,audio,subtitles",
    [
        ("[Audio French] [Subs English]", ["fr-FR"], ["en-US"]),
        ("[Audio English] [Subs French]", ["en-US"], ["fr-FR"]),
        ("VOF subfrench VFQ", ["fr-CA"], ["fr-FR"]),
        ("French VFQ", ["fr-CA"], []),
        ("VOF subfrench ENGSUB", ["fr-FR"], ["fr-FR", "en-US"]),
    ],
)
def test_french_completion_preserves_roles_and_explicit_regions(marker, audio, subtitles):
    result = parse_title(f"Example.2024.1080p.{marker}.BluRay")
    assert result["audio_languages"] == audio
    assert result["subtitle_languages"] == subtitles


@pytest.mark.parametrize(
    "marker,audio",
    [
        ("japanese french subbed", ["ja-JP"]),
        ("subbed french", []),
        ("[Audio: Japanese] [French {SDH]", ["ja-JP"]),
        ("JAPANESE [French.(SDH]", ["ja-JP"]),
    ],
)
def test_missing_french_audio_is_not_inferred_from_ambiguous_annotations(marker, audio):
    result = parse_title(f"Example.2024.1080p.{marker}")
    assert result["audio_languages"] == audio
