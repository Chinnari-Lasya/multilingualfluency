import pytest
from hypothesis import given, settings, strategies as st

from gec_common import align, langs, text as T
from gec_common.errors import (InputTooLongError, InvalidInputError, LanguageMismatchError,
                               LanguageUndeterminedError, UnsupportedLanguageError)

SAMPLES = {
    "en": "I likes to swimming in the the pool .",
    "hi": "मैं स्कूल जाती है।",
    "te": "నేను పాఠశాలకు వెళ్ళి ఉంటాను.",
    "or": "ମୁଁ ସ୍କୁଲକୁ ଯାଏ ।",
    "ja": "私は学校を行きます。",
    "ko": "나는 학교에 갑니다.",
}


@pytest.mark.parametrize("lang,sample", SAMPLES.items())
def test_language_id_by_script(lang, sample):
    assert langs.detect_language(sample).language == lang


def test_tokenizer_keeps_indic_conjuncts_and_marks_together():
    toks = [t.text for t in align.tokenize("వెళ్ళి ఉంటాను.", "te")]
    assert toks == ["వెళ్ళి", "ఉంటాను", "."]  # not split at vowel signs / virama
    assert [t.text for t in align.tokenize("क्षत्रिय की", "hi")] == ["क्षत्रिय", "की"]


def test_japanese_is_char_level_with_latin_runs():
    assert [t.text for t in align.tokenize("私はPythonを使う", "ja")] == ["私", "は", "Python", "を", "使", "う"]


def test_declared_language_conflict_is_error_not_guess():
    with pytest.raises(LanguageMismatchError):
        langs.resolve_language("This is plainly English text here.", declared="hi")
    with pytest.raises(UnsupportedLanguageError):
        langs.resolve_language("hello world", declared="fr")
    with pytest.raises(LanguageUndeterminedError):
        langs.resolve_language("12345 !!! ???")


def test_han_only_is_flagged_ambiguous():
    r = langs.detect_language("学校")
    assert r.language == "ja" and r.confidence <= 0.5 and any("Chinese" in w for w in r.warnings)


def test_code_switching_dominant_script():
    r = langs.detect_language("मैं आज office जा रहा हूँ और meeting भी है")
    assert r.language == "hi" and r.mixed_script


@pytest.mark.parametrize("lang,src,tgt", [
    ("en", "I likes to swimming", "I like swimming"),
    ("en", "He went to school .", "He went to the school ."),
    ("en", "Hello, world", "Hello world"),
    ("hi", "मैं स्कूल जाती है।", "मैं स्कूल जाती हूँ।"),
    ("ko", "나는 학교을 갑니다.", "나는 학교를 갑니다."),
    ("ja", "私は学校を行きます。", "私は学校に行きます。"),
    ("en", "a  b", "a b"),
])
def test_roundtrip_examples(lang, src, tgt):
    edits = align.extract_edits(src, tgt, lang)
    assert align.apply_edits(src, edits) == tgt


def test_spans_are_tight_and_typed():
    e = align.extract_edits("He went to school .", "He went to the school .", "en")
    assert [(x.op, x.original, x.replacement) for x in e] == [("insert", "", "the ")]
    e = align.extract_edits("나는 학교을 갑니다.", "나는 학교를 갑니다.", "ko")
    assert [(x.original, x.replacement) for x in e] == [("을", "를")]  # syllable-level refinement
    e = align.extract_edits("Hello, world", "Hello world", "en")
    assert e[0].error_type == "PUNCT"


def test_apply_edits_rejects_overlap_and_stale_spans():
    e = align.extract_edits("a b c", "a x c", "en")[0]
    with pytest.raises(ValueError):
        align.apply_edits("a b c", [e, e.model_copy()])
    with pytest.raises(ValueError):
        align.apply_edits("zzz z z", [e])


ALPHABET = st.sampled_from(list("ab ,.క ా ్ మ ి ह ा ं は を 学 한 ग ॥ ") + ["  ", "the ", "క్ష", "ଓ"])


@pytest.mark.parametrize("lang", list(langs.SUPPORTED))
@settings(max_examples=400, deadline=None)
@given(a=st.lists(ALPHABET, max_size=14), b=st.lists(ALPHABET, max_size=14))
def test_roundtrip_property(lang, a, b):
    s, t = "".join(a), "".join(b)
    edits = align.extract_edits(s, t, lang)
    assert align.apply_edits(s, edits).strip() == t.strip()  # leading/trailing ws is not aligned


def test_normalize_and_guards():
    assert T.normalize("e\u0301") == "\u00e9"  # NFC
    assert "\u200d" in T.normalize("क्\u200dष")  # ZWJ preserved
    for bad in ["", "   \n", "a\x00b"]:
        with pytest.raises(InvalidInputError):
            T.normalize(bad)
    with pytest.raises(InputTooLongError):
        T.normalize("a" * 50, max_chars=10)


def test_sentence_split():
    txt = "First one. Second one! 3.5 is fine। नया वाक्य।\nline two 私は行く。次です。"
    spans = T.split_sentences(txt)
    assert [txt[a:b] for a, b in spans] == [
        "First one.", "Second one!", "3.5 is fine।", "नया वाक्य।", "line two 私は行く。", "次です。"]
