"""Integration tests for course_workspace_service against a real SQLite DB."""

from __future__ import annotations

import pytest

import services.course_workspace_service as cws


class TestCourseLifecycle:
    def test_create_and_list_course(self, tmp_db):
        course = cws.create_course("COMP3900", "Project Comp")
        assert course["code"] == "COMP3900"
        assert course["name"] == "Project Comp"

        courses = cws.list_courses()
        codes = [c["code"] for c in courses]
        assert "COMP3900" in codes

    def test_get_course_by_id(self, tmp_db):
        created = cws.create_course("MATH1141", "Higher Maths")
        fetched = cws.get_course(created["id"])
        assert fetched is not None
        assert fetched["code"] == "MATH1141"

    def test_get_course_not_found_returns_none(self, tmp_db):
        assert cws.get_course("nonexistent-id") is None

    def test_duplicate_course_code_raises(self, tmp_db):
        cws.create_course("COMP9900", "Software Project")
        with pytest.raises(cws.WorkspaceValidationError):
            cws.create_course("COMP9900", "Duplicate")

    def test_create_course_empty_code_raises(self, tmp_db):
        with pytest.raises(cws.WorkspaceValidationError):
            cws.create_course("", "No code")

    def test_create_course_empty_name_raises(self, tmp_db):
        with pytest.raises(cws.WorkspaceValidationError):
            cws.create_course("COMP1111", "")

    def test_course_code_normalized_uppercase(self, tmp_db):
        course = cws.create_course("comp1511", "Programming Fundamentals")
        assert course["code"] == "COMP1511"


class TestArtifacts:
    def test_save_and_list_artifact(self, tmp_db):
        course = cws.create_course("COMP3331", "Networks")
        artifact = cws.save_artifact(course["id"], "lecture1.pdf", b"pdf content here")
        assert artifact["file_name"] == "lecture1.pdf"

        artifacts = cws.list_artifacts(course["id"])
        names = [a["file_name"] for a in artifacts]
        assert "lecture1.pdf" in names

    def test_duplicate_artifact_deduplicated(self, tmp_db):
        course = cws.create_course("COMP3821", "Algorithms")
        data = b"same content"
        cws.save_artifact(course["id"], "notes.pdf", data)
        cws.save_artifact(course["id"], "notes.pdf", data)
        # Same hash — should not duplicate
        artifacts = cws.list_artifacts(course["id"])
        assert len(artifacts) == 1

    def test_list_artifacts_empty_course(self, tmp_db):
        course = cws.create_course("COMP4920", "Ethics")
        assert cws.list_artifacts(course["id"]) == []


class TestScopeSets:
    def test_create_and_list_scope_sets(self, tmp_db):
        course = cws.create_course("COMP6771", "C++ Prog")
        scope_id = cws.create_scope_set(course["id"], "Week 1-3")
        scopes = cws.list_scope_sets(course["id"])
        ids = [s["id"] for s in scopes]
        assert scope_id in ids

    def test_ensure_default_scope_set(self, tmp_db):
        course = cws.create_course("COMP9313", "BigData")
        default = cws.ensure_default_scope_set(course["id"])
        assert default["is_default"] == 1

    def test_ensure_default_idempotent(self, tmp_db):
        course = cws.create_course("COMP9318", "DataWarehouse")
        d1 = cws.ensure_default_scope_set(course["id"])
        d2 = cws.ensure_default_scope_set(course["id"])
        assert d1["id"] == d2["id"]

    def test_rename_scope_set(self, tmp_db):
        course = cws.create_course("COMP9517", "CV")
        scope_id = cws.create_scope_set(course["id"], "Old Name")
        renamed = cws.rename_scope_set(scope_id, "New Name")
        assert renamed["name"] == "New Name"

    def test_delete_scope_set(self, tmp_db):
        course = cws.create_course("COMP9444", "NeuralNets")
        scope_id = cws.create_scope_set(course["id"], "To Delete")
        cws.delete_scope_set(scope_id)
        scopes = cws.list_scope_sets(course["id"])
        assert all(s["id"] != scope_id for s in scopes)

    def test_get_scope_set(self, tmp_db):
        course = cws.create_course("COMP4336", "Mobile")
        scope_id = cws.create_scope_set(course["id"], "Mid-term")
        scope = cws.get_scope_set(scope_id)
        assert scope is not None
        assert scope["name"] == "Mid-term"


class TestOutputs:
    def test_create_and_list_output(self, tmp_db):
        course = cws.create_course("COMP3153", "Logic")
        out_id = cws.create_output(
            course_id=course["id"],
            output_type="summary",
            content="This is a summary.",
        )
        assert isinstance(out_id, int)
        outputs = cws.list_outputs(course["id"])
        assert any(o["id"] == out_id for o in outputs)

    def test_get_output_by_id(self, tmp_db):
        course = cws.create_course("COMP3231", "OS")
        out_id = cws.create_output(course["id"], "quiz", '{"questions": []}')
        out = cws.get_output(out_id)
        assert out is not None
        assert out["output_type"] == "quiz"

    def test_list_outputs_filtered_by_type(self, tmp_db):
        course = cws.create_course("COMP3211", "Arch")
        cws.create_output(course["id"], "summary", "S1")
        cws.create_output(course["id"], "graph", "G1")
        summaries = cws.list_outputs(course["id"], output_type="summary")
        assert all(o["output_type"] == "summary" for o in summaries)

    def test_invalid_output_type_raises(self, tmp_db):
        course = cws.create_course("COMP3111", "SWE")
        with pytest.raises(cws.WorkspaceValidationError):
            cws.create_output(course["id"], "invalid_type", "content")
