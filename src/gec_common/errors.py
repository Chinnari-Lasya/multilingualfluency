"""Typed errors. Each carries a stable machine code so the API can return structured 4xx/5xx."""
from __future__ import annotations


class GECError(Exception):
    code = "error"
    http_status = 500

    def __init__(self, message: str, **details):
        super().__init__(message)
        self.message = message
        self.details = details


class InvalidInputError(GECError):
    code = "invalid_input"
    http_status = 422


class InputTooLongError(InvalidInputError):
    code = "input_too_long"
    http_status = 413


class UnsupportedLanguageError(GECError):
    code = "unsupported_language"
    http_status = 422


class LanguageMismatchError(GECError):
    code = "language_mismatch"
    http_status = 422


class LanguageUndeterminedError(GECError):
    code = "language_undetermined"
    http_status = 422


class ModelUnavailableError(GECError):
    code = "model_unavailable"
    http_status = 503


class AuthError(GECError):
    """Authentication/authorisation failure with a stable code the UI translates."""

    def __init__(self, code: str, message: str, status: int = 401):
        super().__init__(message)
        self.code = code
        self.http_status = status


class SameLanguageError(GECError):
    code = "same_language"
    http_status = 422


class TranslationUnavailableError(GECError):
    code = "translation_unavailable"
    http_status = 503
