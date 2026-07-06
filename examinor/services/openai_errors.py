from openai import (
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    AuthenticationError,
    OpenAIError,
    RateLimitError,
)


def format_openai_error(error):
    if isinstance(error, APITimeoutError):
        return "OpenAI API timeout"
    if isinstance(error, RateLimitError):
        return "OpenAI API rate limit exceeded"
    if isinstance(error, AuthenticationError):
        return "OpenAI API authentication failed"
    if isinstance(error, APIConnectionError):
        return "OpenAI API connection error"
    if isinstance(error, APIStatusError):
        return f"OpenAI API status error {error.status_code}"
    if isinstance(error, OpenAIError):
        return "OpenAI API error"
    return error.__class__.__name__
