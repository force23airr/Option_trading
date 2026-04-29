from .base import BaseAnalyst


class VolatilityAnalyst(BaseAnalyst):
    name = "Volatility Analyst"
    focus = "volatility regime: realized range expansion/contraction, gap behavior, multi-day ranges"
    system_prompt = (
        "You are a volatility specialist. You watch realized range, intraday range expansion "
        "or contraction, and how recent vol compares to its own short-term history. Translate "
        "vol regime into options-trader language (premium-rich vs premium-cheap, debit vs "
        "credit structures preferred)."
    )
    provider = "deepseek"
    model = "deepseek-chat"
