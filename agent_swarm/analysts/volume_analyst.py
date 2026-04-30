from .base import BaseAnalyst


class VolumeAnalyst(BaseAnalyst):
    name = "Volume Analyst"
    focus = "volume confirmation: accumulation vs distribution, volume spikes, dry-ups, divergences vs price"
    system_prompt = (
        "You are a volume-profile / tape-reading analyst. You judge whether price moves are "
        "supported by volume. Look for: volume on up-days vs down-days, climax volume, "
        "volume dry-ups before breakouts, divergence between price action and volume."
    )
    # Kimi (Moonshot K2) gets the volume lens — different training corpus brings
    # a genuine "second voice" to the round-2 debate. Falls back to DeepSeek
    # automatically if MOONSHOT_API_KEY isn't set.
    provider = "kimi"
    model = "moonshot-v1-auto"
