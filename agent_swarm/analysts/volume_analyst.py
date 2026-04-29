from .base import BaseAnalyst


class VolumeAnalyst(BaseAnalyst):
    name = "Volume Analyst"
    focus = "volume confirmation: accumulation vs distribution, volume spikes, dry-ups, divergences vs price"
    system_prompt = (
        "You are a volume-profile / tape-reading analyst. You judge whether price moves are "
        "supported by volume. Look for: volume on up-days vs down-days, climax volume, "
        "volume dry-ups before breakouts, divergence between price action and volume."
    )
    provider = "deepseek"
    model = "deepseek-chat"
