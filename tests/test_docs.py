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
    for title in gen_pages.HOME_SECTIONS:
        assert title in sections, f"README.md lost its '## {title}' section"


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


def test_an_example_page_has_its_readme_source_and_a_collapsed_recorded_run_after_it(site):
    page = site["patterns/router.md"]
    assert page.startswith("# Router\n")
    assert '=== "agent.py"' in page and '=== "example.toml"' in page
    assert "[`sample_run.md`](#recorded-run)" in page  # the README's link stays on the page
    # The recording is a closed block (`???`, not `???+`) below the source, with its own anchor.
    assert "## Recorded run" not in page and "\n???+ recordedrun" not in page
    anchor, block = page.index("[](){ #recorded-run }"), page.index("??? recordedrun")
    assert (
        page.index("## Source") < page.index('=== "agent.py"') < anchor < block
    )  # below the source
    assert block - anchor < 50  # the anchor is right before the block, for extra.js to find it
    # Its content is still there, its headings are labels (so the table of contents stays short).
    assert "**1. `router.classifier`**" in page and "\n#### " not in page.split("recordedrun")[1]


def test_the_recorded_runs_title_carries_the_models_steps_and_cost():
    text = (
        "# Sample run: X\n\n*Recorded 2026-10-06 with `google:gemini-3.1-flash-lite` · 6 steps · "
        "5,307 tokens · $0.0021 · 4.9 s.*\n\n## Input\n\n> hi\n\n### 1. `x`\n\ntext\n"
    )
    block = gen_pages.recorded_run_block(text)
    assert '??? recordedrun "Recorded run · gemini-3.1-flash-lite · 6 steps · $0.0021"' in block
    one = gen_pages.recorded_run_block(text.replace("6 steps", "1 steps"))
    assert "· 1 step ·" in one  # singular
    assert "\n    **Input**" in block and "\n    **1. `x`**" in block  # headings became labels
    assert "# Sample run" not in block  # its own title is the block's


def test_a_recording_whose_header_is_not_recognised_still_gets_a_plain_title():
    block = gen_pages.recorded_run_block("# T\n\nno header here\n")
    assert '??? recordedrun "Recorded run"' in block


def test_an_example_that_runs_as_a_service_shows_the_service_files(site):
    page = site["patterns/mcp_tools.md"]
    for label in ("service/server.py", "service/Dockerfile", "service/docker-compose.yml"):
        assert f'=== "{label}"' in page
    assert "```dockerfile" in page and "```yaml" in page
    assert '=== "service/' not in site["patterns/router.md"]  # only examples that have one


def test_an_examples_prompt_files_get_their_own_tabs(site):
    assert '=== "prompts/evaluator_optimizer_critic.txt"' in site["patterns/evaluator_optimizer.md"]


def test_an_example_without_a_recording_still_builds_and_drops_the_dead_link(tmp_path, monkeypatch):
    """A new example has no sample_run.md until the release gate records it; the site must still build."""
    import dataclasses
    import shutil

    shutil.copytree(REPO_ROOT / "examples" / "router", tmp_path / "examples" / "router")
    (tmp_path / "examples" / "router" / "sample_run.md").unlink()
    monkeypatch.setattr(gen_pages, "REPO_ROOT", tmp_path)
    example = dataclasses.replace(
        next(e for e in discover() if e.name == "router"), path=tmp_path / "examples" / "router"
    )

    page = gen_pages.example_page(example, gen_pages.page_map([example]))
    assert "recordedrun" not in page and "See it run" not in page and "#recorded-run" not in page
    assert page.startswith("# Router\n") and '=== "agent.py"' in page  # everything else is there


def test_code_containing_backtick_fences_gets_a_longer_fence():
    out = gen_pages.code_tabs([("x.md", "markdown", "```python\nprint(1)\n```")])
    assert "````markdown" in out


def test_the_home_page_does_not_link_to_itself_as_the_documentation(site):
    readme = (REPO_ROOT / "README.md").read_text()
    assert f'<a href="{gen_pages.SITE_URL}">Documentation</a>' in readme  # so the strip is real
    assert ">Documentation</a>" not in site["index.md"]
    assert f'href="{gen_pages.SITE_URL}"' not in site["index.md"]
    assert 'href="patterns/"' in site["index.md"]  # the other links in the row stay
    # The coverage badge's link goes to the page that explains it, as a URL MkDocs serves.
    assert 'href="reference/maintaining/#the-release-check"' in site["index.md"]


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


# --- The home page: tabs, the header, and links ----------------------------------------------


def test_the_use_cases_become_one_tab_each_and_keep_their_code_fences():
    body = "Intro.\n\n### One\n\ntext\n\n```bash\n# not a heading\nrun\n```\n\n### Two\n\nmore"
    tabbed = gen_pages.tabs_from_subsections(body)
    assert tabbed.startswith('Intro.\n\n=== "One"\n\n    text')
    assert '=== "Two"\n\n    more' in tabbed
    assert "    ```bash\n    # not a heading\n    run\n    ```" in tabbed  # nested, not split


def test_every_use_case_in_the_readme_is_on_the_home_page_in_the_chosen_layout(site):
    _, sections = gen_pages.split_sections((REPO_ROOT / "README.md").read_text())
    titles = re.findall(r"^### (.+)$", sections[gen_pages.TABBED_SECTION], re.MULTILINE)
    assert len(titles) >= 6
    marker = {"tabs": '=== "{}"', "collapsible": '??? usecase "{}"'}[gen_pages.USE_CASE_LAYOUT]
    for title in titles:
        # (the first collapsible block is written `???+`, open)
        assert marker.format(title) in site["index.md"].replace("???+", "???")


def test_the_use_cases_can_be_collapsible_blocks_with_the_first_open_and_fences_intact():
    body = "Intro.\n\n### One\n\ntext\n\n```bash\n# not a heading\nrun\n```\n\n### Two\n\nmore"
    out = gen_pages.collapsibles_from_subsections(body)
    assert out.startswith('Intro.\n\n???+ usecase "One"\n\n    text')
    assert '\n\n??? usecase "Two"\n\n    more' in out  # closed
    assert "    ```bash\n    # not a heading\n    run\n    ```" in out
    assert gen_pages.collapsibles_from_subsections(body, open_first=False).count("???+") == 0


def test_the_logo_switches_with_the_sites_colour_scheme_instead_of_the_systems():
    hero = (
        '<a href="https://tmtabor.io/agent-template/">\n<picture>\n'
        '<source media="(prefers-color-scheme: dark)" srcset="assets/logo-dark.svg">\n'
        '<img src="assets/logo-light.svg" alt="x" height="64">\n</picture>\n</a>'
    )
    out = gen_pages.hero_for_site(hero)
    assert "<picture>" not in out and "<a " not in out
    assert 'src="assets/logo-light.svg#only-light"' in out
    assert 'src="assets/logo-dark.svg#only-dark"' in out


def test_raw_html_links_get_the_directory_urls_mkdocs_serves():
    text = '<a href="patterns/index.md">a</a> <a href="faq.md">b</a> <a href="guides/x.md#top">c</a> <a href="https://e.com/a.md">d</a>'
    out = gen_pages.directory_urls_in_html(text)
    assert 'href="patterns/"' in out and 'href="faq/"' in out and 'href="guides/x/#top"' in out
    assert 'href="https://e.com/a.md"' in out  # an external link is not ours to change


def test_html_attributes_are_rewritten_like_markdown_links():
    pages = {"examples": "patterns/index.md", "docs/assets/logo-dark.svg": "assets/logo-dark.svg"}
    text = '<a href="examples/">p</a> <img src="docs/assets/logo-dark.svg"> <a href="https://x.y/">z</a>'
    out = gen_pages.rewrite_links(text, "README.md", "index.md", pages)
    assert 'href="patterns/index.md"' in out and 'src="assets/logo-dark.svg"' in out
    assert 'href="https://x.y/"' in out


def test_a_link_to_a_readme_section_lands_on_the_page_that_holds_it():
    pages = gen_pages.page_map(discover())
    rewrite = lambda text, page: gen_pages.rewrite_links(text, "docs/pages/faq.md", page, pages)  # noqa: E731
    assert rewrite("[x](../../README.md#usage-limits)", "faq.md") == "[x](guides/usage-limits.md)"
    assert rewrite("[x](../../README.md#configuration)", "faq.md") == "[x](configuration.md)"
    assert rewrite("[x](../../README.md#get-started)", "faq.md") == "[x](index.md#get-started)"
    # A section that shares a page with another keeps its own anchor.
    assert rewrite("[x](../../README.md#adding-tools)", "faq.md") == (
        "[x](guides/tools-and-prompts.md#adding-tools)"
    )


def test_the_guides_the_contributing_and_maintaining_pages_are_in_the_site_and_the_nav(site):
    for page in (
        "faq.md",
        "guides/choosing-a-pattern.md",
        "contributing.md",
        "reference/maintaining.md",
    ):
        assert page in site and site[page].startswith("# ")
    flat = str(gen_pages.nav(discover()))
    for page in (
        "faq.md",
        "guides/choosing-a-pattern.md",
        "contributing.md",
        "reference/maintaining.md",
    ):
        assert page in flat


def test_the_site_url_is_the_one_the_site_is_served_at():
    assert gen_pages.SITE_URL == "https://tmtabor.io/agent-template/"
    assert examples_index.DOCS_URL.removesuffix("patterns/") == gen_pages.SITE_URL


# --- The docs workflow rebuilds the site when (and only when) a page's source changes ----------------


def test_the_docs_workflow_runs_when_any_file_the_site_is_built_from_changes():
    """A source missing from the workflow's `paths` means editing it never redeploys the site: the
    Maintaining page went stale that way when MAINTAINING.md was not in the list."""
    import fnmatch

    import yaml

    workflow = yaml.safe_load((REPO_ROOT / ".github/workflows/docs.yml").read_text())
    triggers = (
        workflow.get("on") or workflow[True]
    )  # YAML 1.1 reads a bare `on` as the boolean True
    paths = triggers["push"]["paths"]

    def watched(path: str) -> bool:
        return any(fnmatch.fnmatch(path, pattern) for pattern in paths)

    sources = [
        "README.md",
        "AGENTS.md",
        "CHANGELOG.md",
        *gen_pages.FILE_PAGES,
        *gen_pages.GUIDE_SOURCES,
    ]
    sources += [f"examples/{e.name}/README.md" for e in discover()]
    sources += ["mkdocs.yml", "docs/gen_pages.py", "scripts/example_manifest.py"]
    missing = [path for path in sources if not watched(path)]
    assert not missing, (
        f"docs.yml does not watch {missing}: editing them would not redeploy the site"
    )
