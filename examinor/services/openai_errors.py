from openai import (
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    AuthenticationError,
    OpenAIError,
    RateLimitError,
)


CREDITS_EXHAUSTED_ERROR = "OpenAI API credits exhausted"
RATE_LIMIT_ERROR = "OpenAI API rate limit exceeded"
# OpenAI answers an empty account with HTTP 429 like a rate limit, but only more
# credits fix it, so it is reported separately and is not retried.
CREDITS_EXHAUSTED_CODES = frozenset({"insufficient_quota", "credit_balance_exhausted"})


def is_credits_exhausted(error):
    if not isinstance(error, RateLimitError):
        return False
    body = error.body if isinstance(error.body, dict) else {}
    details = body.get("error", body) if isinstance(body.get("error", body), dict) else {}
    codes = {getattr(error, "code", None), details.get("code"), details.get("type")}
    return bool(codes & CREDITS_EXHAUSTED_CODES)


def format_openai_error(error):
    if isinstance(error, APITimeoutError):
        return "OpenAI API timeout"
    if is_credits_exhausted(error):
        return CREDITS_EXHAUSTED_ERROR
    if isinstance(error, RateLimitError):
        return RATE_LIMIT_ERROR
    if isinstance(error, AuthenticationError):
        return "OpenAI API authentication failed"
    if isinstance(error, APIConnectionError):
        return "OpenAI API connection error"
    if isinstance(error, APIStatusError):
        return f"OpenAI API status error {error.status_code}"
    if isinstance(error, OpenAIError):
        return "OpenAI API error"
    return error.__class__.__name__
