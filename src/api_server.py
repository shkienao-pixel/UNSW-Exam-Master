"""Minimal HTTP API server for v0.2.4 flashcards and mistakes."""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, urlparse
from uuid import uuid4

from migrations.migrate import migrate_to_latest
from services.flashcards_mistakes_service import (
    archive_mistake,
    list_mistakes,
    list_mistakes_review,
    mark_mistake_master,
    review_flashcard,
    save_generated_flashcards,
    submit_flashcard_answer,
)

LOGGER = logging.getLogger("v024.api")


def _now_iso() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat()


def _safe_int(value: Any, default: int = 20) -> int:
    try:
        out = int(value)
    except (TypeError, ValueError):
        return default
    return out


def _normalize_scope(raw_scope: Any) -> dict[str, Any]:
    scope = raw_scope if isinstance(raw_scope, dict) else {}
    chapter_ids = scope.get("chapterIds") if isinstance(scope.get("chapterIds"), list) else []
    file_ids = scope.get("fileIds") if isinstance(scope.get("fileIds"), list) else []
    normalized_file_ids: list[int] = []
    for v in file_ids:
        try:
            normalized_file_ids.append(int(v))
        except (TypeError, ValueError):
            continue
    return {
        "chapterIds": [str(v) for v in chapter_ids],
        "fileIds": sorted(set(normalized_file_ids)),
    }


def _normalize_mix(raw_mix: Any) -> tuple[float, float]:
    mix = raw_mix if isinstance(raw_mix, dict) else {}
    try:
        mcq = float(mix.get("mcq", 0.6))
    except (TypeError, ValueError):
        mcq = 0.6
    try:
        knowledge = float(mix.get("knowledge", 0.4))
    except (TypeError, ValueError):
        knowledge = max(0.0, 1.0 - mcq)
    if mcq < 0:
        mcq = 0.0
    if knowledge < 0:
        knowledge = 0.0
    total = mcq + knowledge
    if total <= 0:
        return 0.6, 0.4
    return mcq / total, knowledge / total


def _source_ref_from_chunk(chunk: dict[str, Any], fallback_file_id: str = "") -> dict[str, Any]:
    return {
        "fileId": str(chunk.get("fileId") or fallback_file_id or "unknown"),
        "page": chunk.get("page"),
        "chunkId": chunk.get("chunkId"),
        "quote": chunk.get("quote") or chunk.get("text") or "",
    }


def _build_cards_object(payload: dict[str, Any]) -> dict[str, Any]:
    user_scope = _normalize_scope(payload.get("scope"))
    count = max(1, min(50, _safe_int(payload.get("count"), 20)))
    mcq_ratio, _ = _normalize_mix(payload.get("mix"))
    chunks = payload.get("chunks") if isinstance(payload.get("chunks"), list) else []
    valid_chunks = [c for c in chunks if isinstance(c, dict)]
    file_ids = user_scope.get("fileIds") if isinstance(user_scope.get("fileIds"), list) else []
    fallback_file_id = str(file_ids[0]) if file_ids else "unknown"

    mcq_count = int(round(count * mcq_ratio))
    mcq_count = max(0, min(count, mcq_count))
    knowledge_count = count - mcq_count

    cards: list[dict[str, Any]] = []
    chunk_cursor = 0

    for i in range(mcq_count):
        chunk = valid_chunks[chunk_cursor % len(valid_chunks)] if valid_chunks else {}
        chunk_cursor += 1
        stem_hint = str(chunk.get("text") or chunk.get("quote") or "").strip()
        if not stem_hint:
            stem_hint = f"Scope question #{i + 1}"
        card = {
            "type": "mcq",
            "front": {
                "stem": f"{stem_hint[:180]} (MCQ)",
                "options": ["A", "B", "C", "D"],
            },
            "back": {
                "answer": 2,
                "explanation": "Option B is the best-supported answer based on provided scope chunks.",
            },
            "sourceRefs": [_source_ref_from_chunk(chunk, fallback_file_id)],
        }
        cards.append(card)

    for i in range(knowledge_count):
        chunk = valid_chunks[chunk_cursor % len(valid_chunks)] if valid_chunks else {}
        chunk_cursor += 1
        stem_hint = str(chunk.get("text") or chunk.get("quote") or "").strip()
        if not stem_hint:
            stem_hint = f"Scope concept #{i + 1}"
        card = {
            "type": "knowledge",
            "front": {
                "stem": f"{stem_hint[:180]} (Knowledge)",
            },
            "back": {
                "explanation": "Key explanation synthesized from selected scope materials.",
            },
            "sourceRefs": [_source_ref_from_chunk(chunk, fallback_file_id)],
        }
        cards.append(card)

    return {"cards": cards}


def _generate_cards_json_with_retry(payload: dict[str, Any]) -> tuple[dict[str, Any], int]:
    attempts = 0
    last_error: Exception | None = None
    while attempts < 2:
        attempts += 1
        try:
            raw = json.dumps(_build_cards_object(payload), ensure_ascii=False)
            parsed = json.loads(raw)
            cards = parsed.get("cards") if isinstance(parsed, dict) else None
            if not isinstance(cards, list):
                raise ValueError("invalid cards payload")
            return parsed, attempts
        except Exception as e:  # pragma: no cover - safeguard branch
            last_error = e
    raise ValueError(f"generate parse failed after retry: {last_error}")


class ApiHandler(BaseHTTPRequestHandler):
    server_version = "UNSWExamAPI/0.2.4"

    def _send_json(self, code: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET,POST,DELETE,OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self) -> dict[str, Any]:
        raw_len = self.headers.get("Content-Length")
        try:
            length = int(raw_len or "0")
        except ValueError:
            length = 0
        if length <= 0:
            return {}
        raw = self.rfile.read(length)
        try:
            parsed = json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}

    def do_OPTIONS(self) -> None:  # noqa: N802
        self._send_json(HTTPStatus.NO_CONTENT, {})

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        path = parsed.path
        query = parse_qs(parsed.query)

        if path == "/health":
            self._send_json(HTTPStatus.OK, {"ok": True, "time": _now_iso()})
            return

        if path == "/api/mistakes":
            user_id = str((query.get("userId") or ["default"])[0])
            status = str((query.get("status") or [""])[0])
            card_type = str((query.get("type") or [""])[0])
            rows = list_mistakes(user_id=user_id, status=status, card_type=card_type)
            self._send_json(HTTPStatus.OK, {"items": rows, "count": len(rows)})
            return

        if path == "/api/mistakes/review":
            user_id = str((query.get("userId") or ["default"])[0])
            card_type = str((query.get("type") or [""])[0])
            rows = list_mistakes_review(user_id=user_id, card_type=card_type)
            self._send_json(HTTPStatus.OK, {"items": rows, "count": len(rows)})
            return

        self._send_json(HTTPStatus.NOT_FOUND, {"error": "not_found"})

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        path = parsed.path
        body = self._read_json()

        if path == "/api/flashcards/generate":
            user_id = str(body.get("userId") or "default")
            course_id = str(body.get("courseId") or "")
            scope = _normalize_scope(body.get("scope"))
            count = max(1, min(50, _safe_int(body.get("count"), 20)))
            mix = body.get("mix") if isinstance(body.get("mix"), dict) else {"mcq": 0.6, "knowledge": 0.4}
            LOGGER.info("flashcards.generate(scope=%s,count=%s,mix=%s)", scope, count, mix)
            try:
                generated, attempts = _generate_cards_json_with_retry(
                    {
                        "scope": scope,
                        "count": count,
                        "mix": mix,
                        "chunks": body.get("chunks"),
                    }
                )
            except Exception as e:
                self._send_json(HTTPStatus.BAD_REQUEST, {"error": str(e)})
                return

            deck_id = str(uuid4())
            cards = generated.get("cards") if isinstance(generated.get("cards"), list) else []
            saved = save_generated_flashcards(
                user_id=user_id,
                course_id=course_id,
                deck_id=deck_id,
                cards=[c for c in cards if isinstance(c, dict)],
                scope=scope,
            )
            self._send_json(
                HTTPStatus.OK,
                {
                    "deckId": deck_id,
                    "cards": saved,
                    "count": len(saved),
                    "generatedAt": _now_iso(),
                    "attempts": attempts,
                },
            )
            return

        review_match = re.fullmatch(r"/api/flashcards/([^/]+)/review", path)
        if review_match:
            card_id = review_match.group(1)
            user_id = str(body.get("userId") or "default")
            action = str(body.get("action") or "")
            LOGGER.info("flashcards.review(cardId=%s,action=%s)", card_id, action)
            try:
                result = review_flashcard(user_id=user_id, card_id=card_id, action=action)
            except Exception as e:
                self._send_json(HTTPStatus.BAD_REQUEST, {"error": str(e)})
                return
            if result.get("mistake"):
                m = result["mistake"]
                LOGGER.info(
                    "mistakes.upsert(flashcardId=%s,wrongCount=%s)",
                    m.get("flashcardId"),
                    m.get("wrongCount"),
                )
            self._send_json(HTTPStatus.OK, result)
            return

        submit_match = re.fullmatch(r"/api/flashcards/([^/]+)/submit", path)
        if submit_match:
            card_id = submit_match.group(1)
            user_id = str(body.get("userId") or "default")
            selected_option = body.get("selectedOption")
            LOGGER.info("flashcards.submit(cardId=%s)", card_id)
            try:
                result = submit_flashcard_answer(user_id=user_id, card_id=card_id, selected_option=selected_option)
            except Exception as e:
                self._send_json(HTTPStatus.BAD_REQUEST, {"error": str(e)})
                return
            if result.get("mistake"):
                m = result["mistake"]
                LOGGER.info(
                    "mistakes.upsert(flashcardId=%s,wrongCount=%s)",
                    m.get("flashcardId"),
                    m.get("wrongCount"),
                )
            self._send_json(HTTPStatus.OK, result)
            return

        master_match = re.fullmatch(r"/api/mistakes/([^/]+)/master", path)
        if master_match:
            mistake_id = int(master_match.group(1))
            user_id = str(body.get("userId") or "default")
            updated = mark_mistake_master(user_id=user_id, mistake_id=mistake_id)
            if not updated:
                self._send_json(HTTPStatus.NOT_FOUND, {"error": "mistake_not_found"})
                return
            self._send_json(HTTPStatus.OK, {"ok": True, "id": mistake_id, "status": "mastered"})
            return

        self._send_json(HTTPStatus.NOT_FOUND, {"error": "not_found"})

    def do_DELETE(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        path = parsed.path
        query = parse_qs(parsed.query)
        delete_match = re.fullmatch(r"/api/mistakes/([^/]+)", path)
        if delete_match:
            mistake_id = int(delete_match.group(1))
            user_id = str((query.get("userId") or ["default"])[0])
            archived = archive_mistake(user_id=user_id, mistake_id=mistake_id)
            if not archived:
                self._send_json(HTTPStatus.NOT_FOUND, {"error": "mistake_not_found"})
                return
            self._send_json(HTTPStatus.OK, {"ok": True, "id": mistake_id, "status": "archived"})
            return

        self._send_json(HTTPStatus.NOT_FOUND, {"error": "not_found"})


def run_api_server(host: str = "127.0.0.1", port: int = 8800) -> None:
    migrate_to_latest()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    server = ThreadingHTTPServer((host, port), ApiHandler)
    LOGGER.info("API server listening on http://%s:%s", host, port)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    run_api_server()
