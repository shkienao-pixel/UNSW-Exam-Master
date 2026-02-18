# 01_ARCHITECT_v0.2.4.md

## 1. Routing Spec

### Page Routes (Top-level)
- `/dashboard` -> `DashboardPage`
- `/study` -> `StudyPage`
- `/quiz` -> `QuizPage`
- `/flashcards` -> `FlashcardsPage`
- `/mistakes` -> `MistakesPage`

### Routing Constraints
- Each route owns independent UI state and action flow.
- `QuizPage` and `FlashcardsPage` must not share business state containers.
- Route refresh must restore page-level state from persisted sources (DB/API) where needed.

### State Isolation Contract
- Quiz-only state keys: prefixed `quiz_*`.
- Flashcards-only state keys: prefixed `flash_*`.
- Mistakes-only state keys: prefixed `mistakes_*`.
- No cross-page write from Flashcards into Quiz state namespace.

---

## 2. Flashcards UI State Machine

### State Flow
- `idle` -> `generating` -> `deckReady` -> `reviewing` -> `finished`

### State Payload (MVP)
- `deckId: string | null`
- `cards: Flashcard[]`
- `index: number` (0-based)
- `showAnswer: boolean`
- `selectedOption?: number | null` (for MCQ card)

### Transition Rules
- `idle -> generating`: user clicks generate.
- `generating -> deckReady`: API returns valid deck JSON.
- `deckReady -> reviewing`: render first card.
- `reviewing -> reviewing`: user marks known/unknown, advance index.
- `reviewing -> finished`: `index >= cards.length`.
- `finished -> idle`: user starts a new generation.

---

## 3. Flashcard Rendering Contract

### Card Type: `mcq`
- Front render:
  - `front.stem`
  - `front.options[]` as selectable options
  - `showAnswer` toggle/button
- Back render (when `showAnswer=true`):
  - `back.answer`
  - `back.explanation`

### Card Type: `knowledge`
- Front render:
  - `front.stem`
  - `showAnswer` toggle/button
- Back render (when `showAnswer=true`):
  - `back.explanation`

### Shared Controls
- progress `i/N`
- `✅ Known`
- `❌ Unknown`

---

## 4. Generator Output JSON Schema (Strict)

```json
{
  "cards": [
    {
      "type": "mcq",
      "front": {"stem": "...", "options": ["A", "B", "C", "D"]},
      "back": {"answer": 2, "explanation": "..."},
      "sourceRefs": [{"fileId": "...", "page": 1, "chunkId": "...", "quote": "..."}]
    },
    {
      "type": "knowledge",
      "front": {"stem": "..."},
      "back": {"explanation": "..."},
      "sourceRefs": [{"fileId": "...", "page": 2, "chunkId": "...", "quote": "..."}]
    }
  ]
}
```

### Schema Enforcement
- Generator must return JSON only.
- Parse failure policy: retry generation once.
- `sourceRefs` must be grounded in provided chunk set (no fabricated references).

---

## 5. Mistakes Bank Architecture

### Persistence Model
- Mistakes item links to flashcard via `flashcardId`.
- Dedup rule: unique `(userId, flashcardId)`.
- Unknown action writes via upsert:
  - first time: create row (`wrongCount=1`)
  - repeat: increment `wrongCount`, update `lastWrongAt`.

### Query/Display
- Mistakes list query joins flashcard content for display.
- Mistakes review source contains only `status='active'` rows.
- Sort priority:
  - `wrongCount DESC`
  - `lastWrongAt DESC`.

### Status Operations
- `master` -> set `status='mastered'`.
- `delete` -> soft delete as `status='archived'`.

---

## 6. Service/API Architecture (MVP)

### Flashcards
- `POST /api/flashcards/generate`
  - input: scope + count + mix config
  - output: strict JSON deck schema
- `POST /api/flashcards/:id/review`
  - input: action `known|unknown`
  - effect: update flashcard stats; unknown triggers mistakes upsert

### Mistakes
- `GET /api/mistakes`
  - list + filter support
- `GET /api/mistakes/review`
  - active-only review deck
- `POST /api/mistakes/:id/master`
  - mark mastered
- `DELETE /api/mistakes/:id`
  - soft delete (archive)

---

## 7. Observability (Minimum Logs)
- `flashcards.generate(scope,count,mix)`
- `flashcards.review(cardId,action)`
- `mistakes.upsert(flashcardId,wrongCount)`

Log shape should include timestamp, userId, route, requestId for traceability.
