"""Integration tests for flashcards_mistakes_service against a real SQLite DB."""

from __future__ import annotations

import pytest

import services.flashcards_mistakes_service as fm


def _make_cards(n: int = 2) -> list[dict]:
    return [
        {
            "type": "mcq",  # service checks card.get("type"), not "card_type"
            "front": {"question": f"Q{i}?", "options": ["A", "B", "C", "D"]},
            "back": {
                "correct_answer": "A",
                "explanation": f"Exp{i}",
                "answer_zh": "A",
                "explanation_zh": f"解释{i}",
            },
        }
        for i in range(n)
    ]


class TestSaveFlashcards:
    def test_save_returns_list_of_dicts(self, tmp_db):
        saved = fm.save_generated_flashcards(
            user_id="u1",
            course_id="COMP3900",
            deck_id="deck1",
            cards=_make_cards(3),
        )
        assert isinstance(saved, list)
        assert len(saved) == 3

    def test_saved_cards_retrievable(self, tmp_db):
        saved = fm.save_generated_flashcards("u1", "COMP3900", "deck1", _make_cards(2))
        cards = fm.list_flashcards_by_deck("u1", "deck1")
        assert len(cards) == 2

    def test_get_flashcard_by_id(self, tmp_db):
        saved = fm.save_generated_flashcards("u1", "COMP3900", "deck1", _make_cards(1))
        card_id = saved[0]["id"]
        fetched = fm.get_flashcard(card_id, "u1")
        assert fetched is not None
        assert fetched["id"] == card_id

    def test_get_flashcard_wrong_user_returns_none(self, tmp_db):
        saved = fm.save_generated_flashcards("u1", "COMP3900", "deck1", _make_cards(1))
        card_id = saved[0]["id"]
        # Different user cannot access
        assert fm.get_flashcard(card_id, "other_user") is None

    def test_save_empty_cards_returns_empty(self, tmp_db):
        saved = fm.save_generated_flashcards("u1", "COMP3900", "deck1", [])
        assert saved == []


class TestReviewFlashcard:
    def test_review_known(self, tmp_db):
        saved = fm.save_generated_flashcards("u1", "COMP3900", "deck1", _make_cards(1))
        card_id = saved[0]["id"]
        result = fm.review_flashcard("u1", card_id, "known")
        assert result["flashcard"]["id"] == card_id
        assert result["mistake"] is None  # "known" should not create a mistake

    def test_review_unknown_creates_mistake(self, tmp_db):
        saved = fm.save_generated_flashcards("u1", "COMP3900", "deck1", _make_cards(1))
        card_id = saved[0]["id"]
        result = fm.review_flashcard("u1", card_id, "unknown")
        assert result["mistake"] is not None
        assert result["mistake"]["status"] == "active"

    def test_review_unknown_increments_wrong_count(self, tmp_db):
        saved = fm.save_generated_flashcards("u1", "COMP3900", "deck1", _make_cards(1))
        card_id = saved[0]["id"]
        fm.review_flashcard("u1", card_id, "unknown")
        result2 = fm.review_flashcard("u1", card_id, "unknown")
        assert result2["mistake"]["wrongCount"] == 2  # camelCase in return value


class TestSubmitAnswer:
    def test_correct_answer_not_mistake(self, tmp_db):
        cards = [
            {
                "type": "mcq",
                "front": {"question": "What?", "options": ["A", "B", "C", "D"]},
                "back": {"correct_answer": "A", "explanation": "A is correct"},
            }
        ]
        saved = fm.save_generated_flashcards("u1", "COMP3900", "deck1", cards)
        card_id = saved[0]["id"]
        result = fm.submit_flashcard_answer("u1", card_id, "A")
        assert result["isCorrect"] is True
        assert result["mistake"] is None

    def test_wrong_answer_creates_mistake(self, tmp_db):
        cards = [
            {
                "type": "mcq",
                "front": {"question": "What?", "options": ["A", "B", "C", "D"]},
                "back": {"correct_answer": "A", "explanation": "A is correct"},
            }
        ]
        saved = fm.save_generated_flashcards("u1", "COMP3900", "deck1", cards)
        card_id = saved[0]["id"]
        result = fm.submit_flashcard_answer("u1", card_id, "B")
        assert result["isCorrect"] is False
        assert result["mistake"] is not None


class TestMistakesManagement:
    def test_upsert_mistake_creates_entry(self, tmp_db):
        saved = fm.save_generated_flashcards("u1", "COMP3900", "deck1", _make_cards(1))
        card_id = saved[0]["id"]
        mistake = fm.upsert_mistake("u1", card_id)
        assert mistake["flashcardId"] == card_id  # camelCase in return value
        assert mistake["wrongCount"] == 1

    def test_upsert_mistake_increments(self, tmp_db):
        saved = fm.save_generated_flashcards("u1", "COMP3900", "deck1", _make_cards(1))
        card_id = saved[0]["id"]
        fm.upsert_mistake("u1", card_id)
        m2 = fm.upsert_mistake("u1", card_id)
        assert m2["wrongCount"] == 2

    def test_list_mistakes_active(self, tmp_db):
        saved = fm.save_generated_flashcards("u1", "COMP3900", "deck1", _make_cards(2))
        fm.upsert_mistake("u1", saved[0]["id"])
        fm.upsert_mistake("u1", saved[1]["id"])
        mistakes = fm.list_mistakes("u1", status="active")
        assert len(mistakes) == 2

    def test_mark_mistake_master(self, tmp_db):
        saved = fm.save_generated_flashcards("u1", "COMP3900", "deck1", _make_cards(1))
        card_id = saved[0]["id"]
        mistake = fm.upsert_mistake("u1", card_id)
        success = fm.mark_mistake_master("u1", mistake["id"])
        assert success is True
        mastered = fm.list_mistakes("u1", status="mastered")
        assert any(m["id"] == mistake["id"] for m in mastered)

    def test_archive_mistake(self, tmp_db):
        saved = fm.save_generated_flashcards("u1", "COMP3900", "deck1", _make_cards(1))
        card_id = saved[0]["id"]
        mistake = fm.upsert_mistake("u1", card_id)
        success = fm.archive_mistake("u1", mistake["id"])
        assert success is True
        active = fm.list_mistakes("u1", status="active")
        assert not any(m["id"] == mistake["id"] for m in active)

    def test_list_mistakes_review_only_active(self, tmp_db):
        saved = fm.save_generated_flashcards("u1", "COMP3900", "deck1", _make_cards(2))
        m1 = fm.upsert_mistake("u1", saved[0]["id"])
        fm.upsert_mistake("u1", saved[1]["id"])
        fm.mark_mistake_master("u1", m1["id"])
        review = fm.list_mistakes_review("u1")
        # Only 1 active remains
        assert len(review) == 1
