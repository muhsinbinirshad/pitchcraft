# Architecture

Pitchcraft is a modular monolith: one Python service (FastAPI) and a static web UI (Next.js).

```
your .docx ─▶ Word engine ──outline with ids──▶ Claude
                  ▲                                │
                  └──── edit operations (JSON) ────┘
                  │
                  ▼
          checks ─▶ new version (.docx + preview)
```

## Editing model

1. **Claude plans, code applies.** Claude reads an outline in which every block has an id: paragraphs, tables, rows, cells, headers and footers. It returns operations such as replace text, insert, delete, insert table and delete range. It never writes XML.
2. **New content is a copy.** New headings, bullets, rows and tables are cloned from elements already in the template, so all formatting comes from the user's document.
3. **Edits cite sources.** Each operation states its evidence. When a decision is missing, Claude returns a question instead of a guess.
4. **Rollback.** An operation that fails is rolled back; the others still apply.

## Checks

These run on every version:

| Check | What it ensures |
|---|---|
| Numbers | Every number comes from the request or attachments, or is calculated from them. |
| Stale values | A value that changed doesn't remain anywhere else. |
| Leftovers | The template's previous client details are gone. |
| Placeholders | No `[placeholder]` text was written. |
| Styles | No formatting was added that the template doesn't already have. |
| Structure and render | The document is well formed and renders cleanly. |

A review pass then has Claude re-read the result and fix anything left over. An optional visual check compares the changed pages before and after.

## Code layout

```
pitchcraft/
  engine/     Word engine (no AI): outline ids, edit ops, checks, structural diff, rendering
  ai/         Claude client, prompts, attachment readers, planner and review pass
  pipeline/   File store and the plan → questions → apply → check workflow
  api/        HTTP API, sign-in, serves the web UI
frontend/     Next.js static export
tests/        Offline tests and a browser walk-through
```
