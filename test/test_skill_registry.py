"""Tests for hydroagent.skill_registry."""

from pathlib import Path

from hydroagent.skill_registry import _parse_frontmatter, SkillRegistry


class TestParseFrontmatter:
    def test_well_formed(self):
        text = """---
name: Test Skill
description: A test skill
keywords: [kw1, kw2]
tools: [tool_a, tool_b]
when_to_use: When testing
---
# Heading
Body content here."""
        meta, body = _parse_frontmatter(text)
        assert meta["name"] == "Test Skill"
        assert meta["description"] == "A test skill"
        assert meta["keywords"] == ["kw1", "kw2"]
        assert meta["tools"] == ["tool_a", "tool_b"]
        assert meta["when_to_use"] == "When testing"
        assert "# Heading" in body
        assert "Body content here" in body

    def test_no_frontmatter(self):
        text = "# Just markdown\nNo frontmatter here."
        meta, body = _parse_frontmatter(text)
        assert meta == {}
        assert body == text

    def test_empty_frontmatter(self):
        text = "---\n---\nBody"
        meta, body = _parse_frontmatter(text)
        # Regex needs content between --- markers: "---\nCONTENT\n---\n"
        # "---\n---\nBody" has nothing between the dashes so it doesn't match
        assert meta == {}
        assert body == text  # returned as-is

    def test_only_opening_dashes(self):
        text = "---\nname: incomplete\nNo closing dashes"
        meta, body = _parse_frontmatter(text)
        assert meta == {}

    def test_extra_fields(self):
        text = """---
name: Extra
custom_field: custom_value
---
Body."""
        meta, body = _parse_frontmatter(text)
        assert meta["name"] == "Extra"
        assert meta["custom_field"] == "custom_value"

    def test_missing_body(self):
        text = "---\nname: NoBody\n---\n"
        meta, body = _parse_frontmatter(text)
        assert meta["name"] == "NoBody"
        assert body.strip() == ""

    def test_invalid_yaml_is_graceful(self):
        text = "---\n: invalid yaml :::\n---\nBody"
        meta, body = _parse_frontmatter(text)
        assert meta == {}  # graceful fallback
        assert "Body" in body

    def test_cognitive_skill_metadata(self):
        text = """---
name: System Prompt Skill
type: cognitive
inject: always
---
Content."""
        meta, _ = _parse_frontmatter(text)
        assert meta["type"] == "cognitive"
        assert meta["inject"] == "always"


class TestSkillRegistry:
    def test_empty_dir(self, tmp_path):
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()
        registry = SkillRegistry(skills_dir)
        assert len(registry.skills) == 0

    def test_missing_dir(self, tmp_path):
        registry = SkillRegistry(tmp_path / "nonexistent")
        assert len(registry.skills) == 0

    def test_single_skill(self, tmp_path):
        skills_dir = tmp_path / "skills"
        skill_dir = skills_dir / "calibrate"
        skill_dir.mkdir(parents=True)
        (skill_dir / "skill.md").write_text("""---
name: Calibrate
description: Calibrate hydrological models
keywords: [calibrate, model, parameter]
tools: [calibrate_model, llm_calibrate]
when_to_use: When the user wants to calibrate
---
# Calibrate Skill
Steps to calibrate.""")
        registry = SkillRegistry(skills_dir)
        assert "calibrate" in registry.skills
        s = registry.skills["calibrate"]
        assert s["name"] == "Calibrate"
        assert s["keywords"] == ["calibrate", "model", "parameter"]
        assert s["tools"] == ["calibrate_model", "llm_calibrate"]
        assert "Steps to calibrate" in s["content"]

    def test_multiple_skills(self, tmp_path):
        skills_dir = tmp_path / "skills"
        for name in ["skill_a", "skill_b", "skill_c"]:
            sd = skills_dir / name
            sd.mkdir(parents=True)
            (sd / "skill.md").write_text(f"---\nname: {name}\n---\nContent for {name}.")
        registry = SkillRegistry(skills_dir)
        assert len(registry.skills) == 3
        assert set(registry.skills.keys()) == {"skill_a", "skill_b", "skill_c"}

    def test_skill_without_frontmatter_gets_fallback(self, tmp_path):
        skills_dir = tmp_path / "skills"
        sd = skills_dir / "basic"
        sd.mkdir(parents=True)
        (sd / "skill.md").write_text("# Basic Skill\nJust content, no frontmatter.")
        registry = SkillRegistry(skills_dir)
        assert "basic" in registry.skills
        assert registry.skills["basic"]["name"] == "basic"

    def test_keyword_match(self, tmp_path):
        skills_dir = tmp_path / "skills"
        sd = skills_dir / "hydrology"
        sd.mkdir(parents=True)
        (sd / "skill.md").write_text("""---
name: Hydrology
keywords: [basin, streamflow, rainfall, runoff]
---
Hydrology workflow.""")
        registry = SkillRegistry(skills_dir)
        results = registry.match("calibrate the streamflow model for a basin")
        assert len(results) > 0

    def test_keyword_no_match(self, tmp_path):
        skills_dir = tmp_path / "skills"
        sd = skills_dir / "specialized"
        sd.mkdir(parents=True)
        (sd / "skill.md").write_text("""---
name: Specialized
keywords: [xyzzy, plugh]
---
Specialized content.""")
        registry = SkillRegistry(skills_dir)
        results = registry.match("calibrate a gr4j model")
        assert len(results) == 0

    def test_default_skill_type_is_task(self, tmp_path):
        skills_dir = tmp_path / "skills"
        sd = skills_dir / "task_skill"
        sd.mkdir(parents=True)
        (sd / "skill.md").write_text("---\nname: Task\n---\nTask content.")
        registry = SkillRegistry(skills_dir)
        assert registry.skills["task_skill"]["type"] == "task"
        assert registry.skills["task_skill"]["inject"] == "on_match"

    def test_cognitive_skill(self, tmp_path):
        skills_dir = tmp_path / "skills"
        sd = skills_dir / "system_skill"
        sd.mkdir(parents=True)
        (sd / "skill.md").write_text("""---
name: System
type: cognitive
inject: always
---
System-level guidance.""")
        registry = SkillRegistry(skills_dir)
        assert registry.skills["system_skill"]["type"] == "cognitive"
        assert registry.skills["system_skill"]["inject"] == "always"
