# 02_WORKER_v0.2.4.md

## Worker Execution (v0.2.4)

### W1. Navigation / Routing Implementation
**Scope**
- Refactor sidebar actions to route-based navigation.
- Ensure route pages exist and render independently:
  - `/dashboard`
  - `/study`
  - `/quiz`
  - `/flashcards`
  - `/mistakes`
- Ensure direct refresh on each route remains valid.

**Implementation Steps**
1. Replace mixed in-page toggles with route jump actions.
2. Add route handlers/components for `/flashcards` and `/mistakes`.
3. Ensure route init reads required persisted context (user/course).
4. Verify no shared business state between Quiz and Flashcards.

**DoD**
- [ ] Five routes are navigable from sidebar.
- [ ] Browser refresh on each route does not break page rendering.
- [ ] Quiz and Flashcards state are not coupled.

**Evidence**
- Commands:
  - `rg -n "dashboard|study|quiz|flashcards|mistakes|nav_page_selector" src/app.py`
- Manual path:
  - sidebar click through all routes + browser refresh each route.

---

### W2. Storage / DB Migration Implementation
**Scope**
- Add persistence for flashcards and mistakes entities.
- Implement uniqueness for mistakes dedup:
  - `unique(userId, flashcardId)`.
- Implement upsert behavior for unknown reviews:
  - `wrongCount++`, update `lastWrongAt`.

**Implementation Steps**
1. Add migration SQL for flashcard/mistake storage (additive only).
2. Add repository methods for create/list/update/upsert.
3. Implement upsert path for unknown action.
4. Keep migration safety invariants intact (lock/transaction/rollback/idempotency).

**DoD**
- [ ] New storage objects are created via migration.
- [ ] Dedup and upsert semantics are enforced.
- [ ] Migration works from clean DB and repeated runs.

**Evidence**
- Commands:
  - `python - <<PY ... migrate_to_latest(); latest_migration_version() ... PY`
  - `python scripts/self_check.py`
- Query checks:
  - uniqueness/index presence, upsert behavior verification.

---

### W3. API Implementation (MVP Endpoints)
**Scope**
- Implement endpoints defined in MASTER plan:
  - `POST /api/flashcards/generate`
  - `POST /api/flashcards/:id/review`
  - `GET  /api/mistakes`
  - `GET  /api/mistakes/review`
  - `POST /api/mistakes/:id/master`
  - `DELETE /api/mistakes/:id` (soft delete)

**Implementation Steps**
1. Add route handlers + request/response DTO validation.
2. Connect handlers to repository/service layer.
3. Enforce soft-delete/master state transitions.
4. Add minimal logs for generate/review/upsert.

**DoD**
- [ ] Endpoints return expected response shape and status codes.
- [ ] Review endpoint updates flashcard stats.
- [ ] Unknown review upserts mistakes.

**Evidence**
- Commands:
  - endpoint smoke calls via curl/postman collection
- Logs:
  - generation/review/upsert log lines captured.

---

### W4. Flashcards Page Implementation
**Scope**
- Reuse scope selector UI (chapter/file selection) from Quiz-style generation area.
- Implement deck generation + viewer flow:
  - generate deck
  - show card
  - showAnswer toggle
  - known/unknown actions
  - next card advance
- Provide empty/failure states.

**Implementation Steps**
1. Build Flashcards generation form with scope + count + mix options.
2. Call `/api/flashcards/generate` and store deck state.
3. Render MCQ and Knowledge cards with unified controls.
4. Wire `known/unknown` to `/api/flashcards/:id/review`.
5. Show `finished` state when deck completes.

**DoD**
- [ ] Mixed cards render correctly (`mcq` + `knowledge`).
- [ ] showAnswer and progression `i/N` work.
- [ ] known/unknown updates stats and behavior.
- [ ] failure/empty messages are user-visible.

**Evidence**
- Manual flow:
  - generate -> review cards -> finish state
- Search trace:
  - `rg -n "showAnswer|known|unknown|deckReady|finished" src/`

---

### W5. Mistakes Page Implementation
**Scope**
- Implement Mistakes list page with filter and actions.
- Implement mistakes review mode (active-only deck), optionally reusing FlashcardViewer.
- Implement master/archive operations.

**Implementation Steps**
1. Add mistakes list view with status filters.
2. Add review entry that loads active mistakes only.
3. Implement `master` action.
4. Implement `delete` action as soft delete (`archived`).

**DoD**
- [ ] Mistakes list/filter works.
- [ ] Review mode uses active mistakes only.
- [ ] Master/delete correctly change status.

**Evidence**
- Manual path:
  - unknown -> appears in mistakes -> review -> master/delete
- API checks:
  - `GET /api/mistakes`, `GET /api/mistakes/review` differences validated.

---

### W6. Edge Cases Checklist
**Scope**
- Ensure critical edge behaviors are stable.

**Checklist**
- [ ] Generator JSON parse fail triggers one retry.
- [ ] Repeated unknown does not duplicate mistake row; increments `wrongCount`.
- [ ] Empty deck state handled gracefully.
- [ ] No-mistakes state handled gracefully.
- [ ] Route refresh does not corrupt state.

**Evidence**
- Logs showing retry path.
- DB rows before/after repeated unknown action.
- UI screenshots for empty states.
