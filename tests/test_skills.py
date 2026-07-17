from redeye.skills import catalog_lines, load_skills


def test_builtin_skills_load():
    skills = load_skills(None)
    assert len(skills) >= 8
    for name in ("domain-recon", "email-osint", "username-osint", "report-writing", "opsec"):
        assert name in skills, name
        assert skills[name].body
        assert skills[name].description


def test_user_skill_overrides_builtin(tmp_path):
    (tmp_path / "domain-recon.md").write_text(
        "---\nname: domain-recon\ndescription: custom override\n---\n\nCustom body.\n"
    )
    skills = load_skills(tmp_path)
    assert skills["domain-recon"].origin == "user"
    assert "Custom body." in skills["domain-recon"].body


def test_malformed_skill_skipped(tmp_path):
    (tmp_path / "bad.md").write_text("no frontmatter here")
    skills = load_skills(tmp_path)
    assert "bad" not in skills


def test_catalog_lists_all():
    skills = load_skills(None)
    cat = catalog_lines(skills)
    for name in skills:
        assert name in cat
