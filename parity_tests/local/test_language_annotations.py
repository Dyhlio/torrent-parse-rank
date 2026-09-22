import pytest
from PTT import parse_title
from PTT.parse import LANGUAGES_TRANSLATION_TABLE, translate_langs
from RTN import parse


@pytest.mark.parametrize("code,expected", LANGUAGES_TRANSLATION_TABLE.items())
def test_existing_public_translation_table_is_honored(code, expected):
    assert translate_langs([code]) == [expected]


@pytest.mark.parametrize(
    "languages,expected",
    [
        (["fr-CA", "fr-FR"], ["French (Canada)", "French (France)"]),
        (["es-419", "multi"], ["Spanish (Latin America)", "Multiple languages"]),
        (["invalid", "", "la"], ["Latino"]),
    ],
)
def test_regional_and_short_code_translation(languages, expected):
    assert translate_langs(languages) == expected


@pytest.mark.parametrize(
    "language,tag",
    [
        ("French", "fr-FR"),
        ("German", "de-DE"),
        ("English", "en-US"),
        ("Japanese", "ja-JP"),
        ("Korean", "ko-KR"),
        ("Spanish", "es-ES"),
        ("fr-CA", "fr-CA"),
        ("zh-Hant-TW", "zh-Hant-TW"),
    ],
)
@pytest.mark.parametrize("annotation", ["(SDH)", "(Forced)", "[SDH]", "{SDH}", "SDH"])
@pytest.mark.parametrize("separator", [" ", ".", "_"])
def test_subtitle_prefix_is_not_a_release_group(language, tag, annotation, separator):
    title = f"[{language}{separator}{annotation}] Dune.2021.1080p.JAPANESE"
    result = parse_title(title)
    assert result["audio_languages"] == ["ja-JP"]
    assert result["subtitle_languages"] == [tag]
    assert result.get("group") is None
    assert result.get("site") is None
    assert result["title"] == "Dune"
    assert parse(title).group is None


@pytest.mark.parametrize(
    "prefix,expected",
    [
        ("[French-Team]", "French-Team"),
        ("[Team French (SDH)]", "Team French (SDH)"),
        ("[French (SDH) Team]", "French (SDH) Team"),
        ("[French-Team (SDH)]", "French-Team (SDH)"),
        ("[French (Forced Vengeance)]", "French (Forced Vengeance)"),
        ("[French] (SDH)", "French"),
        ("[SubsPlease]", "SubsPlease"),
        ("[SDH]", "SDH"),
        ("[Forced]", "Forced"),
        ("[YTS.MX]", None),
    ],
)
def test_group_controls_are_preserved(prefix, expected):
    result = parse_title(prefix + " Dune.2021.1080p.JAPANESE")
    assert result.get("group") == expected


@pytest.mark.parametrize(
    "marker", ["VFQ", "VFF", "VOF", "LATINO", "BENGALI", "MULTi", "Multi-Subs"]
)
def test_standard_parsing_and_rtn_use_identical_languages(marker):
    title = f"Dune.2021.1080p.{marker}.BluRay"
    result = parse_title(title)
    dto = parse(title)
    assert dto.audio_languages == result["audio_languages"]
    assert dto.subtitle_languages == result["subtitle_languages"]


@pytest.mark.parametrize("language", ["fr-CA", "en-US", "en-AU", "en-NZ"])
@pytest.mark.parametrize("annotation", ["[SDH]", "(SDH)", "{Forced}"])
def test_labelled_language_region_is_not_a_country(language, annotation):
    result = parse_title(f"[{language} {annotation}] Dune.2021.1080p.JAPANESE")
    assert result["title"] == "Dune"
    assert result.get("country") is None
    assert result["subtitle_languages"] == [language]


@pytest.mark.parametrize("language,country", [("fr-CA", "US"), ("en-US", "UK"), ("en-AU", "NZ")])
def test_real_country_after_labelled_language_is_still_found(language, country):
    result = parse_title(f"[{language} [SDH]] The.Office.{country}.S01E01.1080p.JAPANESE")
    assert result["title"] == "The Office"
    assert result["country"] == country
    assert result["seasons"] == [1]
    assert result["episodes"] == [1]
    assert result["subtitle_languages"] == [language]


@pytest.mark.parametrize("country", ["US", "UK", "AU", "NZ", "CA"])
def test_unlabelled_country_keeps_native_behavior(country):
    result = parse_title(f"The.Office.{country}.S01E01.1080p")
    assert result["title"] == "The Office"
    assert result["country"] == country


def test_region_inside_real_group_is_not_filtered():
    result = parse_title("[CA-Team] Dune.2021.1080p")
    assert result["title"] == "Dune"
    assert result["country"] == "CA"
    assert result["group"] == "CA-Team"
