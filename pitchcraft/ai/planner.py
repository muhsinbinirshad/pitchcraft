"""Build requests for the planner, the review pass and the visual check."""

from __future__ import annotations

import base64
import json
from pathlib import Path

from ..engine import Outline
from .client import JSONModel, Usage
from .inputs import PreparedInputs
from .prompts import DOC_CHECK_SYSTEM, NEW_DOC_ADDENDUM, PLANNER_SYSTEM, QA_SYSTEM, REVIEW_SYSTEM_ADDENDUM
from .schema import DOC_CHECK_SCHEMA, PLAN_SCHEMA, QA_SCHEMA


def _system(mode: str, review: bool = False) -> str:
    s = PLANNER_SYSTEM
    if mode == "new":
        s += NEW_DOC_ADDENDUM
    if review:
        s += REVIEW_SYSTEM_ADDENDUM
    return s


def _prefix(outline: Outline, inputs: PreparedInputs, doc_name: str) -> list[dict]:
    """Stable content first so it is cached between the plan and review calls."""
    return [
        {"type": "text", "text": f"<document name=\"{doc_name}\">\n{outline.text()}\n</document>"},
        *inputs.blocks,
    ]


def _request_text(instructions: str, answers: dict[str, str], questions: list[dict]) -> str:
    parts = [f"<instructions>\n{instructions.strip() or '(no written instructions; follow the attachments)'}\n</instructions>"]
    if answers:
        qmap = {q["id"]: q["question"] for q in questions}
        lines = [f"- {qmap.get(k, k)}\n  Answer: {v}" for k, v in answers.items() if v.strip()]
        parts.append("<answers>\n" + "\n".join(lines) + "\n</answers>")
    return "\n\n".join(parts)


def make_plan(model: JSONModel, *, mode: str, outline: Outline, inputs: PreparedInputs,
              instructions: str, answers: dict[str, str], prior_questions: list[dict],
              doc_name: str, existing_tags: list[str] | None = None) -> tuple[dict, Usage]:
    prefix = _prefix(outline, inputs, doc_name)
    content = prefix + [{"type": "text", "text": _request_text(instructions, answers, prior_questions)}]
    if existing_tags:
        content.append({"type": "text", "text": "<existing_tags>\n" + ", ".join(existing_tags[:200]) + "\n</existing_tags>"})
    return model.call(system=_system(mode), content=content, schema=PLAN_SCHEMA,
                      cache_prefix_blocks=len(prefix))


def make_review(model: JSONModel, *, mode: str, outline: Outline, inputs: PreparedInputs,
                instructions: str, answers: dict[str, str], prior_questions: list[dict],
                first_plan: dict, doc_name: str, leftovers: list[str] | None = None) -> tuple[dict, Usage]:
    prefix = _prefix(outline, inputs, doc_name)
    done = json.dumps({"summary": first_plan.get("summary"), "fact_changes": first_plan.get("fact_changes")},
                      ensure_ascii=False)
    content = prefix + [
        {"type": "text", "text": _request_text(instructions, answers, prior_questions)},
        {"type": "text", "text": f"<already_done>\n{done}\n</already_done>\nThe document above is the edited version."},
    ]
    if leftovers:
        content.append({"type": "text", "text": "<possible_leftovers>\n" + "\n".join(f"- {t}" for t in leftovers) + "\n</possible_leftovers>"})
    return model.call(system=_system(mode, review=True), content=content, schema=PLAN_SCHEMA,
                      cache_prefix_blocks=len(prefix))


def visual_check(model: JSONModel, pages: list[tuple[int, Path, Path | None]]) -> tuple[dict, Usage]:
    """pages: (page number, edited page image, same page of the original or None)."""
    content: list[dict] = []
    img = lambda p: {"type": "image", "source": {"type": "base64", "media_type": "image/png",  # noqa: E731
                                                  "data": base64.standard_b64encode(p.read_bytes()).decode()}}
    for num, after, before in pages[:10]:
        if before is not None:
            content += [{"type": "text", "text": f"Page {num} BEFORE (original)"}, img(before)]
        content += [{"type": "text", "text": f"Page {num} AFTER (edited)"}, img(after)]
    content.append({"type": "text", "text": "List layout problems that appear in the AFTER pages and are not already present in the BEFORE pages."})
    return model.call(system=QA_SYSTEM, content=content, schema=QA_SCHEMA)


def check_document(model: JSONModel, outline: Outline, name: str, max_chars: int = 60_000) -> tuple[dict, Usage]:
    text = outline.text(max_cell=200)
    if len(text) > max_chars:
        text = text[:max_chars] + "\n(outline truncated)"
    content = [{"type": "text", "text": f"<document name=\"{name}\">\n{text}\n</document>\nClassify this document."}]
    return model.call(system=DOC_CHECK_SYSTEM, content=content, schema=DOC_CHECK_SCHEMA)
