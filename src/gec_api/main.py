"""FastAPI application. Run: gec-api  (or: uvicorn gec_api.main:app --port 8000)"""
from __future__ import annotations

import datetime as dt
import hashlib
import hmac
import os
import re
import threading
import uuid
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal

import jwt
from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from gec_common.align import tokenize
from gec_common.config import language_capability, load_models_config
from gec_common.errors import AuthError, GECError
from gec_common.langs import LANGUAGES
from gec_eval import metrics as eval_metrics
from gec_eval.io import load_dataset
from gec_eval.report import evaluate
from gec_eval.sut import CallableSUT, collect_predictions
from gec_o4.progress import EditOutcome, progress_report
from gec_translate.service import provider_info, translate as do_translate

from . import db as dbm
from .pipeline import Coach

_SECRET = os.environ.get("GEC_JWT_SECRET", "dev-only-secret-change-me")
_REPO = Path(__file__).resolve().parents[2]
_coach: Coach | None = None


def coach() -> Coach:
    global _coach
    if _coach is None:
        _coach = Coach()
    return _coach


# ------------------------------------------------------------------------------------------- security
def hash_pw(pw: str, salt: bytes | None = None) -> str:
    salt = salt or os.urandom(16)
    return salt.hex() + "$" + hashlib.pbkdf2_hmac("sha256", pw.encode(), salt, 100_000).hex()


def check_pw(pw: str, stored: str) -> bool:
    salt_hex, _ = stored.split("$")
    return hmac.compare_digest(hash_pw(pw, bytes.fromhex(salt_hex)), stored)


def make_token(u: dbm.User) -> str:
    exp = dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=12)
    return jwt.encode({"sub": str(u.id), "role": u.role, "exp": exp, "jti": uuid.uuid4().hex}, _SECRET, algorithm="HS256")


def get_db():
    s = dbm.SessionLocal()
    try:
        yield s
    finally:
        s.close()


def _decode(authorization: str | None) -> dict:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise AuthError("unauthorized", "Missing bearer token")
    try:
        return jwt.decode(authorization[7:], _SECRET, algorithms=["HS256"])
    except Exception:  # noqa: BLE001
        raise AuthError("unauthorized", "Invalid or expired token")


def current_user(authorization: str | None = Header(default=None), db=Depends(get_db)) -> dbm.User:
    claims = _decode(authorization)
    if claims.get("jti") and db.get(dbm.RevokedToken, claims["jti"]):
        raise AuthError("unauthorized", "Signed out")
    u = db.get(dbm.User, int(claims["sub"]))
    if not u:
        raise AuthError("unauthorized", "Unknown user")
    return u


def require(*roles: str):
    def dep(u: dbm.User = Depends(current_user)) -> dbm.User:
        if u.role not in roles:
            raise AuthError("forbidden", f"Requires role: {', '.join(roles)}", 403)
        return u
    return dep


def seed_demo_users() -> None:
    """DEMO ACCOUNTS ONLY (local prototype). None of them is an independent educator.
    On by default for local development; production sets GEC_SEED_DEMO_USERS=0 (the backend Docker image does)."""
    if os.environ.get("GEC_SEED_DEMO_USERS", "1").strip().lower() in ("0", "false", "no", "off"):
        return
    with dbm.SessionLocal() as s:
        if s.scalar(select(dbm.User).limit(1)):
            return
        for name, role, disp in [("learner", "learner", "Demo Learner"), ("educator", "educator", "Demo Educator (developer, NOT independent)"),
                                 ("admin", "admin", "Demo Admin")]:
            s.add(dbm.User(username=name, password_hash=hash_pw("demo"), role=role, display_name=disp,
                           is_independent_educator=False))
        s.commit()


@asynccontextmanager
async def lifespan(app: FastAPI):
    dbm.init_db()
    seed_demo_users()
    pre = [x for x in os.environ.get("GEC_PRELOAD", "").split(",") if x]
    if pre:  # warm models in the background so the first request is fast
        def _warm():
            for lang in pre:
                try:
                    coach().run(_WARM[lang], lang, "o2", "reference", False)  # loads generator + XLM-R detector
                    coach().run(_WARM[lang], lang, "o3", "minimal", False)  # loads meaning-gate embedder
                except Exception:  # noqa: BLE001
                    pass
        threading.Thread(target=_warm, daemon=True).start()
    yield


_WARM = {"en": "I has a apple.", "hi": "मैं जाती है।", "ko": "나는 학교을 갑니다.", "te": "నేను ఇంటికి.", "or": "ମୁଁ ଘରକୁ ।", "ja": "私は学校を行く。"}

app = FastAPI(title="Multilingual GEC Coach", version="0.1.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:3000", "http://127.0.0.1:3000", *[o for o in os.environ.get("GEC_ALLOWED_ORIGINS", "").split(",") if o]],
                   allow_methods=["*"], allow_headers=["*"])


@app.exception_handler(GECError)
async def gec_error_handler(_: Request, exc: GECError):
    return JSONResponse(status_code=exc.http_status, content={"error": exc.code, "message": exc.message, "details": exc.details})


# --------------------------------------------------------------------------------------------- schemas
class LoginIn(BaseModel):
    username: str
    password: str


class RegisterIn(BaseModel):
    name: str
    username: str  # username OR email
    password: str
    confirm_password: str | None = None
    role: Literal["learner", "educator", "admin"] = "learner"
    preferred_language: str = "en"
    invite_code: str | None = None  # educator sign-up only, when GEC_EDUCATOR_INVITE_CODE is configured


class PrefsIn(BaseModel):
    preferred_language: str


class TranslateIn(BaseModel):
    text: str
    source_language: str
    target_language: str

class CorrectionIn(BaseModel):
    text: str
    language: str | None = None
    pipeline: Literal["o2", "o3"] = "o2"
    mode: Literal["reference", "minimal", "fluency"] = "reference"
    explain: bool = True
    persist: bool = True


class CompareIn(BaseModel):
    text: str
    language: str | None = None
    o3_mode: Literal["minimal", "fluency"] = "minimal"
    explain: bool = True


class RunOut(BaseModel):
    """Correction result (O2 or O3). Extra fields (edits[], flags[], assessment, trace, ...) pass through."""
    model_config = ConfigDict(extra="allow")
    run_id: int | None
    pipeline: str
    mode: str
    language: str
    source: str
    corrected: str
    degraded: bool = False
    abstained: bool = False
    abstain_reason: str | None = None
    edits: list[dict]


class CompareOut(BaseModel):
    submission_id: int
    language: str
    source: str
    o2: RunOut
    o3: RunOut


class DecisionIn(BaseModel):
    decision: Literal["accept", "reject"]


class AdjudicationIn(BaseModel):
    verdict: Literal["accept", "reject", "revise"]
    revised_replacement: str | None = None
    error_type_override: str | None = None
    meaning_changed: bool = False
    notes: str = Field(default="", max_length=2000)


class EvalRunIn(BaseModel):
    pipeline: Literal["o2", "o3"] = "o2"
    mode: Literal["reference", "minimal", "fluency"] = "reference"
    languages: list[str] | None = None
    max_per_language: int | None = None


# ------------------------------------------------------------------------------------------- public
@app.get("/api/v1/health")
def health():
    return {"status": "ok", "time": dt.datetime.now(dt.timezone.utc).isoformat()}


@app.get("/api/v1/languages")
def languages():
    return [{"code": c, "name": s.name, "native_name": s.native_name, "capability": language_capability(c).model_dump()}
            for c, s in LANGUAGES.items()]


@app.get("/api/v1/models")
def models():
    cfg = load_models_config()
    return {"models": {k: {"hf_id": v["hf_id"], "license": v.get("license"), "notes": v.get("notes")} for k, v in cfg["models"].items()},
            "thresholds_note": "All thresholds are UNCALIBRATED defaults.", "thresholds": cfg["thresholds"]}


@app.post("/api/v1/auth/login")
def login(body: LoginIn, db=Depends(get_db)):
    u = db.scalar(select(dbm.User).where(dbm.User.username == body.username.strip().lower()))
    if not u or not check_pw(body.password, u.password_hash):
        raise AuthError("invalid_credentials", "Invalid username or password")
    return {"token": make_token(u), "user": _user_out(u)}


@app.post("/api/v1/auth/register", status_code=201)
def register(body: RegisterIn, db=Depends(get_db)):
    """Creates the account, hashes the password, and signs the user in. Educator/admin self-selection is a PROTOTYPE
    convenience (GEC_ALLOW_ROLE_SELF_SELECT=0 disables it); self-registered educators are never 'independent'."""
    name = body.name.strip()
    login_id = body.username.strip().lower()
    if not name:
        raise AuthError("name_required", "Name is required", 422)
    is_email = "@" in login_id
    if is_email and not re.fullmatch(r"[^@ ]+@[^@ ]+[.][^@ ]+", login_id):
        raise AuthError("invalid_email", "Enter a valid email address", 422)
    if not is_email and not re.fullmatch(r"[a-z0-9_]{3,32}", login_id):
        raise AuthError("invalid_username", "Username must be 3-32 characters: letters, digits, underscore", 422)
    if len(login_id) > 64:
        raise AuthError("invalid_username", "Too long", 422)
    if len(body.password) < 8:
        raise AuthError("weak_password", "Password must be at least 8 characters", 422)
    if body.confirm_password is not None and body.confirm_password != body.password:
        raise AuthError("password_mismatch", "Passwords do not match", 422)
    if body.preferred_language not in LANGUAGES:
        raise AuthError("unsupported_language", "Unsupported language", 422)
    if body.role != "learner":
        educator_code = os.environ.get("GEC_EDUCATOR_INVITE_CODE", "")
        if body.role == "educator" and educator_code:
            # hosted deployment: educators need the invite code. Admin is never self-created here (see below).
            if not hmac.compare_digest((body.invite_code or "").encode(), educator_code.encode()):
                raise AuthError("invalid_invite_code", "Invalid or missing invite code", 403)
        elif os.environ.get("GEC_ALLOW_ROLE_SELF_SELECT", "1") != "1":
            raise AuthError("forbidden", "Educator and admin accounts are provisioned by an administrator", 403)
    if db.scalar(select(dbm.User).where(dbm.User.username == login_id)):
        raise AuthError("username_taken", "That username or email is already registered", 409)
    u = dbm.User(username=login_id, password_hash=hash_pw(body.password), role=body.role, display_name=name[:64],
                 is_independent_educator=False, preferred_language=body.preferred_language)
    db.add(u)
    db.commit()
    db.refresh(u)
    return {"token": make_token(u), "user": _user_out(u)}


@app.patch("/api/v1/me/preferences")
def set_preferences(body: PrefsIn, u: dbm.User = Depends(current_user), db=Depends(get_db)):
    if body.preferred_language not in LANGUAGES:
        raise AuthError("unsupported_language", "Unsupported language", 422)
    u.preferred_language = body.preferred_language
    db.commit()
    return _user_out(u)


@app.post("/api/v1/auth/logout")
def logout(authorization: str | None = Header(default=None), db=Depends(get_db)):
    claims = _decode(authorization)
    if claims.get("jti") and not db.get(dbm.RevokedToken, claims["jti"]):
        db.add(dbm.RevokedToken(jti=claims["jti"], expires_at=dt.datetime.fromtimestamp(claims["exp"], dt.timezone.utc)))
        db.commit()
    return {"ok": True}


def _user_out(u: dbm.User) -> dict:
    return {"id": u.id, "username": u.username, "role": u.role, "display_name": u.display_name,
            "is_independent_educator": u.is_independent_educator, "preferred_language": u.preferred_language}


@app.get("/api/v1/me")
def me(u: dbm.User = Depends(current_user)):
    return _user_out(u)


# ----------------------------------------------------------------------------------------- corrections
def _edit_out(e: dbm.EditRow) -> dict:
    return {"id": e.id, "start": e.start, "end": e.end, "original": e.original, "replacement": e.replacement, "op": e.op,
            "language": e.language, "error_type": e.error_type, "rule_id": e.rule_id, "source": e.source,
            "confidence": e.confidence, "confidence_calibrated": e.confidence_calibrated, "gate_status": e.gate_status,
            "gate_reason": e.gate_reason, "scores": e.scores, "explanation": e.explanation,
            "learner_decision": e.learner_decision,
            "adjudications": [{"verdict": a.verdict, "reviewer_independent": a.reviewer_independent, "notes": a.notes,
                               "meaning_changed": a.meaning_changed} for a in e.adjudications]}


def _run_out(run: dbm.CorrectionRun) -> dict:
    return {"run_id": run.id, "submission_id": run.submission_id, "pipeline": run.pipeline, "mode": run.mode,
            "language": run.submission.language, "source": run.submission.text, "corrected": run.corrected,
            "degraded": run.degraded, "latency_ms": run.latency_ms, "edits": [_edit_out(e) for e in run.edits],
            **run.meta}


_META_KEYS = ("language_detection", "capability", "warnings", "trace", "model_ids", "flags", "abstained",
              "abstain_reason", "assessment")


def _persist(db, user: dbm.User, sub: dbm.Submission | None, res, exps) -> dbm.CorrectionRun:
    payload = res.model_dump()
    sub = sub or dbm.Submission(user_id=user.id, language=res.language, text=res.source)
    run = dbm.CorrectionRun(submission=sub, pipeline=res.pipeline, mode=res.mode, corrected=res.corrected,
                            degraded=res.degraded, latency_ms=res.latency_ms, meta={k: payload[k] for k in _META_KEYS})
    for e, x in zip(res.edits, exps):
        run.edits.append(dbm.EditRow(**e.model_dump(exclude={"scores"}), scores=e.scores, explanation=x))
    db.add_all([sub, run])
    db.commit()
    db.refresh(run)
    return run


def refresh_progress(db, user_id: int) -> None:
    """Rebuild the learner_progress snapshot rows from edits + adjudications (idempotent)."""
    rep = _progress_for(db, user_id)
    for row in db.scalars(select(dbm.LearnerProgress).where(dbm.LearnerProgress.user_id == user_id)).all():
        db.delete(row)
    for lang, d in rep["languages"].items():
        for r in d["error_types"]:
            db.add(dbm.LearnerProgress(user_id=user_id, language=lang, error_type=r["error_type"], total=r["total"],
                                       recent_per_100_tokens=r["recent_per_100_tokens"], trend=r["trend"]))
    db.commit()


@app.post("/api/v1/corrections", response_model=RunOut)
def create_correction(body: CorrectionIn, authorization: str | None = Header(default=None), db=Depends(get_db)):
    """Single pipeline (O2 or O3). persist=false is the stateless mode used by the evaluator."""
    res, exps = coach().run(body.text, body.language, body.pipeline, body.mode, body.explain)
    if not body.persist:
        payload = res.model_dump()
        for e, x in zip(payload["edits"], exps):
            e["explanation"] = x
        return {**payload, "run_id": None}
    user = current_user(authorization, db)
    run = _persist(db, user, None, res, exps)
    refresh_progress(db, user.id)
    return _run_out(run)


@app.post("/api/v1/corrections/compare", response_model=CompareOut)
def compare_correction(body: CompareIn, u: dbm.User = Depends(current_user), db=Depends(get_db)):
    """Combined workflow: same text through O2 (reference) and O3 (controlled), stored under one submission."""
    r2, e2 = coach().run(body.text, body.language, "o2", "reference", body.explain)
    r3, e3 = coach().run(body.text, r2.language, "o3", body.o3_mode, body.explain)
    run2 = _persist(db, u, None, r2, e2)
    run3 = _persist(db, u, run2.submission, r3, e3)
    refresh_progress(db, u.id)
    return {"submission_id": run2.submission_id, "language": r2.language, "source": r2.source,
            "o2": _run_out(run2), "o3": _run_out(run3)}


@app.get("/api/v1/edits/{edit_id}/explanation")
def edit_explanation(edit_id: int, u: dbm.User = Depends(current_user), db=Depends(get_db)):
    e = db.get(dbm.EditRow, edit_id)
    if not e or (u.role == "learner" and e.run.submission.user_id != u.id):
        raise HTTPException(404, "Not found")
    return {"edit_id": e.id, "error_type": e.error_type, "explanation": e.explanation,
            "note": "Templates are developer-authored v0 and NOT reviewed by native-speaker educators."}


@app.get("/api/v1/corrections/{run_id}")
def get_correction(run_id: int, u: dbm.User = Depends(current_user), db=Depends(get_db)):
    run = db.get(dbm.CorrectionRun, run_id)
    if not run or (u.role == "learner" and run.submission.user_id != u.id):
        raise HTTPException(404, "Not found")
    return _run_out(run)


@app.get("/api/v1/submissions")
def my_submissions(u: dbm.User = Depends(current_user), db=Depends(get_db)):
    rows = db.scalars(select(dbm.Submission).where(dbm.Submission.user_id == u.id).order_by(dbm.Submission.id.desc()).limit(50)).all()
    return [{"id": s.id, "language": s.language, "text": s.text, "created_at": s.created_at.isoformat(),
             "runs": [r.id for r in s.runs]} for s in rows]


@app.post("/api/v1/edits/{edit_id}/decision")
def learner_decision(edit_id: int, body: DecisionIn, u: dbm.User = Depends(current_user), db=Depends(get_db)):
    e = db.get(dbm.EditRow, edit_id)
    if not e or e.run.submission.user_id != u.id:
        raise HTTPException(404, "Not found")
    e.learner_decision = body.decision
    db.commit()
    return _edit_out(e)


# ---------------------------------------------------------------------------------------- educator
@app.get("/api/v1/review/queue")
def review_queue(limit: int = 30, u: dbm.User = Depends(require("educator", "admin")), db=Depends(get_db)):
    edits = db.scalars(select(dbm.EditRow).order_by(dbm.EditRow.id.desc()).limit(500)).all()
    pending = [e for e in edits if not e.adjudications]
    # least-confident and gate-rejected edits first: that is where an educator's time is most valuable
    pending.sort(key=lambda e: (e.gate_status != "rejected", e.confidence if e.confidence is not None else 0.0))
    return [{**_edit_out(e), "context": e.run.submission.text, "pipeline": e.run.pipeline, "mode": e.run.mode}
            for e in pending[:limit]]


@app.post("/api/v1/edits/{edit_id}/adjudications")
def adjudicate(edit_id: int, body: AdjudicationIn, u: dbm.User = Depends(require("educator", "admin")), db=Depends(get_db)):
    e = db.get(dbm.EditRow, edit_id)
    if not e:
        raise HTTPException(404, "Not found")
    if body.verdict == "revise" and not body.revised_replacement:
        raise HTTPException(422, "verdict 'revise' needs revised_replacement")
    a = dbm.Adjudication(edit_id=edit_id, educator_id=u.id, reviewer_independent=u.is_independent_educator,
                         **body.model_dump())
    db.add(a)
    db.commit()
    db.refresh(e)
    refresh_progress(db, e.run.submission.user_id)
    return _edit_out(e)


def _acceptance(db) -> dict:
    rows = db.scalars(select(dbm.Adjudication)).all()
    out = eval_metrics.educator_acceptance([{"verdict": a.verdict, "reviewer_independent": a.reviewer_independent,
                                             "reviewer_id": a.educator_id} for a in rows])
    out["n_total_adjudications_incl_demo"] = len(rows)
    return out


@app.get("/api/v1/review/summary")
def review_summary(u: dbm.User = Depends(require("educator", "admin")), db=Depends(get_db)):
    return _acceptance(db)


# ----------------------------------------------------------------------------------------- progress
@app.get("/api/v1/learners/me/progress")
def my_progress(u: dbm.User = Depends(current_user), db=Depends(get_db)):
    return _progress_for(db, u.id)


@app.get("/api/v1/learners/me/history")
def my_history(u: dbm.User = Depends(current_user), db=Depends(get_db)):
    subs = db.scalars(select(dbm.Submission).where(dbm.Submission.user_id == u.id).order_by(dbm.Submission.id.desc()).limit(30)).all()
    return [{"submission_id": s.id, "language": s.language, "text": s.text, "created_at": s.created_at.isoformat(),
             "runs": [{"run_id": r.id, "pipeline": r.pipeline, "mode": r.mode, "corrected": r.corrected,
                       "n_edits": len(r.edits), "abstained": bool((r.meta or {}).get("abstained"))} for r in s.runs]} for s in subs]


def _progress_for(db, user_id: int) -> dict:
    """Per-user error profile + statistics for the six languages (valid and empty for new users)."""
    subs = db.scalars(select(dbm.Submission).where(dbm.Submission.user_id == user_id)).all()
    submissions, outcomes = [], []
    keys = ("attempts", "corrected_sentences", "errors_found", "learner_accepted", "learner_rejected",
            "educator_verdicts", "o3_abstained", "o3_blocked_edits")
    stats = {c: {k: 0 for k in keys} for c in LANGUAGES}
    conf: dict[str, list[float]] = {c: [] for c in LANGUAGES}
    per_day: dict[str, int] = {}
    for s in subs:
        toks = max(1, len(tokenize(s.text, s.language)))
        submissions.append((s.id, s.created_at.timestamp(), s.language, toks))
        st = stats[s.language]
        st["attempts"] += 1
        day = s.created_at.date().isoformat()
        per_day[day] = per_day.get(day, 0) + 1
        o2 = next((r for r in s.runs if r.pipeline == "o2"), None)
        for r in s.runs:
            if r.pipeline == "o3":
                st["o3_abstained"] += int(bool((r.meta or {}).get("abstained")))
            for e in r.edits:
                st["learner_accepted"] += int(e.learner_decision == "accept")
                st["learner_rejected"] += int(e.learner_decision == "reject")
                st["educator_verdicts"] += len(e.adjudications)
                st["o3_blocked_edits"] += int(r.pipeline == "o3" and e.gate_status == "rejected")
        run = o2 or (max(s.runs, key=lambda r: r.id) if s.runs else None)  # O2 detects errors in all six languages
        if run:
            st["corrected_sentences"] += int(run.corrected != s.text)
            applied = [e for e in run.edits if e.gate_status != "rejected"]
            st["errors_found"] += len(applied)
            conf[s.language] += [e.confidence for e in applied if e.confidence is not None]
            for e in applied:
                verdict = e.adjudications[-1].verdict if e.adjudications else None
                outcomes.append(EditOutcome(s.id, s.created_at.timestamp(), s.language, toks, e.error_type, verdict))
    rep = progress_report(outcomes, submissions)
    for code in LANGUAGES:
        entry = rep["languages"].setdefault(code, {"submissions": 0, "error_types": [], "focus": [], "note": None})
        avg = round(sum(conf[code]) / len(conf[code]), 3) if conf[code] else None
        entry["stats"] = {**stats[code], "avg_confidence": avg}
    rep["languages"] = {c: rep["languages"][c] for c in LANGUAGES}  # stable order, always all six
    allc = [x for v in conf.values() for x in v]
    totals = {k: sum(v[k] for v in stats.values()) for k in keys}
    decided = totals["learner_accepted"] + totals["learner_rejected"]
    totals["avg_confidence"] = round(sum(allc) / len(allc), 3) if allc else None  # raw, UNCALIBRATED evidence score
    totals["suggestion_acceptance_rate"] = round(totals["learner_accepted"] / decided, 3) if decided else None
    rep["totals"] = totals
    today = dt.datetime.now(dt.timezone.utc).date()
    rep["activity"] = [{"date": (today - dt.timedelta(days=i)).isoformat(),
                        "count": per_day.get((today - dt.timedelta(days=i)).isoformat(), 0)} for i in range(13, -1, -1)]
    return rep


# --------------------------------------------------------------------------------------- translation
@app.get("/api/v1/translate/info")
def translate_info(u: dbm.User = Depends(current_user)):
    return provider_info()


@app.post("/api/v1/translate")
def translate_text(body: TranslateIn, u: dbm.User = Depends(current_user)):
    """Machine translation between the six languages. NOT grammar correction (see /corrections)."""
    with coach()._sem:  # share the CPU concurrency limit with the correction pipeline
        return do_translate(body.text, body.source_language, body.target_language)


# --------------------------------------------------------------------------------------- evaluation
def _run_eval(run_id: int, body: EvalRunIn) -> None:
    with dbm.SessionLocal() as s:
        run = s.get(dbm.EvaluationRun, run_id)
        try:
            meta, exs = load_dataset(_REPO / "data" / "smoke" / "smoke_v0.jsonl")
            if body.languages:
                exs = [e for e in exs if e.lang in body.languages]
            if body.max_per_language:
                cnt: dict[str, int] = {}
                keep = []
                for e in exs:
                    cnt[e.lang] = cnt.get(e.lang, 0) + 1
                    if cnt[e.lang] <= body.max_per_language:
                        keep.append(e)
                exs = keep

            def fn(text: str, lang: str) -> dict:
                res, _ = coach().run(text, lang, body.pipeline, body.mode, False)
                return res.model_dump()

            sut = CallableSUT(fn, f"in-process:{body.pipeline}/{body.mode}")

            def prog(i, n):
                run.progress = f"{i}/{n}"
                s.commit()

            preds = collect_predictions(sut, exs, prog)
            adj = [{"verdict": a.verdict, "reviewer_independent": a.reviewer_independent, "reviewer_id": a.educator_id}
                   for a in s.scalars(select(dbm.Adjudication)).all()]
            run.report = evaluate(meta, exs, preds, system=sut.name, dataset_path=_REPO / "data" / "smoke" / "smoke_v0.jsonl",
                                  adjudications=adj)
            run.status = "done"
        except Exception as e:  # noqa: BLE001
            run.status, run.error = "failed", f"{type(e).__name__}: {e}"[:500]
        run.finished_at = dt.datetime.now(dt.timezone.utc)
        s.commit()


@app.post("/api/v1/evaluations/run")
def start_eval(body: EvalRunIn, u: dbm.User = Depends(require("admin")), db=Depends(get_db)):
    run = dbm.EvaluationRun(pipeline=body.pipeline, mode=body.mode, dataset="smoke_v0")
    db.add(run)
    db.commit()
    threading.Thread(target=_run_eval, args=(run.id, body), daemon=True).start()
    return {"id": run.id, "status": run.status}


@app.get("/api/v1/evaluations")
def list_evals(u: dbm.User = Depends(require("educator", "admin")), db=Depends(get_db)):
    rows = db.scalars(select(dbm.EvaluationRun).order_by(dbm.EvaluationRun.id.desc()).limit(20)).all()
    return [{"id": r.id, "pipeline": r.pipeline, "mode": r.mode, "dataset": r.dataset, "status": r.status,
             "progress": r.progress, "created_at": r.created_at.isoformat(), "error": r.error} for r in rows]


@app.get("/api/v1/evaluations/{run_id}")
def get_eval(run_id: int, u: dbm.User = Depends(require("educator", "admin")), db=Depends(get_db)):
    r = db.get(dbm.EvaluationRun, run_id)
    if not r:
        raise HTTPException(404, "Not found")
    return {"id": r.id, "pipeline": r.pipeline, "mode": r.mode, "status": r.status, "progress": r.progress,
            "error": r.error, "report": r.report}


def run() -> None:
    import uvicorn
    uvicorn.run("gec_api.main:app", host=os.environ.get("GEC_HOST", "127.0.0.1"), port=int(os.environ.get("GEC_PORT", "8000")))


if __name__ == "__main__":
    run()
