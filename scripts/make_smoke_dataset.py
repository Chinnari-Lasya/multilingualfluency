"""Build data/smoke/smoke_v0.jsonl: a DEVELOPER-AUTHORED smoke fixture (NOT a benchmark).

Provenance / honesty:
* Written by the developer (an AI assistant working with the project owner), NOT by native speakers or
  professional annotators, and NOT validated by any independent educator. Telugu and Odia items in particular
  need native review before anyone relies on them.
* Purpose: exercise the pipeline + metric code end to end and make over-correction measurable (items whose
  reference == source are already-correct sentences). Scores on it must never be presented as validation.
"""
import json
import pathlib

META = {
    "name": "smoke_v0", "kind": "smoke_fixture", "license": "project-internal",
    "description": "Developer-authored smoke fixture, 10 items x 6 languages. NOT a benchmark; not native-speaker validated.",
}

# (lang, source, [references], tags)  -- reference == source means "already correct"
D = [
    # ------------------------------------------------------------------ English
    ("en", "I likes to swimming in the pool.", ["I like to swim in the pool.", "I like swimming in the pool."], ["error"]),
    ("en", "She don't know nothing about it.", ["She doesn't know anything about it.", "She does not know anything about it."], ["error"]),
    ("en", "He go to school yesterday.", ["He went to school yesterday."], ["error"]),
    ("en", "I have two dog and a cat.", ["I have two dogs and a cat."], ["error"]),
    ("en", "We was very happy to see the the teacher.", ["We were very happy to see the teacher."], ["error"]),
    ("en", "the meeting starts at 9 am tomorrow.", ["The meeting starts at 9 am tomorrow."], ["error"]),
    ("en", "i think he is right .", ["I think he is right."], ["error"]),
    ("en", "The weather is nice today.", ["The weather is nice today."], ["correct"]),
    ("en", "She did not go to the party with 5 friends.", ["She did not go to the party with 5 friends."], ["correct"]),
    ("en", "They have been waiting for the bus since morning.", ["They have been waiting for the bus since morning."], ["correct"]),
    # ------------------------------------------------------------------ Hindi
    ("hi", "मैं स्कूल जाती है।", ["मैं स्कूल जाती हूँ।", "मैं स्कूल जाती हूं।"], ["error"]),
    ("hi", "राम ने ने खाना खाया।", ["राम ने खाना खाया।"], ["error"]),
    ("hi", "वे किताबें पढ़ता है।", ["वे किताबें पढ़ते हैं।"], ["error"]),
    ("hi", "लड़कियाँ खेल रहा है।", ["लड़कियाँ खेल रही हैं।"], ["error"]),
    ("hi", "मुझे यह किताब बहुत अच्छी लगा।", ["मुझे यह किताब बहुत अच्छी लगी।"], ["error"]),
    ("hi", "वह घर जा रहा है |", ["वह घर जा रहा है।"], ["error"]),
    ("hi", "उसने ने मुझे बुलाया।", ["उसने मुझे बुलाया।"], ["error"]),
    ("hi", "आज मौसम अच्छा है।", ["आज मौसम अच्छा है।"], ["correct"]),
    ("hi", "मैं हर रोज़ सुबह जल्दी उठता हूँ।", ["मैं हर रोज़ सुबह जल्दी उठता हूँ।"], ["correct"]),
    ("hi", "हम कल दिल्ली जाएँगे।", ["हम कल दिल्ली जाएँगे।"], ["correct"]),
    # ------------------------------------------------------------------ Korean
    ("ko", "나는 학교을 갑니다.", ["나는 학교에 갑니다."], ["error"]),
    ("ko", "한국어는어렵다.", ["한국어는 어렵다."], ["error"]),
    ("ko", "저는 어제 친구를 만나요.", ["저는 어제 친구를 만났어요."], ["error"]),
    ("ko", "그는 책을 읽어요 .", ["그는 책을 읽어요."], ["error"]),
    ("ko", "어제 비가 와요.", ["어제 비가 왔어요."], ["error"]),
    ("ko", "저는 커피을 좋아합니다.", ["저는 커피를 좋아합니다."], ["error"]),
    ("ko", "동생이 학교가 갑니다.", ["동생이 학교에 갑니다."], ["error"]),
    ("ko", "오늘 날씨가 좋습니다.", ["오늘 날씨가 좋습니다."], ["correct"]),
    ("ko", "저는 매일 아침 운동을 합니다.", ["저는 매일 아침 운동을 합니다."], ["correct"]),
    ("ko", "친구와 함께 도서관에 갔어요.", ["친구와 함께 도서관에 갔어요."], ["correct"]),
    # ------------------------------------------------------------------ Japanese
    ("ja", "私は学校を行きます。", ["私は学校に行きます。"], ["error"]),
    ("ja", "昨日友達をを会いました。", ["昨日友達に会いました。"], ["error"]),
    ("ja", "明日は雨が降ります.", ["明日は雨が降ります。"], ["error"]),
    ("ja", "私は東京,大阪に行きました。", ["私は東京、大阪に行きました。"], ["error"]),
    ("ja", "彼は先生がです。", ["彼は先生です。"], ["error"]),
    ("ja", "私は日本語が勉強します。", ["私は日本語を勉強します。"], ["error"]),
    ("ja", "私はりんごをを食べました。", ["私はりんごを食べました。"], ["error"]),
    ("ja", "今日は天気がいいですね。", ["今日は天気がいいですね。"], ["correct"]),
    ("ja", "私は毎朝コーヒーを飲みます。", ["私は毎朝コーヒーを飲みます。"], ["correct"]),
    ("ja", "友達と一緒に映画を見ました。", ["友達と一緒に映画を見ました。"], ["correct"]),
    # ------------------------------------------------------------------ Telugu (needs native review)
    ("te", "నేను నేను ఇంటికి వెళ్తాను.", ["నేను ఇంటికి వెళ్తాను."], ["error"]),
    ("te", "వారు పుస్తకం చదివాడు.", ["వారు పుస్తకం చదివారు."], ["error"]),
    ("te", "అతను పాఠశాలకు వెళ్ళింది.", ["అతను పాఠశాలకు వెళ్ళాడు."], ["error"]),
    ("te", "ఆమె అన్నం తిన్నాడు.", ["ఆమె అన్నం తిన్నది."], ["error"]),
    ("te", "నేను  రోజూ పాఠశాలకు వెళ్తాను.", ["నేను రోజూ పాఠశాలకు వెళ్తాను."], ["error"]),
    ("te", "పిల్లలు ఆడుతున్నాడు.", ["పిల్లలు ఆడుతున్నారు."], ["error"]),
    ("te", "నేను రోజూ పాఠశాలకు వెళ్తాను.", ["నేను రోజూ పాఠశాలకు వెళ్తాను."], ["correct"]),
    ("te", "ఈ రోజు వాతావరణం బాగుంది.", ["ఈ రోజు వాతావరణం బాగుంది."], ["correct"]),
    ("te", "మేము రేపు హైదరాబాద్ వెళ్తాము.", ["మేము రేపు హైదరాబాద్ వెళ్తాము."], ["correct"]),
    ("te", "నాకు తెలుగు చాలా ఇష్టం.", ["నాకు తెలుగు చాలా ఇష్టం."], ["correct"]),
    # ------------------------------------------------------------------ Odia (needs native review)
    ("or", "ମୁଁ ମୁଁ ଘରକୁ ଯାଉଛି ।", ["ମୁଁ ଘରକୁ ଯାଉଛି ।"], ["error"]),
    ("or", "ସେମାନେ ବହି ପଢ଼େ ।", ["ସେମାନେ ବହି ପଢ଼ନ୍ତି ।"], ["error"]),
    ("or", "ମୁଁ ସ୍କୁଲକୁ ଯାଉଛି |", ["ମୁଁ ସ୍କୁଲକୁ ଯାଉଛି ।"], ["error"]),
    ("or", "ଆମେ କାଲି ବଜାରକୁ ଯାଇଥିଲା ।", ["ଆମେ କାଲି ବଜାରକୁ ଯାଇଥିଲୁ ।"], ["error"]),
    ("or", "ମୋର  ନାମ ରାମ ଅଟେ ।", ["ମୋର ନାମ ରାମ ଅଟେ ।"], ["error"]),
    ("or", "ପିଲାମାନେ ଖେଳୁଛି ।", ["ପିଲାମାନେ ଖେଳୁଛନ୍ତି ।"], ["error"]),
    ("or", "ମୁଁ ପ୍ରତିଦିନ ସ୍କୁଲକୁ ଯାଏ ।", ["ମୁଁ ପ୍ରତିଦିନ ସ୍କୁଲକୁ ଯାଏ ।"], ["correct"]),
    ("or", "ଆଜି ପାଗ ଭଲ ଅଛି ।", ["ଆଜି ପାଗ ଭଲ ଅଛି ।"], ["correct"]),
    ("or", "ସେ ଏକ ବହି ପଢ଼ୁଛି ।", ["ସେ ଏକ ବହି ପଢ଼ୁଛି ।"], ["correct"]),
    ("or", "ମୋ ନାମ ରାମ ।", ["ମୋ ନାମ ରାମ ।"], ["correct"]),
]


def main() -> None:
    out = pathlib.Path(__file__).resolve().parents[1] / "data" / "smoke" / "smoke_v0.jsonl"
    out.parent.mkdir(parents=True, exist_ok=True)
    counters: dict[str, int] = {}
    with open(out, "w", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps({"_meta": META}, ensure_ascii=False) + "\n")
        for lang, src, refs, tags in D:
            counters[lang] = counters.get(lang, 0) + 1
            f.write(json.dumps({"id": f"{lang}-{counters[lang]:02d}", "lang": lang, "source": src,
                                "references": refs, "tags": tags}, ensure_ascii=False) + "\n")
    print(f"wrote {out} ({sum(counters.values())} examples: {counters})")


if __name__ == "__main__":
    main()
