import inspect
import itertools
import json
import subprocess
import sys

import pytest
from PTT import parse_title
from PTT.handlers import add_defaults
from PTT.parse import Parser

EXTENDED_FIELDS = {
    "audio_languages",
    "subtitle_languages",
    "audio",
    "channels",
    "hdr",
    "dolby_vision_profiles",
}


@pytest.mark.parametrize(
    "marker,audio,subtitles",
    [
        ("VFQ", ["fr-CA"], []),
        ("VFF", ["fr-FR"], []),
        ("VFQ VFF", ["fr-CA", "fr-FR"], []),
        ("FRENCH VFQ", ["fr-CA"], []),
        ("FRENCH VFF VFQ", ["fr-FR", "fr-CA"], []),
        ("JAPANESE VOSTFR", ["ja-JP"], ["fr-FR"]),
        ("VFQ VOSTFR", ["fr-CA"], ["fr-FR"]),
        ("VOSTA", [], ["en-US"]),
        ("ENGSUB", [], ["en-US"]),
        ("Multi-Subs", [], ["multi"]),
        ("MULTI", ["multi"], []),
        ("MULTI VOSTFR", ["multi"], ["fr-FR"]),
        ("[AAC ENG FRE]", ["en-US", "fr-FR"], []),
        ("[Audio ENG POL Subs FRE GER]", ["en-US", "pl-PL"], ["fr-FR", "de-DE"]),
        ("[Subs Latin American Spanish]", [], ["es-419"]),
        ("Dublado BR", ["pt-BR"], []),
        ("legendado BR", [], ["pt-BR"]),
        ("[Audio Japanese] [French SDH]", ["ja-JP"], ["fr-FR"]),
        ("(eng-fre-pt-spa)", ["en-US", "fr-FR", "pt-BR", "es-ES"], []),
        ("pt-PT", ["pt-PT"], []),
        ("fr-CA", ["fr-CA"], []),
        ("es-419", ["es-419"], []),
        ("zh-Hant-TW", ["zh-Hant-TW"], []),
        ("fr-FR fr-CA", ["fr-FR", "fr-CA"], []),
        ("CHT", ["zh-Hant-TW"], []),
        ("[Audio Japanese French] [Subs English]", ["ja-JP", "fr-FR"], ["en-US"]),
    ],
)
@pytest.mark.parametrize("separator", [" ", ".", "_"])
@pytest.mark.parametrize("base", ["Example.2024", "Example.S02E03", "[Group] Example - 1177"])
def test_regional_languages_and_roles(marker, audio, subtitles, separator, base):
    result = parse_title(base + ".1080p." + marker.replace(" ", separator))
    assert result["audio_languages"] == audio
    assert result["subtitle_languages"] == subtitles


@pytest.mark.parametrize(
    "marker,expected",
    [
        ("VFQ", "fr-CA"),
        ("VFF", "fr-FR"),
        ("pt-PT", "pt-PT"),
        ("Japanese", "ja-JP"),
        ("French", "fr-FR"),
    ],
)
@pytest.mark.parametrize("extension", ["srt", "ass", "ssa", "vtt", "sub", "idx"])
def test_subtitle_files(marker, expected, extension):
    result = parse_title(f"Example.S02E03.{marker}.{extension}")
    assert result["audio_languages"] == []
    assert result["subtitle_languages"] == [expected]


@pytest.mark.parametrize(
    "prefix,audio,subtitles",
    [
        ("[Subs French]", [], ["fr-FR"]),
        ("[VFQ]", ["fr-CA"], []),
        ("[Audio Japanese] [Subs French]", ["ja-JP"], ["fr-FR"]),
    ],
)
def test_labelled_prefixes(prefix, audio, subtitles):
    result = parse_title(prefix + " Example.2024.1080p")
    assert result["audio_languages"] == audio
    assert result["subtitle_languages"] == subtitles


@pytest.mark.parametrize(
    "marker,expected",
    [("AAC", "AAC"), ("HE-AACv2", "HE-AACv2"), ("TrueHD", "TrueHD"), ("DTS-HD.MA", "DTS-HD MA")],
)
def test_attached_complex_channels(marker, expected):
    result = parse_title(f"Example.2024.1080p.{marker}7.1.4")
    assert result["audio"] == [expected]
    assert result["channels"] == ["7.1.4"]


CODECS = [
    ("DTS", "DTS Lossy"),
    ("DTS-HD MA", "DTS-HD MA"),
    ("DTS-HD HRA", "DTS-HD HRA"),
    ("DTS-X", "DTS-X"),
    ("AAC", "AAC"),
    ("HE-AAC", "HE-AAC"),
    ("HE-AACv2", "HE-AACv2"),
    ("TrueHD", "TrueHD"),
    ("DD+", "Dolby Digital Plus"),
    ("FLAC", "FLAC"),
]


@pytest.mark.parametrize("marker,expected", CODECS)
@pytest.mark.parametrize("channels", ["2.0", "5.1", "7.1.4", "5.1.2"])
@pytest.mark.parametrize("separator", [" ", ".", "_"])
def test_codecs_and_complete_channels(marker, expected, channels, separator):
    result = parse_title(
        "Example.S02E03.1080p.BluRay." + marker.replace(" ", separator) + separator + channels
    )
    assert result["audio"] == [expected]
    assert result["channels"] == [channels]


@pytest.mark.parametrize("left,right", list(itertools.permutations(CODECS, 2)))
def test_distinct_codec_occurrences_are_retained(left, right):
    result = parse_title(f"Example.2024.1080p.BluRay.{left[0]}.2.0.{right[0]}.5.1")
    assert set(result["audio"]) == {left[1], right[1]}


@pytest.mark.parametrize("left,right", [("5.1", "5.1.2"), ("7.1", "7.1.4"), ("5.1.2", "7.1.4")])
@pytest.mark.parametrize(
    "first,second", list(itertools.product(["AAC", "TrueHD", "DTS-HD MA"], repeat=2))
)
def test_distinct_channel_occurrences_are_retained(left, right, first, second):
    result = parse_title(f"Example.2024.1080p.{first}.{left}.{second}.{right}")
    assert set(result["channels"]) == {left, right}


@pytest.mark.parametrize(
    "marker,expected,profiles",
    [
        ("HDR10", ["HDR10"], []),
        ("HDR10+", ["HDR10+"], []),
        ("HLG", ["HLG"], []),
        ("DV P8.1", ["DV"], ["8.1"]),
        ("HDR10+ DV P8.1", ["DV", "HDR10+"], ["8.1"]),
        ("HDR HLG", ["HDR", "HLG"], []),
    ],
)
@pytest.mark.parametrize("separator", [" ", ".", "_"])
def test_hdr_and_explicit_dolby_vision_profile(marker, expected, profiles, separator):
    result = parse_title("Example.2024.2160p." + marker.replace(" ", separator))
    assert result["hdr"] == expected
    assert result.get("dolby_vision_profiles", []) == profiles


@pytest.mark.parametrize("marker", ["DV.P", "DoVi.Profile.", "Dolby.Vision.P"])
@pytest.mark.parametrize("profile", ["5", "7", "8", "8.1", "8.4"])
@pytest.mark.parametrize("resolution", ["480p", "720p", "1080p", "1080i", "2160p"])
def test_dolby_vision_profile_before_resolution(marker, profile, resolution):
    result = parse_title(f"Example.2024.{marker}{profile}.{resolution}.WEB-DL.x265-GRP")
    control = parse_title(f"Example.2024.{resolution}.{marker}{profile}.WEB-DL.x265-GRP")
    assert result.get("dolby_vision_profiles") == [profile]
    assert result == control


@pytest.mark.parametrize("profile", ["8.1.2", "8.123", "8.1234", "8.1.1080", "8.1.1080pixels"])
def test_dolby_vision_profile_does_not_truncate_numeric_suffixes(profile):
    result = parse_title(f"Example.2024.2160p.DV.P{profile}.WEB-DL.x265-GRP")
    assert result.get("dolby_vision_profiles", []) == []


@pytest.mark.parametrize(
    "title,expected",
    [
        (
            "La Saison Des Femmes.2015.1080p.BluRay",
            {
                "resolution": "1080p",
                "year": 2015,
                "quality": "BluRay",
                "episodes": [],
                "seasons": [],
                "title": "La",
            },
        ),
        (
            "Seinfeld.COMPLETE.SLOSUBS.DVDRip.XviD",
            {
                "quality": "DVDRip",
                "codec": "xvid",
                "complete": True,
                "episodes": [],
                "seasons": [],
                "title": "Seinfeld",
            },
        ),
        (
            "Heidi Audio Latino DVDRip [cap. 3 Al 18]",
            {"quality": "DVDRip", "episodes": [3], "seasons": [], "title": "Heidi"},
        ),
        (
            "[ Torrent9.cz ] The.InBetween.S01E10.FiNAL.HDTV.XviD-EXTREME.avi",
            {
                "container": "avi",
                "quality": "HDTV",
                "codec": "xvid",
                "group": "EXTREME",
                "seasons": [1],
                "episodes": [10],
                "site": "Torrent9.cz",
                "extension": "avi",
                "title": "The InBetween FiNAL -EXTREME",
            },
        ),
        (
            "Example.2024.1080p.H264-BEN.THE.MEN",
            {
                "resolution": "1080p",
                "year": 2024,
                "codec": "avc",
                "episodes": [],
                "seasons": [],
                "title": "Example",
            },
        ),
        (
            "The French Dispatch.2021.1080p.BluRay",
            {
                "resolution": "1080p",
                "year": 2021,
                "quality": "BluRay",
                "episodes": [],
                "seasons": [],
                "title": "The French Dispatch",
            },
        ),
        (
            "The HDR Experiment.2024.1080p",
            {
                "resolution": "1080p",
                "year": 2024,
                "episodes": [],
                "seasons": [],
                "title": "The HDR Experiment",
            },
        ),
    ],
)
def test_title_group_and_other_fields_remain_upstream(title, expected):
    result = parse_title(title)
    assert {k: v for k, v in result.items() if k not in EXTENDED_FIELDS} == expected


def test_calls_do_not_share_mutable_results():
    title = "Example.2024.1080p.JAPANESE.VOSTFR.DTS-HD.MA.7.1.4"
    expected = parse_title(title)
    result = parse_title(title)
    result["audio_languages"].clear()
    result["audio"].clear()
    assert parse_title(title) == expected
    assert "result_version" not in parse_title(title)


def test_custom_parser_uses_the_same_output():
    parser = Parser()
    add_defaults(parser)
    title = "Example.2024.1080p.VFQ"
    assert parser.parse(title) == parse_title(title)
    assert parser.parse(title)["audio_languages"] == ["fr-CA"]


def test_custom_handler_receives_match_context():
    parser = Parser()

    def custom(context):
        assert set(context) == {"title", "result", "matched"}

    parser.add_handler("custom", custom)
    parser.parse("Example")


def test_public_entry_points_have_no_output_mode():
    assert list(inspect.signature(parse_title).parameters) == ["raw_title", "translate_languages"]
    assert list(inspect.signature(Parser.parse).parameters) == [
        "self",
        "title",
        "translate_languages",
    ]


@pytest.mark.parametrize("translated", [False, True])
def test_cli_uses_the_same_output(translated):
    title = "Example.2024.1080p.VFQ.VOSTFR.DTS-HD.MA.7.1.4"
    command = [sys.executable, "-m", "PTT.cli", "parse", title]
    if translated:
        command.append("--translate-languages")
    result = subprocess.run(
        command, capture_output=True, text=True, encoding="utf-8", timeout=15, check=True
    )
    assert json.loads(result.stdout) == parse_title(title, translate_languages=translated)


@pytest.mark.parametrize("letters", list(itertools.product("mM", "uU", "lL", "tT", "iI")))
@pytest.mark.parametrize("suffix", ["", "-Subs", "-SUBS", "-subs", " Subs", ".Subs"])
def test_multi_is_case_insensitive_and_keeps_its_role(letters, suffix):
    result = parse_title("Example.S01E02.1080p.WEB-DL." + "".join(letters) + suffix)
    assert result["audio_languages"] == ([] if suffix else ["multi"])
    assert result["subtitle_languages"] == (["multi"] if suffix else [])


def test_display_languages_keep_regions_and_subtitle_roles():
    title = "Example.2024.1080p.VFQ.VOSTFR"
    result = parse_title(title, translate_languages=True)
    assert result["audio_languages"] == ["French (Canada)"]
    assert result["subtitle_languages"] == ["French (France)"]


@pytest.mark.parametrize("suffix", ["GB", "MB", "FPS", "Kbps"])
def test_complex_number_with_non_channel_unit_is_not_enriched(suffix):
    title = f"Example.2024.1080p.AAC.7.1.4{suffix}"
    result = parse_title(title)
    assert "7.1.4" not in result.get("channels", [])


def test_only_the_three_requested_features_are_added():
    title = "Example.2024.1080p.REPACK2.3D.HSBS.[French.SDH]"
    result = parse_title(title)
    assert not {"subtitle_details", "repack_numbers", "stereo_layout"}.intersection(result)


@pytest.mark.parametrize(
    "title", ["Forced Vengeance", "The Subs Club", "The Subtitle", "Undertekst"]
)
@pytest.mark.parametrize("coordinate", ["1982", "S02E03", "S01-S03"])
@pytest.mark.parametrize(
    "language,expected", [("JAPANESE", "ja-JP"), ("FRENCH", "fr-FR"), ("ENGLISH", "en-US")]
)
@pytest.mark.parametrize("separator", [" ", ".", "_"])
def test_title_words_do_not_assign_subtitle_languages(
    title, coordinate, language, expected, separator
):
    result = parse_title(separator.join((title, coordinate, "1080p", language)))
    assert result["audio_languages"] == [expected]
    assert result["subtitle_languages"] == []


@pytest.mark.parametrize(
    "title,audio,subtitles",
    [
        ("Atonement.2017.KOREAN.ENSUBBED.1080p.WEBRip.x264-VXTT", ["ko-KR"], ["en-US"]),
        ("[Eng Sub] Rebirth Ep #36 [8CF3ADFA].mkv", [], ["en-US"]),
        (
            "[OFFICIAL ENG SUB] Soul Land Episode 121-125 [1080p][Soft Sub][Web-DL][Douluo Dalu][斗罗大陆]",
            ["zh-CN"],
            ["en-US"],
        ),
        ("[TBox] Dragon Ball Z Full 1-291(Subbed Jap Vers)", ["ja-JP"], []),
        ("Forced Vengeance.1982.1080p.JAPANESE.VOSTFR", ["ja-JP"], ["fr-FR"]),
        ("[Subs French] Forced Vengeance.1982.1080p.JAPANESE", ["ja-JP"], ["fr-FR"]),
        ("Forced Vengeance.1982.1080p.[Subs French] [Audio Japanese]", ["ja-JP"], ["fr-FR"]),
        ("Forced Vengeance.1982.1080p.[Audio Japanese] [Subs French]", ["ja-JP"], ["fr-FR"]),
        ("Forced Vengeance.1982.1080p.[Audio Japanese] [French Forced]", ["ja-JP"], ["fr-FR"]),
        ("Forced Vengeance.1982.1080p.FRENCH.SUBBED", ["fr-FR"], []),
        ("Forced Vengeance.1982.1080p.JAPANESE.Multi-Subs", ["ja-JP"], ["multi"]),
    ],
)
def test_explicit_subtitle_roles_do_not_leak_into_audio(title, audio, subtitles):
    result = parse_title(title)
    assert result["audio_languages"] == audio
    assert result["subtitle_languages"] == subtitles


@pytest.mark.parametrize(
    "title,audio,subtitles",
    [
        (
            "Red Riding 1974 [2009 PAL DVD][En Subs[Sv.No.Fi]",
            ["en-US"],
            ["sv-SE", "no-NO", "fi-FI"],
        ),
        (
            "Comme une Image (Look at Me) [2004 PAL DVD][Fr Subs[Sv.Da.No]",
            ["fr-FR"],
            ["sv-SE", "da-DK", "no-NO"],
        ),
        ("2- English- {SDH}.srt", [], ["en-US"]),
        (
            "The.Prisoner.1967-1968.Complete.Series.Subs.English+Nordic",
            [],
            ["en-US", "da-DK", "fi-FI", "sv-SE", "no-NO"],
        ),
        ("Cowboy Bebop - 1080p BDrip Audio+sub MULTI (VF / VOSTFR)", ["fr-FR"], ["multi", "fr-FR"]),
        ("InuYasha.EP161.ptBR.subtitles.[inuplace.com.br].avi", [], ["pt-BR"]),
        ("[HR] Boku no Hero Academia 87 (S4-24) [1080p HEVC Multi-Subs] HR-GZ", [], ["multi"]),
    ],
)
def test_native_subtitle_blocks_preserve_their_roles(title, audio, subtitles):
    result = parse_title(title)
    assert set(result["audio_languages"]) == set(audio)
    assert set(result["subtitle_languages"]) == set(subtitles)


@pytest.mark.parametrize(
    "marker,audio,subtitles",
    [
        ("[Audio: Japanese] [English SDH]", ["ja-JP"], ["en-US"]),
        ("[Audio: Japanese] [English SDH] [Audio: English]", ["ja-JP", "en-US"], ["en-US"]),
        ("[Audio: Japanese] [Subtitles: English (SDH), French]", ["ja-JP"], ["en-US", "fr-FR"]),
        ("[Audio: Japanese] [Subtitles: English [SDH], French]", ["ja-JP"], ["en-US", "fr-FR"]),
        ("[Audio: Japanese] [Subtitles: English (Forced), French]", ["ja-JP"], ["en-US", "fr-FR"]),
        ("[Audio: English] [Subs: French] [Audio: Japanese]", ["en-US", "ja-JP"], ["fr-FR"]),
        ("[Audio: English (AAC), Japanese] [Subs: French]", ["en-US", "ja-JP"], ["fr-FR"]),
        ("English Subs[French, German]", ["en-US"], ["fr-FR", "de-DE"]),
        ("[English Subs] [Audio: Japanese]", ["ja-JP"], ["en-US"]),
        ("[English SDH] JAPANESE", ["ja-JP"], ["en-US"]),
    ],
)
@pytest.mark.parametrize("separator", [" ", ".", "_"])
@pytest.mark.parametrize("casing", [str, str.lower, str.upper])
def test_nested_roles_and_overlapping_language_matches(marker, audio, subtitles, separator, casing):
    result = parse_title("Example.2024.1080p." + casing(marker).replace(" ", separator))
    assert set(result["audio_languages"]) == set(audio)
    assert set(result["subtitle_languages"]) == set(subtitles)


@pytest.mark.parametrize(
    "annotation", ["(SDH)", "[SDH]", "{SDH}", "(Forced)", "[Forced]", "{Forced}"]
)
@pytest.mark.parametrize("separator", [" ", ".", "_"])
@pytest.mark.parametrize("audio_english", [False, True])
def test_delimited_subtitle_annotation_does_not_invent_audio(annotation, separator, audio_english):
    marker = f"[Audio: Japanese] [English {annotation}]"
    if audio_english:
        marker += " [Audio: English]"
    result = parse_title("Example.S02E03.1080p." + marker.replace(" ", separator))
    assert set(result["audio_languages"]) == ({"ja-JP", "en-US"} if audio_english else {"ja-JP"})
    assert result["subtitle_languages"] == ["en-US"]


@pytest.mark.parametrize(
    "marker,audio,subtitles",
    [
        ("English Subs[French,German] HE-AACv2", ["en-US"], ["fr-FR", "de-DE"]),
        ("English Subs[French,German] JAPANESE HE-AACv2", ["en-US", "ja-JP"], ["fr-FR", "de-DE"]),
        ("English Subs[French,German] HEBREW HE-AACv2", ["en-US", "he-IL"], ["fr-FR", "de-DE"]),
        (
            "English Subs[French,German] [Audio: he] HE-AACv2",
            ["en-US", "he-IL"],
            ["fr-FR", "de-DE"],
        ),
        ("[Audio: Japanese] [Subs: he] HE-AACv2", ["ja-JP"], ["he-IL"]),
        ("[Audio: Japanese] Subs: French HE-AACv2", ["ja-JP"], ["fr-FR"]),
        ("[Audio: Japanese] Subs: French HE-AACv2 he", ["ja-JP"], ["fr-FR", "he-IL"]),
        ("[Audio: Japanese] [Subs: French HE-AACv2]", ["ja-JP"], ["fr-FR"]),
    ],
)
@pytest.mark.parametrize("separator", [" ", ".", "_"])
def test_language_roles_end_with_their_list_and_exclude_codec_spans(
    marker, audio, subtitles, separator
):
    result = parse_title("Example.S02E03.1080p." + marker.replace(" ", separator))
    assert set(result["audio_languages"]) == set(audio)
    assert set(result["subtitle_languages"]) == set(subtitles)
    assert result["audio"] == ["HE-AACv2"]


@pytest.mark.parametrize(
    "marker,audio,subtitles",
    [
        ("[Audio: Japanese] [English] (Forced)", ["ja-JP", "en-US"], []),
        ("[Audio: Japanese] [English (Forced Vengeance)]", ["ja-JP", "en-US"], []),
        ("[Audio: Japanese] [English (AAC)]", ["ja-JP", "en-US"], []),
        ("[Audio: English] [Subs: French (SDH)]", ["en-US"], ["fr-FR"]),
        ("[Audio: English] [Subs: French (Forced)]", ["en-US"], ["fr-FR"]),
    ],
)
def test_subtitle_annotations_do_not_cross_or_consume_unrelated_blocks(marker, audio, subtitles):
    result = parse_title("Example.S02E03.1080p." + marker)
    assert set(result["audio_languages"]) == set(audio)
    assert set(result["subtitle_languages"]) == set(subtitles)


@pytest.mark.parametrize(
    "language,tag",
    [
        ("French", "fr-FR"),
        ("German", "de-DE"),
        ("Spanish", "es-ES"),
        ("Japanese", "ja-JP"),
        ("Korean", "ko-KR"),
        ("Russian", "ru-RU"),
        ("fr-CA", "fr-CA"),
        ("English", "en-US"),
    ],
)
@pytest.mark.parametrize("annotation", ["(SDH)", "(Forced)", "{SDH}"])
@pytest.mark.parametrize("separator", [" ", ".", "_"])
def test_prefix_annotation_keeps_subtitle_role_and_separate_audio(
    language, tag, annotation, separator
):
    prefix = f"[{language} {annotation}]".replace(" ", separator)
    result = parse_title(prefix + " Example.S02E03.1080p.JAPANESE")
    assert result["audio_languages"] == ["ja-JP"]
    assert result["subtitle_languages"] == [tag]


@pytest.mark.parametrize(
    "prefix,group",
    [
        ("[French]", "French"),
        ("[French-Team]", "French-Team"),
        ("[French (AAC)]", "French ()"),
        ("[French (Forced Vengeance)]", "French (Forced Vengeance)"),
        ("[French-Team (SDH)]", "French-Team (SDH)"),
        ("[French (SDH) Team]", "French (SDH) Team"),
        ("[Team French (SDH)]", "Team French (SDH)"),
        ("[French] (SDH)", "French"),
    ],
)
def test_ambiguous_prefix_is_not_certified_as_a_subtitle_annotation(prefix, group):
    title = prefix + " Example.S02E03.1080p.JAPANESE"
    result = parse_title(title)
    assert result["subtitle_languages"] == []
    assert result.get("group") == group


@pytest.mark.parametrize(
    "language,tag", [("German", "de-DE"), ("Japanese", "ja-JP"), ("French", "fr-FR")]
)
def test_prefix_annotation_does_not_remove_separate_audio_in_the_same_language(language, tag):
    result = parse_title(f"[{language} (SDH)] Example.2024.1080p.{language.upper()}")
    assert result["audio_languages"] == [tag]
    assert result["subtitle_languages"] == [tag]
