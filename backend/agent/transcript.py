"""Runs the scripted questions and writes the transcript (brief §10.6)."""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from agent import data, handler

TESTS = Path(__file__).with_name("tests")
# Approximate list prices on Amazon Bedrock, US dollars per million tokens (input, output),
# read from the Bedrock pricing page on 2026-10-11. The page listed these models for other
# regions; their US West (Oregon) prices were not on the part of the page that was read.
PRICES = {
    "openai.gpt-oss-120b": (0.15, 0.60),
    "mistral.mistral-large-3-675b-instruct": (0.52, 1.55),
}


def questions() -> list[str]:
    lines = (TESTS / "questions.md").read_text().splitlines()
    return [line[2:].strip() for line in lines if line.startswith("- ")]


def run(log: Callable[[str], None] = lambda _: None) -> tuple[Path, dict]:
    """Ask every scripted question. Returns the transcript's path and a summary."""
    replies = []
    for number, question in enumerate(questions(), 1):
        reply = handler.ask(question)
        replies.append((question, reply))
        verdict = "grounded" if reply["grounding"]["grounded"] else "NOT GROUNDED"
        log(f"{number:>2}. {verdict:<12} {reply['seconds']:>5.1f} s  {question[:60]}")

    tokens_in = sum(reply["usage"]["input_tokens"] for _, reply in replies)
    tokens_out = sum(reply["usage"]["output_tokens"] for _, reply in replies)
    model = replies[0][1]["model"]
    price = PRICES.get(model.partition(":")[2])
    cost = None if price is None else (tokens_in * price[0] + tokens_out * price[1]) / 1e6
    summary = {
        "model": model,
        "questions": len(replies),
        "grounded": sum(1 for _, reply in replies if reply["grounding"]["grounded"]),
        "answered_without_tools": sum(1 for _, reply in replies if not reply["tools_used"]),
        "input_tokens": tokens_in,
        "output_tokens": tokens_out,
        "estimated_cost_usd": None if cost is None else round(cost, 4),
    }
    spent = (
        "No list price on file for this model."
        if price is None
        else f"Estimated cost ${cost:.4f} at about ${price[0]:.2f} and ${price[1]:.2f} per "
        "million tokens (approximate list prices; the exact US price was not confirmed)."
    )
    latest = data.load("latest.json")
    lines = [
        "# Agent transcript",
        "",
        f"- Run: {datetime.now(UTC).isoformat(timespec='seconds')}",
        f"- Model: `{model}`",
        f"- Data: season {latest['season']}, through {latest['data_through']}, "
        f"published {latest['generated_at']}",
        f"- Grounded: {summary['grounded']} of {summary['questions']}. A reply is grounded when "
        "every number in it is in that turn's tool results or the question (to within one unit "
        "of its last digit) and it uses none of the words the project rules out. The check is "
        "mechanical: it catches invented figures, not a true figure used for the wrong thing.",
        f"- Tokens: {tokens_in:,} in, {tokens_out:,} out. {spent}",
        "",
    ]
    for number, (question, reply) in enumerate(replies, 1):
        check = reply["grounding"]
        lines += [f"## {number}. {question}", ""]
        if reply["tools_used"]:
            for call in reply["tools_used"]:
                arguments = json.dumps(call["input"], ensure_ascii=False)
                status = "" if call["ok"] else " (returned an error)"
                lines.append(f"- Tool: `{call['name']}` {arguments}{status}")
        else:
            lines.append("- Tool: none")
        actions = ", ".join(action["type"] for action in reply["ui_actions"]) or "none"
        lines.append(f"- Map actions: {actions}")
        verdict = "yes" if check["grounded"] else "NO"
        detail = f"{check['numbers']} numbers checked"
        if check["unmatched"]:
            detail += f"; not found in tool results: {', '.join(check['unmatched'])}"
        if check["banned_words"]:
            detail += f"; ruled-out words: {', '.join(check['banned_words'])}"
        lines.append(f"- Grounded: {verdict} ({detail})")
        lines.append(
            f"- {reply['usage']['input_tokens']:,} tokens in, "
            f"{reply['usage']['output_tokens']:,} out, {reply['seconds']} s"
        )
        lines += ["", *[f"> {line}" if line else ">" for line in reply["answer"].splitlines()], ""]
    path = TESTS / "transcript.md"
    path.write_text("\n".join(lines))
    return path, summary
