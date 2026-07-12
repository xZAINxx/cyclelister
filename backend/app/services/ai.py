"""AI service (spec §8): Claude vision identification + listing generation.

Contracts:
- prompts live versioned in backend/prompts/
- every call returns strict JSON validated by a Pydantic model (structured
  outputs via messages.parse); on failure retry once with a JSON reminder,
  then surface the error so the pipeline can flag the draft for review
- large static system content is prompt-cached (cache_control ephemeral)
- model routing per §8.4: Sonnet-class for vision/description, Haiku-class
  reserved for narrow classification steps
"""
from pathlib import Path

from anthropic import AsyncAnthropic
from pydantic import BaseModel, Field, field_validator

from app.config import PROMPTS_DIR, Settings, get_settings

IDENTIFY_PROMPT_FILE = "identify_v1.md"
GENERATE_PROMPT_FILE = "generate_v1.md"


class AIUnavailableError(RuntimeError):
    pass


class ConditionInfo(BaseModel):
    grade: str = "used"  # new_nos | new_other | used | for_parts
    notes: str = ""


class IdentifyResult(BaseModel):
    part_numbers: list[str] = Field(default_factory=list)
    part_type: str | None = None
    brand: str | None = None
    condition: ConditionInfo = Field(default_factory=ConditionInfo)
    visible_text: list[str] = Field(default_factory=list)
    confidence: float = 0.0


class FitmentSuggestion(BaseModel):
    make: str
    model: str
    year_start: int | None = None
    year_end: int | None = None
    confidence: float = 0.5


class GenerateResult(BaseModel):
    title: str
    description: str
    item_specifics: dict[str, str] = Field(default_factory=dict)
    suggested_category: str | None = None
    fitment_suggestions: list[FitmentSuggestion] = Field(default_factory=list)

    @field_validator("title")
    @classmethod
    def title_max_80(cls, v: str) -> str:
        # Soft constraint: truncate rather than reject, so an over-long title
        # never burns a retry API call (spec §6: title <= 80 chars).
        v = v.strip()
        return v if len(v) <= 80 else v[:80].rstrip()


def _load_prompt(filename: str) -> str:
    return (Path(PROMPTS_DIR) / filename).read_text(encoding="utf-8")


class AIService:
    def __init__(self, settings: Settings | None = None):
        self.settings = settings or get_settings()
        if not self.settings.anthropic_api_key:
            raise AIUnavailableError(
                "ANTHROPIC_API_KEY is not configured; cannot run AI identification"
            )
        self.client = AsyncAnthropic(api_key=self.settings.anthropic_api_key)
        self.usage_log: list[dict] = []  # per-call token usage (spec §8.4 / §15)

    def _record_usage(self, step: str, model: str, usage) -> None:
        self.usage_log.append(
            {
                "step": step,
                "model": model,
                "input_tokens": usage.input_tokens,
                "output_tokens": usage.output_tokens,
                "cache_read_input_tokens": getattr(usage, "cache_read_input_tokens", 0),
            }
        )

    async def _parse_with_retry(self, step: str, model: str, *, system: str, content, output_format):
        system_blocks = [
            {"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}
        ]
        messages = [{"role": "user", "content": content}]
        last_err: Exception | None = None
        for attempt in range(2):
            try:
                response = await self.client.messages.parse(
                    model=model,
                    max_tokens=4096,
                    system=system_blocks,
                    messages=messages,
                    output_format=output_format,
                )
                self._record_usage(step, model, response.usage)
                return response.parsed_output
            except Exception as err:  # validation or API error -> one retry (spec §8)
                last_err = err
                messages = [
                    {"role": "user", "content": content},
                    {
                        "role": "user",
                        "content": "Your previous output was invalid. Return ONLY valid JSON "
                        "matching the required schema, with no extra text.",
                    },
                ]
        raise last_err  # type: ignore[misc]

    async def identify_part(
        self, images: list[tuple[bytes, str]], hint: str | None = None
    ) -> IdentifyResult:
        """Spec §8.1 — images as (raw bytes base64-encoded upstream? no: encode here)."""
        import base64

        content: list[dict] = []
        for data, media_type in images[:8]:
            content.append(
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": media_type,
                        "data": base64.standard_b64encode(data).decode("ascii"),
                    },
                }
            )
        text = "Identify this part."
        if hint:
            text += f" Seller hint: {hint}"
        content.append({"type": "text", "text": text})

        return await self._parse_with_retry(
            "identify",
            self.settings.vision_model,
            system=_load_prompt(IDENTIFY_PROMPT_FILE),
            content=content,
            output_format=IdentifyResult,
        )

    async def generate_listing(
        self,
        *,
        part_number_display: str | None,
        part_type: str | None,
        brand: str | None,
        condition: ConditionInfo,
        known_fitment: list[dict],
        hint: str | None,
        boilerplate: str | None,
        item_specifics_defaults: dict | None,
    ) -> GenerateResult:
        """Spec §8.2 — title/description/item specifics/category + fitment suggestions."""
        lines = [
            f"Part number: {part_number_display or 'unknown'}",
            f"Part type: {part_type or 'unknown'}",
            f"Brand: {brand or 'unknown'}",
            f"Condition grade: {condition.grade}",
            f"Condition notes: {condition.notes or 'none'}",
            f"Known confirmed fitment: {known_fitment or 'none'}",
            f"Seller hint: {hint or 'none'}",
            f"Seller boilerplate to include at the end of the description: {boilerplate or 'none'}",
            f"Item-specific defaults for this category: {item_specifics_defaults or 'none'}",
        ]
        return await self._parse_with_retry(
            "generate",
            self.settings.text_model,
            system=_load_prompt(GENERATE_PROMPT_FILE),
            content="\n".join(lines),
            output_format=GenerateResult,
        )
