"""One question in, `{answer, tools_used, ui_actions}` out (brief §10.3, §10.5).

`ask` is what the local server and the Lambda entry point both call. Each question is its own
conversation: nothing is remembered between calls.
"""

from __future__ import annotations

import base64
import json
import logging
import os
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from agent import grounding, ratelimit, tools
from agent.model import build_model, model_name

MAX_QUESTION_CHARS = 500
MAX_TOOL_CALLS = 6
PROMPT = Path(__file__).with_name("prompt.md").read_text().strip()
# Added after the brief's prompt (kept verbatim in prompt.md): how replies are shown, and
# what the open-weight model needs spelled out.
NOTES = """
Format: plain sentences, or a short numbered list for rankings. No tables, no emoji.
Quote numbers exactly as the tools give them; do not estimate, combine or compare beyond them.
Use the level words (Low, Moderate, High, Very high) exactly as the tools give them.
State limitations only as the tools give them.
Never mention tools or their names; say what you can look up instead.
Results cover only the districts the tools name; never describe them as all of Punjab or Haryana.
Spell village and locality names exactly as the tools give them, in Latin letters.
The data window is the one the tool result gives. "1-15 Nov 2025" above only shows the format.
Give no figure unless a tool returned it in this conversation.
"""
HINDI_NOTE = "The user wrote in Hindi. Write the whole reply in Hindi, in Devanagari script."
LATIN_NOTE = (
    "The user wrote in Latin letters. Reply in English; if the question is Hindi written in "
    "Latin letters (Hinglish), reply in Hinglish."
)
# A reply that fails the grounding check is asked for once more, with what was wrong.
RETRIES_WHEN_UNGROUNDED = 1
RETRY_NOTE = (
    "Your previous draft was rejected. Figures not found in any tool result: {figures}. "
    "Words that must not be used: {words}. Write the reply again using only what the tools "
    "return in this conversation; look things up again if you need to, or say you do not have it."
)
log = logging.getLogger("afterpass.agent")


def system_prompt(question: str) -> str:
    """The brief's prompt, the notes, and the language to reply in."""
    devanagari = sum(1 for ch in question if "\u0900" <= ch <= "\u097f")
    language = HINDI_NOTE if devanagari > len(question) / 4 else LATIN_NOTE
    return "\n\n".join([PROMPT, NOTES.strip(), language])


# Runs the model: (question, tools, system prompt) -> (answer text, token usage).
Runner = Callable[[str, list[Callable], str], tuple[str, dict]]


@dataclass
class Turn:
    """What one question's tool calls did, collected for the reply."""

    calls: int = 0
    tools_used: list[dict] = field(default_factory=list)
    ui_actions: list[dict] = field(default_factory=list)
    results: list[dict] = field(default_factory=list)

    def run(self, name: str, function: Callable[..., dict], **arguments) -> str:
        """Call a tool, record it, and return what the model gets to read."""
        self.calls += 1
        if self.calls > MAX_TOOL_CALLS:
            log.info(json.dumps({"tool": name, "refused": "tool-call limit"}))
            return json.dumps({"error": "Tool-call limit reached. Answer from what you have."})
        started = time.perf_counter()
        given = {key: value for key, value in arguments.items() if value is not None}
        try:
            result = function(**given)
        except Exception as exc:  # noqa: BLE001 - the model should hear about any tool failure
            log.exception("tool %s failed", name)
            result = {"data": {"error": f"The {name} tool failed: {type(exc).__name__}."}}
        payload = result["data"]
        ok = "error" not in payload
        self.tools_used.append({"name": name, "input": given, "ok": ok})
        self.results.append(payload)
        for action in result.get("ui_actions", []):
            if action not in self.ui_actions:
                self.ui_actions.append(action)
        elapsed = round((time.perf_counter() - started) * 1000)
        log.info(
            json.dumps({"tool": name, "input": given, "ok": ok, "ms": elapsed}, ensure_ascii=False)
        )
        return json.dumps(payload, ensure_ascii=False)


def build_tools(turn: Turn) -> list[Callable]:
    """The six tools as the model sees them: typed arguments in, JSON text out."""

    def season_overview(season: int = 2025, district: str | None = None) -> str:
        """Season totals: hectares burned, hectares not in official counts and their share,
        number of burn scars and of official fire detections, and the dates the data covers.

        Args:
            season: The burning season's year. Only 2025 is published.
            district: A district name in English or Hindi. Leave out for all districts together.
        """
        return turn.run("season_overview", tools.season_overview, season=season, district=district)

    def top_unrecorded_villages(
        district: str | None = None, season: int = 2025, n: int = 10, week: str | None = None
    ) -> str:
        """Villages ranked by burned area that is not in official counts, and whether each has
        before and after satellite images. Shows the top village on the map.

        Args:
            district: A district name in English or Hindi. Leave out to rank across all districts.
            season: The burning season's year. Only 2025 is published.
            n: How many villages to return, 1 to 20.
            week: An ISO week such as 2025-W45 to rank within one week. Leave out for the season.
        """
        return turn.run(
            "top_unrecorded_villages",
            tools.top_unrecorded_villages,
            district=district,
            season=season,
            n=n,
            week=week,
        )

    def district_trend(district: str, season: int = 2025) -> str:
        """Week by week burned area for one district, split into area in official counts and
        area not in official counts, with the peak week.

        Args:
            district: A district name in English or Hindi.
            season: The burning season's year. Only 2025 is published.
        """
        return turn.run("district_trend", tools.district_trend, district=district, season=season)

    def official_detection_times(season: int = 2025) -> str:
        """The hours of the day (IST) at which official satellites detected fires, and when
        those satellites pass. Use it to explain why official counts miss fires.

        Args:
            season: The burning season's year. Only 2025 is published.
        """
        return turn.run("official_detection_times", tools.official_detection_times, season=season)

    def smoke_outlook(place: str, hours: int = 48, start_date: str | None = None) -> str:
        """The hourly Smoke Arrival Index (0-100, relative) for a Delhi locality over a 48-hour
        model run, with the peak window and level. Plays the smoke on the map.

        Args:
            place: A Delhi locality as the user wrote it, in English or Hindi, e.g. Dwarka.
            hours: How many hours from the start of the run to report, 1 to 48.
            start_date: The run's first day as YYYY-MM-DD. Leave out for the latest forecast,
                or the replay's smokiest 48 hours when no forecast is published.
        """
        return turn.run(
            "smoke_outlook", tools.smoke_outlook, place=place, hours=hours, start_date=start_date
        )

    def method_and_limits(topic: str) -> str:
        """A short section of the method document.

        Args:
            topic: One of detection, why_official_counts_miss_fires, matching, smoke,
                validation, limitations, ethics, data_sources.
        """
        return turn.run("method_and_limits", tools.method_and_limits, topic=topic)

    return [
        season_overview,
        top_unrecorded_villages,
        district_trend,
        official_detection_times,
        smoke_outlook,
        method_and_limits,
    ]


def strands_runner(
    question: str, functions: list[Callable], system_prompt: str
) -> tuple[str, dict]:
    """Run the question through a Strands agent on the configured model."""
    from strands import Agent, tool

    agent = Agent(
        model=build_model(),
        tools=[tool(function) for function in functions],
        system_prompt=system_prompt,
        callback_handler=None,
    )
    result = agent(question)
    text = "".join(block.get("text", "") for block in result.message["content"]).strip()
    usage = result.metrics.accumulated_usage
    return text, {
        "input_tokens": int(usage.get("inputTokens", 0)),
        "output_tokens": int(usage.get("outputTokens", 0)),
    }


def ask(question: str, runner: Runner | None = None) -> dict:
    """Answer one question from the published data."""
    question = question.strip()
    if not question:
        return _refusal("empty", "Ask a question about stubble burning or the smoke outlook.")
    if len(question) > MAX_QUESTION_CHARS:
        return _refusal(
            "too_long", f"Please keep the question under {MAX_QUESTION_CHARS} characters."
        )
    run = runner or strands_runner
    started = time.perf_counter()
    prompt = system_prompt(question)
    usage = {"input_tokens": 0, "output_tokens": 0}
    for attempt in range(1 + RETRIES_WHEN_UNGROUNDED):
        turn = Turn()
        answer, used = run(question, build_tools(turn), prompt)
        usage = {key: usage[key] + used.get(key, 0) for key in usage}
        check = grounding.check(answer, question, turn.results)
        if check["grounded"]:
            break
        log.info(json.dumps({"ungrounded_attempt": attempt + 1, **check}, ensure_ascii=False))
        prompt = (
            system_prompt(question)
            + "\n\n"
            + RETRY_NOTE.format(
                figures=", ".join(check["unmatched"]) or "none",
                words=", ".join(check["banned_words"]) or "none",
            )
        )
    reply = {
        "answer": answer,
        "tools_used": turn.tools_used,
        "ui_actions": turn.ui_actions,
        "grounding": check,
        "usage": usage,
        "model": model_name(),
        "seconds": round(time.perf_counter() - started, 1),
    }
    log.info(
        json.dumps(
            {"question_chars": len(question), "tools": [t["name"] for t in turn.tools_used]}
            | {key: reply[key] for key in ("usage", "seconds", "model")}
            | {"grounded": check["grounded"]},
            ensure_ascii=False,
        )
    )
    return reply


def _refusal(code: str, message: str) -> dict:
    return {"answer": message, "tools_used": [], "ui_actions": [], "error": code}


def _respond(status: int, payload: dict) -> dict:
    return {
        "statusCode": status,
        "headers": {"Content-Type": "application/json; charset=utf-8"},
        "body": json.dumps(payload, ensure_ascii=False),
    }


_table = None


def _rate_table():
    """The rate-limit table named by RATE_LIMIT_TABLE, or None when running without one."""
    global _table
    name = os.environ.get("RATE_LIMIT_TABLE")
    if name and _table is None:
        import boto3

        _table = boto3.resource("dynamodb").Table(name)
    return _table


def lambda_handler(event: dict, _context: object) -> dict:
    """Lambda Function URL entry point: POST {"question": "..."}."""
    body = event.get("body") or "{}"
    if event.get("isBase64Encoded"):
        body = base64.b64decode(body).decode("utf-8", "replace")
    try:
        question = json.loads(body).get("question", "")
    except (json.JSONDecodeError, AttributeError):
        question = ""
    if not isinstance(question, str):
        question = ""

    table = _rate_table()
    address = event.get("requestContext", {}).get("http", {}).get("sourceIp")
    if table is not None and address and not ratelimit.allow(address, table):
        log.info(json.dumps({"refused": "rate limit"}))
        return _respond(
            429,
            _refusal("rate_limited", "Too many questions from this address. Try again in an hour."),
        )
    try:
        reply = ask(question)
    except Exception:  # noqa: BLE001 - the caller gets a clean failure, the log gets the cause
        log.exception("ask failed")
        return _respond(
            502, _refusal("agent_failed", "The assistant could not answer. Please try again.")
        )
    return _respond(400 if "error" in reply else 200, reply)
