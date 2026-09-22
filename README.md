<h1 align="center" id="title">torrent-parse-rank</h1>

<p align="center">
  A high-performance Rust implementation of The Best Damn Filename Parser You've Ever Used!
</p>

<p align="center">
  <img src="https://img.shields.io/badge/python-3.10%2B-3776AB?style=flat-square&logo=python&logoColor=white" />
  <img src="https://img.shields.io/badge/rust-core-000000?style=flat-square&logo=rust&logoColor=white" />
  <img src="https://img.shields.io/badge/license-GPLv3-blue?style=flat-square" />
</p>

## Credits

- Upstream PTT reference: https://github.com/dreulavelle/PTT
- Upstream RTN reference: https://github.com/dreulavelle/rank-torrent-name
- Rust implementation: https://github.com/g0ldyy/torrent-parse-rank
- Regional-language data: https://github.com/rspeer/langcodes (CLDR/IANA data).

This fork retains the upstream licence and attributions. Its version 1.0.0 adds the
detailed metadata contract below; it is not the upstream PyPI release.

## What You Get

- Fast `PTT` parsing API for raw torrent names.
- `RTN` ranking/filtering API with configurable quality rules.
- Python-first usage (`from PTT import parse_title`, `from RTN import RTN`).
- Rust performance without changing your Python integration style.

## Install In Your Python Project

### Option 1: Local path

```bash
uv add --editable /absolute/path/to/torrent-parse-rank
```

### Option 2: This fork

```bash
uv add "torrent-parse-rank@git+https://github.com/Dyhlio/torrent-parse-rank"
```

Notes:

- Installing from source requires a Rust toolchain (`cargo`) available in `PATH`.
- The import names are `PTT` and `RTN`.
- The Git URL above installs this fork, including its detailed metadata additions.
- Do not coinstall another distribution providing the `PTT` or `RTN` packages.

## Detailed Metadata

`audio_languages` and `subtitle_languages` replace the result's `languages` field.
Explicit regional tags are retained; otherwise the bundled CLDR default supplies
a region. This convention does not prove which regional dub a file contains.
`multi` is a marker, not a language, and remains separate for each role.

| Input after the title | Result |
| --- | --- |
| VFQ / VFF | audio: fr-CA / fr-FR |
| JAPANESE VOSTFR | audio: ja-JP; subtitles: fr-FR |
| MULTi / Multi-Subs | audio: multi / subtitles: multi |
| DTS-HD MA / HE-AACv2 | explicit audio format retained |
| 7.1.4 / DV.Profile.8.1 | full channel layout / explicit DV profile |

Language preferences still live in `settings.languages` and apply to audio:
`fr` matches both `fr-FR` and `fr-CA`; `fr-CA` does not match `fr-FR`.
Optional `dts_hd` and `dts_x` policies fall back to the existing lossy/lossless
families unless explicitly configured. A refined label replaces the overlapping
generic detection; distinct codecs retain their individual ranking scores.

`ParsedData.three_d` serializes as `3d`. The retired `languages` and `_3d`
inputs are rejected. There is no output-version switch. Parsing, CLI, ranking and
batch APIs use the same detailed contract.

The native episode rules are retained: E02E04 means [2, 4], E02-E04 means [2, 3, 4],
and an absolute episode does not imply season 1. No collection-title cleanup or
external media-ID lookup is added.

Custom Python handlers retain TPR's contract: they run after the native defaults
and receive `title`, `result` and `matched`. The working `title` reflects removals
already made by native handlers. They do not expose the Python PTT
fork's internal match-tracking objects or its before-default handler ordering.

## Quickstart

### 1) Parse a torrent title (PTT)

```python
from PTT import parse_title

data = parse_title("The.Simpsons.S01E01.1080p.BluRay.x265", False)
print(data["title"])  # The Simpsons
print(data["resolution"])  # 1080p
```

### 2) Parse + rank a candidate (RTN)

```python
from RTN import RTN
from RTN.models import DefaultRanking, SettingsModel

rtn = RTN(SettingsModel(), DefaultRanking())
item = rtn.rank(
    raw_title="The Walking Dead S05E03 720p x264-ASAP",
    infohash="c08a9ee8ce3a5c2c08865e2b05406273cabc97e7",
)

print(item.fetch)  # True/False after filters
print(item.rank)  # computed rank score
print(item.data.parsed_title)
```

### 3) Parse only (RTN)

```python
from RTN import parse

parsed = parse("Oppenheimer.2023.2160p.REMUX.DV.HDR10Plus.TrueHD.7.1.HEVC")
print(parsed.resolution)
print(parsed.codec)
```

## Development

```bash
cd torrent-parse-rank
uv sync --group dev
uv run maturin develop --release
```

## Quality / Tests

```bash
cd torrent-parse-rank
./scripts/quality_gate.sh
./scripts/quality_gate.sh --full
```

`--full` includes the frozen reference corpus and scalar/batch parity tests.
Both variants rebuild the optimized native extension before running Python tests.
The corpus records its reference revisions and the approved field-composition policy.
The native handler catalogue is authoritative; the upstream extractor writes to a
separate comparison file. `scripts/run_parity_tests.sh` is an optional upstream
API audit: unchanged upstream tests still expect the retired output contract and
are not the acceptance suite for this fork.

Regenerate language data with `uv run python scripts/generate_language_data.py`;
the dev dependencies pin the data versions, and `--check` verifies reproducibility.

## Benchmarks

The numbers below describe the original Rust port, **not this enriched fork**.
Re-run the benchmark after changing parsing or ranking policies.

| Parser (N=30,000) | Upstream Python (items/s) | Rust port (items/s) | Speedup | Upstream p50 (ms) | Rust p50 (ms) |
|---|---:|---:|---:|---:|---:|
| `PTT.parse_title` | 1,815.6 | 40,355.6 | 22.23x | 0.556 | 0.024 |
| `RTN.parse` | 1,708.8 | 30,284.9 | 17.72x | 0.590 | 0.032 |

Full benchmark report: [`benchmarks/README.md`](benchmarks/README.md)
