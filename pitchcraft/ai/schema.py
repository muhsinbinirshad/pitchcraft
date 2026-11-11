"""JSON schema for the plan the model returns (structured outputs)."""

from __future__ import annotations

from typing import Any


def _nullable(schema: dict) -> dict:
    return {"anyOf": [schema, {"type": "null"}]}


_STR = {"type": "string"}
_NSTR = _nullable(_STR)

OP_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "op": {
            "type": "string",
            "enum": ["replace_text", "set_text", "insert_after", "insert_rows", "delete", "insert_table", "delete_range"],
        },
        "find": _NSTR,
        "replace": _NSTR,
        "expect": _nullable({"type": "integer"}),
        "target": _NSTR,
        "anchor": _NSTR,
        "like": _NSTR,
        "items": _nullable(
            {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {"like": _STR, "text": _NSTR, "new_id": _NSTR},
                    "required": ["like", "text", "new_id"],
                    "additionalProperties": False,
                },
            }
        ),
        "rows": _nullable({"type": "array", "items": {"type": "array", "items": _STR}}),
        "targets": _nullable({"type": "array", "items": _STR}),
        "new_id": _NSTR,
        "reason": _STR,
        "evidence": _STR,
    },
    "required": [
        "op", "find", "replace", "expect", "target", "anchor", "like",
        "items", "rows", "targets", "new_id", "reason", "evidence",
    ],
    "additionalProperties": False,
}

PLAN_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "understanding": _STR,
        "facts": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"fact": _STR, "source": _STR},
                "required": ["fact", "source"],
                "additionalProperties": False,
            },
        },
        "questions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": _STR,
                    "question": _STR,
                    "why": _STR,
                    "options": {"type": "array", "items": _STR},
                    "blocking": {"type": "boolean"},
                },
                "required": ["id", "question", "why", "options", "blocking"],
                "additionalProperties": False,
            },
        },
        "fact_changes": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"old": _STR, "new": _STR},
                "required": ["old", "new"],
                "additionalProperties": False,
            },
        },
        "reference_terms": {"type": "array", "items": _STR},
        "proposal_meta": {
            "type": "object",
            "properties": {"client": _STR, "title": _STR, "tags": {"type": "array", "items": _STR}},
            "required": ["client", "title", "tags"],
            "additionalProperties": False,
        },
        "ops": {"type": "array", "items": OP_SCHEMA},
        "summary": {
            "type": "object",
            "properties": {
                "changes": {"type": "array", "items": _STR},
                "please_check": {"type": "array", "items": _STR},
            },
            "required": ["changes", "please_check"],
            "additionalProperties": False,
        },
    },
    "required": ["understanding", "facts", "questions", "fact_changes", "reference_terms", "proposal_meta", "ops", "summary"],
    "additionalProperties": False,
}

QA_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "issues": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "page": {"type": "integer"},
                    "severity": {"type": "string", "enum": ["high", "medium", "low"]},
                    "issue": _STR,
                },
                "required": ["page", "severity", "issue"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["issues"],
    "additionalProperties": False,
}

DOC_CHECK_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "is_proposal": {"type": "boolean"},
        "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
        "document_type": _STR,
        "company": _STR,
        "client": _STR,
        "summary": _STR,
        "concerns": {"type": "array", "items": _STR},
        "unsafe_content": {"type": "boolean"},
    },
    "required": ["is_proposal", "confidence", "document_type", "company", "client", "summary", "concerns", "unsafe_content"],
    "additionalProperties": False,
}
