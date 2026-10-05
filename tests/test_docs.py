"""The docs site generator (docs/gen_pages.py) and the committed index of examples.

The site is built from the repo's own files, so these tests check the generator's pure functions
and that what it emits hangs together — every page is in the nav, every internal link resolves —
without needing MkDocs installed. One more test builds the real site if MkDocs is available.
"""

import importlib.util
import os
import posixpath
import re
import subprocess
import sys
from pathlib import Path

import pytest

import examples_index
from example_manifest import REPO_ROOT, discover

spec = importlib.util.spec_from_file_location("gen_pages", REPO_ROOT / "docs" / "gen_pages.py")
gen_pages = importlib.util.module_from_spec(spec)
sys.modules["gen_pages"] = gen_pages
spec.loader.exec_module(gen_pages)


# --- Markdown plumbing ---------------------------------------------------------------------


def test_sections_split_on_h2_and_ignore_hashes_inside_code_fences():
    text = "# Title\n\nintro\n\n## One\n\n```bash\n## not a heading\n```\n\n## Two\n\nbody"
    preamble, sections = gen_pages.split_sections(text)
    assert preamble == "# Title\n\nintro"
    assert list(sections) == ["One", "Two"]
    assert "## not a heading" in sections["One"]


def test_headings_shift_but_code_fences_do_not():
    text = "## A\n\n### B\n\n```\n### code\n```"
    assert gen_pages.shift_headings(text, 1) == "### A\n\n#### B\n\n```\n### code\n```"
    assert gen_pages.shift_headings("### B", -2, minimum=2) == "## B"  # never above the minimum


def test_a_missing_readme_section_fails_loudly_and_says_what_exists():
    with pytest.raises(gen_pages.SectionNotFound, match="has no '## Gone' section"):
        gen_pages.section({"Here": "x"}, "Gone")


def test_the_pages_the_site_expects_really_exist_in_the_readme():
    _, sections = gen_pages.split_sections((REPO_ROOT / "README.md").read_text())
    for group in gen_pages.README_PAGES:
        for title in group.sections:
            assert title in sections, f"README.md lost its '## {title}' section"
    assert "Stack" in sections


# --- Lists ---------------------------------------------------------------------------------


def test_a_list_straight_after_a_paragraph_line_gets_a_blank_line_first():
    """GitHub renders this as a list; MkDocs would run the items into one paragraph."""
    text = "**What it shows**\n- one\n- two\n\nAfter."
    assert gen_pages.blank_line_before_lists(text) == "**What it shows**\n\n- one\n- two\n\nAfter."


def test_numbered_lists_are_handled_too():
    assert gen_pages.blank_line_before_lists("Steps:\n1. a\n2. b") == "Steps:\n\n1. a\n2. b"


@pytest.mark.parametrize(
    "text",
    [
        "- one\n- two",  # items following items
        "Intro\n\n- one\n- two",  # already preceded by a blank line
        "- one\n  continued\n  - nested\n- two",  # indented continuation and nesting
        "```bash\nstep\n- not a list in code\n```",  # code fences are not touched
        "text\n    - indented code, not a list start",
    ],
)
def test_text_that_is_already_fine_is_left_unchanged(text):
    assert gen_pages.blank_line_before_lists(text) == text


def test_every_generated_page_has_a_blank_line_before_each_list(site):
    """The bug this guards against was visible in the browser, not in the build."""
    for page, text in site.items():
        assert gen_pages.blank_line_before_lists(text) == text, (
            f"{page} has a list with no blank line before it"
        )


# --- Links ---------------------------------------------------------------------------------

PAGES = {
    "README.md": "index.md",
    "examples": "patterns/index.md",
    "examples/router": "patterns/router.md",
}


def links(text: str, source: str = "README.md", page: str = "guides/agents.md") -> str:
    return gen_pages.rewrite_links(text, source, page, PAGES)


def test_a_link_to_a_page_the_site_holds_becomes_a_relative_page_link():
    assert links("[x](examples/)") == "[x](../patterns/index.md)"
    assert links("[r](examples/router/#top)", page="patterns/index.md") == "[r](router.md#top)"


def test_a_link_to_the_current_page_stays_on_it():
    on_router = {"source": "examples/pipeline/README.md", "page": "patterns/router.md"}
    assert links("[r](../router/)", **on_router) == "[r](#)"  # the page's top, not an empty href
    assert links("[r](../router/#x)", **on_router) == "[r](#x)"


def test_other_repo_files_link_to_github_and_folders_to_tree():
    assert links("[l](LICENSE)").startswith(
        "[l](https://github.com/tmtabor/agent-template/blob/main/LICENSE"
    )
    assert "/tree/main/agent" in links("[a](agent/)")


def test_external_links_anchors_and_code_fences_are_left_alone():
    assert links("[w](https://example.com)") == "[w](https://example.com)"
    assert links("[a](#here)") == "[a](#here)"
    fenced = "```\n[x](examples/)\n```"
    assert links(fenced) == fenced


def test_a_link_to_nothing_is_left_as_it_was():
    assert links("[n](no/such/file.md)") == "[n](no/such/file.md)"


# --- The generated site --------------------------------------------------------------------


@pytest.fixture(scope="module")
def site() -> dict[str, str]:
    return gen_pages.generate_site()


def flatten(nav) -> list[str]:
    out = []
    for item in nav:
        for value in item.values():
            out += flatten(value) if isinstance(value, list) else [value]
    return out


def test_every_example_gets_a_page_and_a_nav_entry(site):
    nav_paths = flatten(gen_pages.nav(discover()))
    for example in discover():
        assert f"patterns/{example.name}.md" in site
        assert f"patterns/{example.name}.md" in nav_paths


def test_every_page_is_in_the_nav_and_every_nav_entry_is_a_page(site):
    nav_paths = flatten(gen_pages.nav(discover()))
    assert sorted(nav_paths) == sorted(site)
    assert len(nav_paths) == len(set(nav_paths))


def test_every_internal_link_in_the_site_resolves_to_a_page(site):
    link = re.compile(r"(?<!!)\[[^\]]+\]\(([^)\s]+)\)")
    for page, text in site.items():
        in_code = False
        for line in text.splitlines():
            if line.lstrip().startswith(("```", "~~~")):
                in_code = not in_code
            if in_code:
                continue
            for target in link.findall(line):
                if re.match(r"^([a-z][a-z0-9+.-]*:|#)", target, re.IGNORECASE):
                    continue
                path = target.partition("#")[0]
                resolved = posixpath.normpath(posixpath.join(posixpath.dirname(page), path))
                assert resolved in site, f"{page} links to {target!r}, which is not a page"


def test_an_example_page_has_its_readme_recorded_run_and_source(site):
    page = site["patterns/router.md"]
    assert page.startswith("# Router\n")
    assert "## Recorded run" in page and "#### 1. `router.classifier`" in page
    assert '=== "agent.py"' in page and '=== "example.toml"' in page
    assert "[`sample_run.md`](#recorded-run)" in page  # the README's link now stays on the page


def test_an_examples_prompt_files_get_their_own_tabs(site):
    assert '=== "prompts/evaluator_optimizer_critic.txt"' in site["patterns/evaluator_optimizer.md"]


def test_code_containing_backtick_fences_gets_a_longer_fence():
    out = gen_pages.code_tabs([("x.md", "markdown", "```python\nprint(1)\n```")])
    assert "````markdown" in out


def test_the_home_page_does_not_link_to_itself_as_the_documentation(site):
    assert gen_pages.DOCS_LINK in (REPO_ROOT / "README.md").read_text()  # so the strip is real
    assert "Read the documentation" not in site["index.md"]
    assert "Browse the example patterns" in site["index.md"]


def test_the_nav_follows_the_display_order():
    titles = [list(item.values())[0] for item in gen_pages.nav(discover()) if "Patterns" in item][0]
    assert [list(t)[0] for t in titles][:3] == ["Overview", "Blank", "Single agent"]


# --- Configuration and the committed examples index ----------------------------------------


def test_mkdocs_yml_agrees_with_the_urls_the_scripts_use():
    config = (REPO_ROOT / "mkdocs.yml").read_text()
    assert f"repo_url: {gen_pages.REPO_URL}" in config
    assert f"site_url: {examples_index.DOCS_URL}" in config


def test_the_examples_index_is_current():
    """Regenerate with: uv run python scripts/examples_index.py"""
    assert examples_index.INDEX_PATH.read_text() == examples_index.render(discover())


def test_the_examples_index_lists_every_example_in_display_order():
    text = examples_index.render(discover())
    names = re.findall(r"^\| \[`(\w+)`\]", text, re.MULTILINE)
    assert names == [e.name for e in gen_pages.display_order(discover())]


def test_the_real_site_builds_without_warnings(tmp_path: Path):
    pytest.importorskip("mkdocs")
    pytest.importorskip("material")
    pytest.importorskip("mkdocs_gen_files")
    result = subprocess.run(
        [sys.executable, "-m", "mkdocs", "build", "--strict", "-d", str(tmp_path / "site")],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        env={**os.environ, "DISABLE_MKDOCS_2_WARNING": "true"},
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert (tmp_path / "site" / "patterns" / "router" / "index.html").exists()
