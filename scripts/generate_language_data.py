"""Generate the regional-language snapshot from langcodes' bundled CLDR data."""

import argparse
import json
from pathlib import Path
from string import ascii_uppercase

from langcodes import Language, tag_is_valid
from langcodes.data_dicts import ALL_SCRIPTS, LANGUAGE_REPLACEMENTS, LIKELY_SUBTAGS

ROOT = Path(__file__).resolve().parents[1]
CODES = "en ja zh ru ar pt es fr de it ko hi bn pa mr gu ta te kn ml th vi id tr he fa uk el lt lv et pl cs sk hu ro bg sr hr sl nl da fi sv no ms".split()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    defaults = {}
    for code in CODES:
        defaults[code] = Language.get(code).maximize().territory
    for tag in LIKELY_SUBTAGS:
        parts = tag.split("-")
        if len(parts) == 2 and parts[0] in CODES and len(parts[1]) == 4:
            defaults[tag] = Language.get(tag).maximize().territory
    territories = {}
    for code in [a + b for a in ascii_uppercase for b in ascii_uppercase] + [
        f"{n:03}" for n in range(1000)
    ]:
        if tag_is_valid("en-" + code):
            territories[code] = Language.get("en-" + code).territory
    aliases = {code: code for code in CODES}
    for code, target in LANGUAGE_REPLACEMENTS.items():
        if len(code) <= 3 and "-" not in code and target in CODES:
            aliases[code] = target
    payload = {
        "defaults": defaults,
        "languages": aliases,
        "territories": territories,
        "scripts": sorted(ALL_SCRIPTS),
        "names": {code: Language.get(code).display_name("en") for code in CODES},
        "territory_names": {
            code: Language.make(territory=code).territory_name("en")
            for code in set(territories.values())
        },
        "script_names": {
            code: Language.make(script=code).script_name("en") for code in ALL_SCRIPTS
        },
    }
    path = ROOT / "crates/ptt-core/data/languages.json"
    content = json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    if args.check:
        if path.read_text(encoding="utf8") != content:
            raise SystemExit("Regional-language snapshot is stale")
    else:
        path.write_text(content, encoding="utf8")


if __name__ == "__main__":
    main()
