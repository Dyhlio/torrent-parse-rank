use std::collections::{HashMap, HashSet};

use once_cell::sync::Lazy;
use pcre2::bytes::Regex;
use serde::Deserialize;
use serde_json::{Map, Value};

use crate::{ParseError, compile_regex};

macro_rules! re {
    ($pattern:expr) => {{
        static PATTERN: Lazy<Regex> =
            Lazy::new(|| compile_regex($pattern, true).expect("valid metadata regex"));
        &*PATTERN
    }};
}

#[derive(Clone, Debug)]
pub(crate) struct Record {
    pub field: String,
    pub start: usize,
    pub end: usize,
    pub value: Value,
}

#[derive(Deserialize)]
struct LanguageData {
    defaults: HashMap<String, String>,
    languages: HashMap<String, String>,
    territories: HashMap<String, String>,
    scripts: HashSet<String>,
    names: HashMap<String, String>,
    territory_names: HashMap<String, String>,
    script_names: HashMap<String, String>,
}

static LANGUAGE_DATA: Lazy<LanguageData> = Lazy::new(|| {
    serde_json::from_str(include_str!("../data/languages.json")).expect("valid language data")
});

fn strings(value: Option<&Value>) -> Vec<String> {
    value
        .and_then(Value::as_array)
        .into_iter()
        .flatten()
        .filter_map(Value::as_str)
        .map(str::to_owned)
        .collect()
}

fn unique(values: impl IntoIterator<Item = String>) -> Vec<String> {
    let mut seen = HashSet::new();
    values
        .into_iter()
        .filter(|value| seen.insert(value.clone()))
        .collect()
}

fn set_strings(result: &mut Map<String, Value>, field: &str, values: Vec<String>) {
    result.insert(
        field.to_owned(),
        Value::Array(unique(values).into_iter().map(Value::String).collect()),
    );
}

fn spans(pattern: &Regex, text: &str) -> Result<Vec<(usize, usize, String)>, ParseError> {
    pattern
        .captures_iter(text.as_bytes())
        .map(|capture| {
            let capture = capture.map_err(|error| ParseError::Regex(error.to_string()))?;
            let whole = capture.get(0).expect("whole capture");
            let value = capture.get(1).unwrap_or(whole);
            Ok((
                whole.start(),
                whole.end(),
                text[value.start()..value.end()].to_owned(),
            ))
        })
        .collect()
}

fn has(pattern: &Regex, text: &str) -> bool {
    pattern.is_match(text.as_bytes()).unwrap_or(false)
}

fn full(pattern: &Regex, text: &str) -> bool {
    pattern
        .find(text.as_bytes())
        .ok()
        .flatten()
        .is_some_and(|m| m.start() == 0 && m.end() == text.len())
}

fn overlap(a: (usize, usize), b: (usize, usize)) -> bool {
    a.0 < b.1 && b.0 < a.1
}

pub(crate) fn regional_language(code: &str) -> Option<String> {
    if code == "multi" {
        return Some(code.to_owned());
    }
    if code == "la" {
        return Some("es-419".to_owned());
    }
    let parts: Vec<_> = code.split('-').collect();
    let base = LANGUAGE_DATA.languages.get(&parts[0].to_lowercase())?;
    let mut script = None;
    let mut territory = None;
    for part in &parts[1..] {
        if part.len() == 4 && part.bytes().all(|c| c.is_ascii_alphabetic()) && script.is_none() {
            let normalized = format!("{}{}", part[..1].to_uppercase(), part[1..].to_lowercase());
            if !LANGUAGE_DATA.scripts.contains(&normalized) {
                return None;
            }
            script = Some(normalized);
        } else if territory.is_none() {
            territory = Some(LANGUAGE_DATA.territories.get(&part.to_uppercase())?.clone());
        } else {
            return None;
        }
    }
    let prefix = match script {
        Some(script) => format!("{base}-{script}"),
        None => base.clone(),
    };
    let territory = territory.or_else(|| {
        LANGUAGE_DATA
            .defaults
            .get(&prefix)
            .or_else(|| LANGUAGE_DATA.defaults.get(base))
            .cloned()
    })?;
    Some(format!("{prefix}-{territory}"))
}

pub(crate) fn language_name(code: &str) -> Option<String> {
    if code == "multi" {
        return Some("Multiple languages".to_owned());
    }
    let mut parts = code.split('-');
    let base = parts.next()?;
    let name = LANGUAGE_DATA.names.get(base)?;
    let qualifiers: Vec<_> = parts
        .filter_map(|part| {
            LANGUAGE_DATA
                .script_names
                .get(part)
                .or_else(|| LANGUAGE_DATA.territory_names.get(part))
        })
        .map(String::as_str)
        .collect();
    Some(if qualifiers.is_empty() {
        name.clone()
    } else {
        format!("{name} ({})", qualifiers.join(", "))
    })
}

pub(crate) struct Details<'a> {
    title: &'a str,
    records: &'a [Record],
    title_end: usize,
    blocks: Vec<(usize, usize)>,
}

impl<'a> Details<'a> {
    pub(crate) fn is_labelled_language_region(
        &self,
        span: (usize, usize),
    ) -> Result<bool, ParseError> {
        Ok(spans(
            re!(r"(?<![\w-])([a-z]{2,3}-(?:[a-z]{4}-)?(?:[a-z]{2}|\d{3}))(?![\w-])"),
            self.title,
        )?
        .iter()
        .any(|(start, end, code)| {
            *start < span.0
                && span.1 == *end
                && regional_language(code).is_some()
                && self.labelled((*start, *end))
        }))
    }

    pub(crate) fn has_labelled_languages(&self) -> bool {
        LANGUAGE_PATTERNS.iter().any(|(_, pattern)| {
            spans(pattern, self.title)
                .unwrap_or_default()
                .into_iter()
                .any(|(start, end, _)| self.labelled((start, end)))
        }) || spans(
            re!(r"(?<![\w-])([a-z]{2,3}-(?:[a-z]{4}-)?(?:[a-z]{2}|\d{3}))(?![\w-])"),
            self.title,
        )
        .unwrap_or_default()
        .into_iter()
        .any(|(start, end, code)| regional_language(&code).is_some() && self.labelled((start, end)))
    }

    pub(crate) fn new(title: &'a str, records: &'a [Record], title_end: usize) -> Self {
        let mut stack = Vec::new();
        let mut blocks = Vec::new();
        for (index, ch) in title.char_indices() {
            if "[({".contains(ch) {
                stack.push((ch, index));
            } else if let Some(&(open, start)) = stack.last()
                && matches!((open, ch), ('[', ']') | ('(', ')') | ('{', '}'))
            {
                blocks.push((start, index));
                stack.pop();
            }
        }
        blocks.extend(stack.into_iter().map(|(_, start)| (start, title.len())));
        blocks.sort_unstable_by(|a, b| b.cmp(a));
        Self {
            title,
            records,
            title_end,
            blocks,
        }
    }

    fn context_text(&self, start: usize, end: usize) -> String {
        let mut text = self.title.as_bytes()[start..end].to_vec();
        for &(mut left, right) in &self.blocks {
            if start <= right && right < end {
                if left >= start {
                    let prefix = &self.title[start..left];
                    if let Ok(labels) = spans(
                        re!(
                            r"\b(audio|dub(?:bed|lado)?|subs?(?:titles?)?|sdh|forced|leg(?:endado|endas?)?|undertekst)\b[ .,:-]*$"
                        ),
                        prefix,
                    ) && let Some((offset, _, label)) = labels.last()
                        && self.is_language_list(start + offset + label.len())
                    {
                        left = start + offset;
                    }
                }
                let left = left.max(start);
                text[left - start..=right - start].fill(b' ');
            }
        }
        String::from_utf8(text).expect("masked complete UTF-8 blocks")
    }

    fn is_language_list(&self, start: usize) -> bool {
        let suffix = &self.title[start..];
        let Ok(Some(opening)) = re!(r"^(?:[ .,:-]*[\[({]|[ .-]*:)\s*").find(suffix.as_bytes())
        else {
            return false;
        };
        let start = start + opening.end();
        if self
            .records
            .iter()
            .any(|r| r.field == "languages" && r.start == start)
        {
            return true;
        }
        LANGUAGE_PATTERNS.iter().any(|(_, pattern)| {
            pattern
                .find(&self.title.as_bytes()[start..])
                .ok()
                .flatten()
                .is_some_and(|m| m.start() == 0)
        })
    }

    fn subtitle_annotation(&self, end: usize, limit: Option<usize>) -> bool {
        let suffix = &self.title[end..limit.unwrap_or(self.title.len())];
        if let Ok(Some(annotation)) = re!(r"^[ .,:-]*(?:sdh|forced)\b").find(suffix.as_bytes())
            && (limit.is_none() || full(re!(r"[ .,:-]*"), &suffix[annotation.end()..]))
        {
            return true;
        }
        self.blocks.iter().any(|&(left, right)| {
            end <= left
                && right < limit.unwrap_or(self.title.len())
                && full(re!(r"[ .,:-]*"), &self.title[end..left])
                && (limit.is_none()
                    || full(re!(r"[ .,:-]*"), &self.title[right + 1..limit.unwrap()]))
                && full(re!(r"\s*(?:sdh|forced)\s*"), &self.title[left + 1..right])
        })
    }

    fn labelled(&self, span: (usize, usize)) -> bool {
        self.blocks.iter().any(|&(left, right)| {
            left < span.0 && span.1 <= right && {
                let prefix = self.context_text(left + 1, span.0);
                has(role_pattern(), &prefix)
                    || full(
                        re!(r"[ .,:-]*(?:subs?(?:titles?)?|SDH|FORCED)[ .,:-]*"),
                        &self.title[span.1..right],
                    )
                    || (full(re!(r"[ .,:-]*"), &prefix)
                        && self.subtitle_annotation(span.1, Some(right)))
            }
        })
    }

    fn metadata_position(&self, span: (usize, usize)) -> bool {
        if self.records.iter().any(|r| {
            matches!(
                r.field.as_str(),
                "languages" | "audio" | "channels" | "hdr" | "subbed" | "dubbed"
            ) && overlap(span, (r.start, r.end))
        }) {
            return true;
        }
        if self.labelled(span) {
            return true;
        }
        if self.records.iter().any(|r| {
            matches!(r.field.as_str(), "group" | "site") && r.start <= span.0 && span.1 <= r.end
        }) {
            return false;
        }
        self.records.iter().any(|r| {
            matches!(
                r.field.as_str(),
                "year" | "resolution" | "seasons" | "episodes"
            ) && r.end <= span.0
        })
    }

    fn labels(&self, text: &str, audio_marker: bool) -> Vec<(usize, usize, String)> {
        spans(role_pattern(), text)
            .unwrap_or_default()
            .into_iter()
            .filter(|(start, end, _)| {
                !audio_marker
                    || has(re!(r"^[ .-]*[:\[({]"), &text[*end..])
                    || !has(re!(r"\bmulti(?:ple)?[ .-]*$"), &text[..*start])
            })
            .collect()
    }

    fn subtitle_role(&self, mut span: (usize, usize)) -> bool {
        if has(
            re!(r"\.(?:srt|ass|ssa|vtt|sub|idx|smi|ttxt)\s*$"),
            self.title,
        ) {
            return true;
        }
        if let Some(&(_, right)) = self
            .blocks
            .iter()
            .find(|&&(left, right)| left < span.0 && span.0 < right)
        {
            span.1 = span.1.min(right);
        }
        let text = &self.title[span.0..span.1];
        let audio_marker = full(
            re!(r"VO[QF]|VQ|VF[FQIB2]?|FR2|TRUEFRENCH|MULTI(?:PLE)?(?:[ .-]*AUDIO)?"),
            text,
        );
        if full(re!(r"MULTI(?:PLE)?[ .-]*SUB(?:S|TITLES?|BED)?|MSUB"), text) {
            return true;
        }
        let list_label =
            self.is_language_list(span.1) && has(re!(r"\bsubs?(?:titles?)?\s*$"), text);
        if !list_label
            && has(
                re!(r"vost|sub|undertekst|\b(?:sdh|forced|leg(?:endado|endas?)?)\b"),
                text,
            )
        {
            return true;
        }
        if self.subtitle_annotation(span.1, None) {
            return true;
        }
        for &(left, right) in &self.blocks {
            if left < span.0 && span.1 <= right {
                let prefix = self.context_text(left + 1, span.0);
                if let Some((_, _, label)) = self.labels(&prefix, audio_marker).last() {
                    return !has(re!(r"^(?:audio|dub)"), label);
                }
            }
        }
        let mut start = 0;
        if !self.labelled(span) {
            if span.0 < self.title_end {
                return false;
            }
            start = self.title_end;
            for r in self.records {
                if matches!(
                    r.field.as_str(),
                    "year" | "resolution" | "seasons" | "episodes"
                ) && r.end <= span.0
                {
                    start = start.max(r.end);
                }
            }
        }
        let prefix = self.context_text(start, span.0);
        if let Some((_, end, label)) = self.labels(&prefix, audio_marker).last() {
            let block = self
                .blocks
                .iter()
                .filter(|&&(left, right)| left < span.0 && span.1 <= right)
                .map(|&(left, _)| left)
                .min();
            if block.is_none_or(|left| {
                start + end <= left && full(re!(r"[ .,:-]*"), &self.title[start + end..left])
            }) {
                return !has(re!(r"^(?:audio|dub)"), label);
            }
        }
        re!(r"^[ .,:-]*(subs?(?:titles?)?|sdh|forced|undertekst)\b")
            .find(&self.title.as_bytes()[span.1..])
            .ok()
            .flatten()
            .is_some_and(|m| !self.is_language_list(span.1 + m.end()))
    }
}

fn role_pattern() -> &'static Regex {
    re!(
        r"\b(audio|dub(?:bed|lado)?|subs?(?:titles?)?|sdh|forced|leg(?:endado|endas?)?|undertekst)\b"
    )
}

fn subtitle_annotation_group(group: &str, subtitles: &[String]) -> bool {
    if subtitles.is_empty() || !has(re!(r"\b(?:SDH|FORCED)\b"), group) {
        return false;
    }
    let annotation = re!(
        r"[ .,:-]*(?:SDH|FORCED|\(\s*(?:SDH|FORCED)\s*\)|\[\s*(?:SDH|FORCED)\s*\]|\{\s*(?:SDH|FORCED)\s*\})[ .,:-]*"
    );
    let recognized = |start: usize, end: usize, code: &str| {
        start == 0
            && full(annotation, &group[end..])
            && regional_language(code).is_some_and(|code| subtitles.contains(&code))
    };
    LANGUAGE_PATTERNS.iter().any(|(code, pattern)| {
        spans(pattern, group)
            .unwrap_or_default()
            .iter()
            .any(|(start, end, _)| recognized(*start, *end, code))
    }) || spans(
        re!(r"(?<![\w-])([a-z]{2,3}-(?:[a-z]{4}-)?(?:[a-z]{2}|\d{3}))(?![\w-])"),
        group,
    )
    .unwrap_or_default()
    .iter()
    .any(|(start, end, code)| recognized(*start, *end, code))
}

static LANGUAGE_PATTERNS: Lazy<Vec<(String, Regex)>> = Lazy::new(|| {
    crate::languages_translation_table()
        .into_iter()
        .map(|(code, name)| {
            let pattern = format!(r"\b(?:{name}|{code})\b");
            (
                code,
                compile_regex(&pattern, true).expect("valid language pattern"),
            )
        })
        .collect()
});

struct TechnicalPattern {
    field: &'static str,
    pattern: Regex,
    value: Option<&'static str>,
}

static TECHNICAL: Lazy<Vec<TechnicalPattern>> = Lazy::new(|| {
    [
        ("audio", r"DTS[ .:-]*HD[ .-]*MA(?:STER)?(?:[ .-]*AUDIO)?|DTS[ .-]*MA", Some("DTS-HD MA")),
        ("audio", r"DTS[ .:-]*HD[ .-]*(?:HRA?|HIGH[ .-]*RESOLUTION(?:[ .-]*AUDIO)?)", Some("DTS-HD HRA")),
        ("audio", r"DTS[ .:-]*X", Some("DTS-X")),
        ("audio", r"DTS[ .:-]*HD", Some("DTS-HD")),
        ("audio", r"HE[ .-]*AAC[ .-]*V2", Some("HE-AACv2")),
        ("audio", r"HE[ .-]*AAC", Some("HE-AAC")),
        ("audio", r"TRUE[ .-]*HD(?=\d[. ]\d)", Some("TrueHD")),
        ("audio", r"AAC(?=\d[. ]\d)", Some("AAC")),
        ("audio", r"DTS(?=\d[. ]\d)", Some("DTS Lossy")),
        ("channels", r"([1-9]\d?[. -][012][. -][1-9]\d?)(?:ch)?(?!\w|[.]\d(?!\d{2,3}[pi]\b))", None),
        ("hdr", r"HDR10(?:\+|[ .-]*PLUS)", Some("HDR10+")),
        ("hdr", r"HDR10", Some("HDR10")),
        ("hdr", r"HLG", Some("HLG")),
        ("dolby_vision_profiles", r"(?:DV|DOVI|DOLBY[ .-]*VISION)[ .-]*(?:PROFILE|PROFIL|P)[ .-]*(\d{1,2}(?:\.\d{1,2})?)(?!\.\d(?!\d{2,3}[pi]\b))", None),
    ].into_iter().map(|(field, pattern, value)| {
        let prefix = if field == "channels" { r"(?<!\d)" } else { r"(?<!\w)" };
        TechnicalPattern { field, pattern: compile_regex(&format!(r"{prefix}(?:{pattern})(?=$|\W|\d[. ]\d)"), true).expect("valid technical pattern"), value }
    }).collect()
});

impl Details<'_> {
    fn technical_matches(&self) -> Result<Vec<Record>, ParseError> {
        let mut output: Vec<Record> = Vec::new();
        for pattern in TECHNICAL.iter() {
            for (start, end, captured) in spans(&pattern.pattern, self.title)? {
                if !self.metadata_position((start, end))
                    || output.iter().any(|r| {
                        r.field == pattern.field && overlap((start, end), (r.start, r.end))
                    })
                {
                    continue;
                }
                if pattern.field == "channels" {
                    if has(
                        re!(r"^[ .-]*(?:[KMGT]i?[BO]|FPS|K?BPS)\b"),
                        &self.title[end..],
                    ) || has(re!(r"\b\d+[. -]$"), &self.title[..start])
                    {
                        continue;
                    }
                    if self.title[..start]
                        .chars()
                        .next_back()
                        .is_some_and(char::is_alphanumeric)
                        && !output.iter().any(|r| r.field == "audio" && r.end == start)
                        && !has(
                            re!(r"(?:AAC(?:v2)?|DTS|TRUE[ .-]*HD)$"),
                            &self.title[..start],
                        )
                    {
                        continue;
                    }
                }
                let value = pattern.value.map(str::to_owned).unwrap_or(captured);
                let value = if pattern.field == "channels" {
                    value.replace([' ', '-'], ".")
                } else {
                    value
                };
                output.push(Record {
                    field: pattern.field.to_owned(),
                    start,
                    end,
                    value: Value::String(value),
                });
                if pattern.field == "audio" {
                    let start = end
                        + self.title[end..]
                            .bytes()
                            .take_while(|b| b" .-".contains(b))
                            .count();
                    if let Some((_, length, value)) = spans(re!(r"^([1-9]\d?[. -][012][. -][1-9]\d?)(?:ch)?(?!\w|[.]\d(?!\d{2,3}[pi]\b))"), &self.title[start..])?.into_iter().next()
                        && !has(re!(r"^[ .-]*(?:[KMGT]i?[BO]|FPS|K?BPS)\b"), &self.title[start + length..]) {
                        output.push(Record { field: "channels".to_owned(), start, end: start + length, value: Value::String(value.replace([' ', '-'], ".")) });
                    }
                }
            }
        }
        Ok(output)
    }

    fn excluded_language_occurrence(&self, span: (usize, usize)) -> bool {
        self.records
            .iter()
            .any(|r| r.field == "site" && r.start <= span.0 && span.1 <= r.end)
            || spans(
                re!(r"\bwww\.[a-z0-9_-]+\.[a-z]+\b|\bsci[ .-]?fi\b"),
                self.title,
            )
            .unwrap_or_default()
            .iter()
            .any(|&(start, end, _)| start <= span.0 && span.1 <= end)
    }

    fn languages(
        &self,
        result: &mut Map<String, Value>,
        technical: &[Record],
    ) -> Result<(), ParseError> {
        let detected: Vec<_> = self
            .records
            .iter()
            .filter(|r| r.field == "languages")
            .filter_map(|r| r.value.as_str().map(|v| (r.start, r.end, v.to_owned())))
            .collect();
        let mut explicit = Vec::new();
        for (start, end, marker) in spans(
            re!(
                r"\b(VF2|FR2|VFQ|VFF|VFB|VOQ|VQ|TRUEFRENCH|SUBFRENCH|FRENCH|VOSTFR|VOSTA|ENGSUB|ESUBS?|MULTI(?:PLE)?[ .-]*SUB(?:S|TITLES?|BED)?|MSUB|MULTI(?:PLE)?[ .-]*AUDIO|MULTI)\b"
            ),
            self.title,
        )? {
            if !self.metadata_position((start, end)) {
                continue;
            }
            let marker = marker.to_uppercase();
            if marker == "FRENCH"
                && !self.labelled((start, end))
                && (start < self.title_end
                    || has(re!(r"\bsubbed\b"), self.title)
                    || self
                        .blocks
                        .iter()
                        .any(|&(left, right)| left < start && right == self.title.len()))
            {
                continue;
            }
            if marker == "VF2" || marker == "FR2" {
                explicit.push((start, end, "fr-FR".to_owned()));
                explicit.push((start, end, "fr-CA".to_owned()));
                continue;
            }
            let code = match marker.as_str() {
                "VFQ" | "VOQ" | "VQ" => "fr-CA",
                "VFB" => "fr-BE",
                "VFF" | "TRUEFRENCH" => "fr-FR",
                "VOSTFR" | "SUBFRENCH" | "FRENCH" => "fr",
                "VOSTA" | "ENGSUB" | "ESUB" | "ESUBS" => "en",
                _ => "multi",
            };
            explicit.push((start, end, code.to_owned()));
        }
        for (start, end, code) in spans(
            re!(r"(?<![\w-])([a-z]{2,3}-(?:[a-z]{4}-)?(?:[a-z]{2}|\d{3}))(?![\w-])"),
            self.title,
        )? {
            if regional_language(&code).is_some() && self.metadata_position((start, end)) {
                explicit.push((start, end, code));
            }
        }
        for (code, pattern) in LANGUAGE_PATTERNS.iter() {
            for (start, end, _) in spans(pattern, self.title)? {
                if technical
                    .iter()
                    .any(|r| overlap((start, end), (r.start, r.end)))
                {
                    continue;
                }
                if (self.subtitle_role((start, end)) || self.labelled((start, end)))
                    && self.metadata_position((start, end))
                    && !detected
                        .iter()
                        .chain(explicit.iter())
                        .any(|&(left, right, _)| overlap((start, end), (left, right)))
                {
                    explicit.push((start, end, code.clone()));
                }
            }
        }
        let mut entries: Vec<_> = detected
            .iter()
            .filter(|&&(start, end, _)| {
                !explicit
                    .iter()
                    .any(|&(left, right, _)| overlap((start, end), (left, right)))
            })
            .cloned()
            .collect();
        entries.extend(explicit.iter().cloned());
        entries.sort_by_key(|&(start, end, _)| (start, end));
        let mut audio = Vec::new();
        let mut subtitles = strings(result.get("subtitle_languages"));
        for (start, end, mut code) in entries {
            if self.excluded_language_occurrence((start, end)) {
                continue;
            }
            let text = &self.title[start..end];
            if code == "de"
                && text.eq_ignore_ascii_case("de")
                && !self.labelled((start, end))
                && !self.subtitle_role((start, end))
                && !(start >= self.title_end
                    && self.title[..start].ends_with('.')
                    && self.title[end..].starts_with('.'))
                && !(text == "DE" && spans(re!(r"(?-i:\b[A-Z]{2,3}\b)"), self.title)?.len() >= 3)
            {
                continue;
            }
            if code == "zh" && has(re!(r"\bCHT\b|hant|traditional"), text) {
                code = "zh-Hant".to_owned();
            } else if code == "zh" && has(re!(r"\bCHS\b|hans|simplified"), text) {
                code = "zh-Hans".to_owned();
            } else if code == "pt" && has(re!(r"\bBR\b|brazil"), text) {
                code = "pt-BR".to_owned();
            }
            if self.subtitle_role((start, end)) {
                subtitles.push(code);
            } else {
                audio.push(code);
            }
        }
        let mut recorded: HashSet<_> = detected.iter().map(|(_, _, code)| code.clone()).collect();
        recorded.extend(
            explicit
                .iter()
                .map(|(_, _, code)| code.split('-').next().unwrap_or(code).to_lowercase()),
        );
        for code in strings(result.get("languages")) {
            if !recorded.contains(&code) {
                if has(
                    re!(r"\.(?:srt|ass|ssa|vtt|sub|idx|smi|ttxt)\s*$"),
                    self.title,
                ) {
                    subtitles.push(code);
                } else {
                    audio.push(code);
                }
            }
        }
        result.remove("languages");
        for (field, values) in [
            ("audio_languages", audio),
            ("subtitle_languages", subtitles),
        ] {
            let explicit_bases: HashSet<_> = values
                .iter()
                .filter(|value| value.contains('-'))
                .map(|value| value.split('-').next().unwrap().to_lowercase())
                .collect();
            let values = values
                .iter()
                .filter(|value| {
                    value.contains('-') || !explicit_bases.contains(&value.to_lowercase())
                })
                .filter_map(|value| regional_language(value))
                .collect();
            set_strings(result, field, values);
        }
        Ok(())
    }

    pub(crate) fn apply(
        &self,
        result: &mut Map<String, Value>,
        translate: bool,
    ) -> Result<(), ParseError> {
        let technical = self.technical_matches()?;
        self.languages(result, &technical)?;
        if result
            .get("group")
            .and_then(Value::as_str)
            .is_some_and(|group| {
                subtitle_annotation_group(group, &strings(result.get("subtitle_languages")))
            })
        {
            result.remove("group");
        }
        for field in ["audio", "channels", "hdr", "dolby_vision_profiles"] {
            let changes: Vec<_> = technical.iter().filter(|r| r.field == field).collect();
            if changes.is_empty() {
                continue;
            }
            let recorded: Vec<_> = self.records.iter().filter(|r| r.field == field).collect();
            let mut values: Vec<String> = recorded
                .iter()
                .filter(|r| {
                    !changes
                        .iter()
                        .any(|change| overlap((r.start, r.end), (change.start, change.end)))
                })
                .filter_map(|r| r.value.as_str().map(str::to_owned))
                .collect();
            values.extend(
                strings(result.get(field))
                    .into_iter()
                    .filter(|value| !recorded.iter().any(|r| r.value.as_str() == Some(value))),
            );
            values.extend(
                changes
                    .iter()
                    .filter_map(|r| r.value.as_str().map(str::to_owned)),
            );
            set_strings(result, field, values);
        }
        if !strings(result.get("dolby_vision_profiles")).is_empty() {
            let mut hdr = strings(result.get("hdr"));
            hdr.push("DV".to_owned());
            set_strings(result, "hdr", hdr);
        }
        if result.get("quality").and_then(Value::as_str) == Some("HDTV") {
            let sources: Vec<_> = self
                .records
                .iter()
                .filter(|r| r.field == "quality" && r.value.as_str() == Some("HDTV"))
                .collect();
            if !sources.is_empty()
                && sources.iter().all(|r| {
                    technical.iter().any(|t| {
                        t.field == "audio"
                            && t.value.as_str().is_some_and(|v| v.starts_with("DTS-HD"))
                            && t.start <= r.start
                            && r.end <= t.end
                    })
                })
            {
                result.remove("quality");
            }
        }
        for (edition, field) in [
            ("Extended Edition", "extended"),
            ("Remastered", "remastered"),
        ] {
            if result.get("edition").and_then(Value::as_str) == Some(edition) {
                result.insert(field.to_owned(), Value::Bool(true));
            }
        }
        if translate {
            for field in ["audio_languages", "subtitle_languages"] {
                set_strings(
                    result,
                    field,
                    strings(result.get(field))
                        .iter()
                        .filter_map(|code| language_name(code))
                        .collect(),
                );
            }
        }
        Ok(())
    }
}
