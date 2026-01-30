"""Formatting utilities for duration, tokens, and cost."""


def fmt_duration(seconds: float) -> str:
    """Format duration as human readable string."""
    if seconds < 60:
        return f"{seconds:.0f}s"
    elif seconds < 3600:
        mins, secs = divmod(int(seconds), 60)
        return f"{mins}m {secs}s"
    else:
        hours, remainder = divmod(int(seconds), 3600)
        mins, secs = divmod(remainder, 60)
        return f"{hours}h {mins}m {secs}s"


def fmt_tokens(tokens: int) -> str:
    """Format token count: '500' for <1k, '15.2k' for >=1k."""
    if tokens < 1000:
        return str(tokens)
    return f"{tokens / 1000:.1f}k"


def fmt_cost(usd: float) -> str:
    """Format cost: '$0.0045' for <$0.01, '$0.04' for >=$0.01."""
    if usd < 0.01:
        return f"${usd:.4f}"
    return f"${usd:.2f}"
