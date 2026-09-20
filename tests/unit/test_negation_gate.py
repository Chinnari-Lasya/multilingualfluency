import pytest
from gec_eval.metrics import mp_checks
from gec_o3.gates import hard_violations


@pytest.mark.parametrize("fn", [hard_violations, mp_checks])
def test_english_negation_detection_is_word_bounded_and_handles_double_negation(fn):
    assert fn("I know it", "I knew it", "en") == []                      # 'no' inside 'know' is NOT negation
    assert fn("She did not go", "She did go", "en") == ["negation_changed"]  # real polarity flip
    assert fn("She knows nothing", "She knows anything", "en") == ["negation_changed"]
    assert fn("She don't know nothing", "She didn't know anything", "en") == []  # double negation, same meaning
    assert "number_changed" in fn("I have 5 cats", "I have 6 cats", "en")
