"""End-to-end check against a RUNNING API: every language through the combined O2+O3 workflow, then
learner decision, educator adjudication, progress. Prints results; exits non-zero on any failure."""
import sys, json, httpx

API = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000"
CASES = {
    "en": "I likes to swimming in the pool. She don't know nothing.",
    "hi": "मैं स्कूल जाती है। राम ने ने खाना खाया|",
    "ko": "나는 학교을 갑니다. 한국어는어렵다.",
    "ja": "私は学校を行きます,  昨日友達をを会いました.",
    "te": "నేను నేను ఇంటికి వెళ్తాను.  ఈ రోజు వాతావరణం బాగుంది.",
    "or": "ମୁଁ ମୁଁ ଘରକୁ ଯାଉଛି |",
}
c = httpx.Client(base_url=API, timeout=600)
def login(u):
    r = c.post("/api/v1/auth/login", json={"username": u, "password": "demo"}); r.raise_for_status()
    return {"Authorization": f"Bearer {r.json()['token']}"}
L, E = login("learner"), login("educator")
fails = 0
first_edit = None
for lang, text in CASES.items():
    r = c.post("/api/v1/corrections/compare", headers=L, json={"text": text, "language": lang, "o3_mode": "minimal"})
    if r.status_code != 200:
        print(f"[{lang}] FAIL HTTP {r.status_code} {r.text[:200]}"); fails += 1; continue
    d = r.json(); o2, o3 = d["o2"], d["o3"]
    print(f"\n[{lang}] capability={o2['capability']['level']}  submission={d['submission_id']}")
    print(f"  source: {d['source']}\n  O2    : {o2['corrected']}  (edits={len(o2['edits'])}, flags={len(o2.get('flags', []))}, MP={o2['assessment']['meaning_preservation']['status']})")
    print(f"  O3    : {o3['corrected']}  (edits={len(o3['edits'])}, applied={sum(e['gate_status']!='rejected' for e in o3['edits'])}, abstained={o3['abstained']}, MP={o3['assessment']['meaning_preservation']['status']}, OC={o3['assessment']['over_correction']['risk']})")
    for e in o2["edits"][:3]:
        print(f"    O2 edit {e['original']!r}->{e['replacement']!r} [{e['error_type']}] conf={e['confidence']} cal={e['confidence_calibrated']} | {(e['explanation'] or {}).get('text','')[:70]}")
    if first_edit is None and o2["edits"]:
        first_edit = o2["edits"][0]["id"]
if first_edit:
    r = c.post(f"/api/v1/edits/{first_edit}/decision", headers=L, json={"decision": "accept"}); print("\nlearner decision:", r.status_code)
    r = c.post(f"/api/v1/edits/{first_edit}/adjudications", headers=E, json={"verdict": "revise", "revised_replacement": "X", "notes": "demo review"}); print("educator adjudication (Modify):", r.status_code, r.json().get("adjudications"))
    r = c.get("/api/v1/review/summary", headers=E); print("educator acceptance:", r.json())
r = c.get("/api/v1/learners/me/progress", headers=L); print("progress languages:", list(r.json()["languages"]))
r = c.get("/api/v1/learners/me/history", headers=L); print("history items:", len(r.json()))
sys.exit(1 if fails else 0)
