from datetime import datetime
from pathlib import Path

SYSTEM = (Path(__file__).parent.parent / "prompts" / "system.md").read_text()


def system_prompt(memories: list[str], now: datetime) -> str:
    """Stable instructions first; the per-customer and per-day parts last, so the shared prefix stays cacheable."""
    parts = [SYSTEM, f"<today>{now:%Y-%m-%d}</today>"]
    if memories:
        facts = "\n".join(f"- {m}" for m in memories)
        parts.append(
            '<customer_memory note="Facts from past conversations. May be outdated; confirm before acting.">\n'
            f"{facts}\n</customer_memory>"
        )
    return "\n\n".join(parts)
