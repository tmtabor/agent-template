"""Builds the documentation site from the repository's own files.

Nothing here is written twice. The README, AGENTS.md, CHANGELOG.md and each example (its README,
recorded run, manifest and source) are the sources; this script turns them into pages, so the docs
cannot drift from the code. It runs under `mkdocs-gen-files` (see mkdocs.yml), and its pure
functions are tested in tests/test_docs.py without MkDocs installed.

    uv run --group docs mkdocs serve          # preview at http://127.0.0.1:8000
    uv run --group docs mkdocs build --strict # what the Pages workflow runs
"""

from __future__ import annotations

import posixpath
import re
import sys
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from example_manifest import Example, discover, display_order  # noqa: E402

REPO_URL = "https://github.com/tmtabor/agent-template"  # keep in sync with mkdocs.yml (tested)
BRANCH = "main"

FENCE = re.compile(r"^\s*(`{3,}|~{3,})")
HEADING = re.compile(r"^(#{1,6})\s+(.*\S)\s*$")
LINK = re.compile(r"(?<!!)\[([^\]]+)\]\(([^)\s]+)((?:\s+\"[^\"]*\")?)\)")


DOCS_LINK = "**[Read the documentation](https://tmtabor.github.io/agent-template/)** · "


class SectionNotFound(KeyError):
    """A README section the site expects is missing — it was renamed or removed."""


# --- Markdown plumbing ------------------------------------------------------------------------


def outside_fences(lines: list[str]):
    """Yield (line, in_fence) for each line, tracking ``` and ~~~ fenced code blocks."""
    fence: str | None = None
    for line in lines:
        match = FENCE.match(line)
        if fence is None:
            if match:
                fence = match.group(1)[0] * 3
                yield line, True
                continue
            yield line, False
        else:
            yield line, True
            if match and match.group(1).startswith(fence):
                fence = None


def split_sections(markdown: str) -> tuple[str, dict[str, str]]:
    """Split on H2 headings (ignoring `#` inside code fences) into (preamble, {title: body})."""
    preamble: list[str] = []
    sections: dict[str, list[str]] = {}
    current: list[str] = preamble
    for line, in_fence in outside_fences(markdown.splitlines()):
        heading = None if in_fence else HEADING.match(line)
        if heading and len(heading.group(1)) == 2:
            current = sections.setdefault(heading.group(2), [])
        else:
            current.append(line)
    return "\n".join(preamble).strip(), {k: "\n".join(v).strip() for k, v in sections.items()}


def shift_headings(markdown: str, delta: int, *, minimum: int = 1) -> str:
    """Move every heading (outside code fences) `delta` levels, never above `minimum`."""
    out = []
    for line, in_fence in outside_fences(markdown.splitlines()):
        heading = None if in_fence else HEADING.match(line)
        if heading:
            level = min(6, max(minimum, len(heading.group(1)) + delta))
            line = f"{'#' * level} {heading.group(2)}"
        out.append(line)
    return "\n".join(out)


def drop_title(markdown: str) -> str:
    """Remove the leading `# Title` line (the page supplies its own)."""
    lines = markdown.strip().splitlines()
    if lines and lines[0].startswith("# "):
        lines = lines[1:]
    return "\n".join(lines).strip()


def section(sections: dict[str, str], title: str) -> str:
    try:
        return sections[title]
    except KeyError:
        raise SectionNotFound(
            f"README.md has no '## {title}' section (it has {sorted(sections)}); "
            "update docs/gen_pages.py to match"
        ) from None


SEE_IT_RUN = re.compile(r"^\*\*See it run:\*\*[^\n]*\n+", re.MULTILINE)
LIST_ITEM = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+\S")


def blank_line_before_lists(markdown: str) -> str:
    """Put a blank line before a list that starts straight after a paragraph line.

    GitHub renders `**What it shows**` followed directly by `- item` as a list; MkDocs's
    Markdown parser needs a blank line first, and otherwise runs the items into one paragraph.
    Lists already preceded by a blank line, list items following list items (or their indented
    continuation lines), and anything in a code fence are left alone.
    """
    out: list[str] = []
    for line, in_fence in outside_fences(markdown.splitlines()):
        if not in_fence and out and LIST_ITEM.match(line):
            previous = out[-1]
            # An item indented four or more spaces is a lazy continuation of the paragraph above,
            # not a new list; a blank line there would turn it into a code block.
            shallow = len(line) - len(line.lstrip()) < 4
            starts_list = (
                shallow
                and previous.strip()
                and not LIST_ITEM.match(previous)
                and not previous[:1].isspace()
                and not FENCE.match(previous)
            )
            if starts_list:
                out.append("")
        out.append(line)
    return "\n".join(out) + ("\n" if markdown.endswith("\n") else "")


# --- Links ------------------------------------------------------------------------------------


def repo_link(path: str) -> str:
    """A GitHub URL for a repo-relative path (a folder if it is one)."""
    kind = "tree" if (REPO_ROOT / path).is_dir() else "blob"
    return f"{REPO_URL}/{kind}/{BRANCH}/{path.rstrip('/')}"


def rewrite_links(markdown: str, source: str, page: str, pages: dict[str, str]) -> str:
    """Make `source`'s relative links work on `page`.

    `source` is the repo-relative path the text came from; `pages` maps repo paths to the site
    page that now holds them (a value may end in `#anchor`). A link to a mapped path becomes a
    relative page link; any other link into the repo becomes a GitHub URL; external links,
    anchors and links to nothing are left alone.
    """

    def fix(match: re.Match) -> str:
        label, target, title = match.groups()
        if re.match(r"^([a-z][a-z0-9+.-]*:|#|/)", target, re.IGNORECASE):
            return match.group(0)
        path, _, fragment = target.partition("#")
        resolved = posixpath.normpath(posixpath.join(posixpath.dirname(source), path))
        mapped = pages.get(resolved) or pages.get(resolved + "/")
        if mapped:
            mapped_page, _, mapped_fragment = mapped.partition("#")
            anchor = mapped_fragment or fragment
            if mapped_page == page:
                url = f"#{anchor}" if anchor else "#"  # this very page: its top
            else:
                url = posixpath.relpath(mapped_page, posixpath.dirname(page) or ".")
                url += f"#{anchor}" if anchor else ""
            return f"[{label}]({url}{title})"
        if (REPO_ROOT / resolved).exists():
            return f"[{label}]({repo_link(resolved)}{title})"
        return match.group(0)

    out = []
    for line, in_fence in outside_fences(blank_line_before_lists(markdown).splitlines()):
        out.append(line if in_fence else LINK.sub(fix, line))
    return "\n".join(out)


# --- Pages ------------------------------------------------------------------------------------


def read(path: str) -> str:
    return (REPO_ROOT / path).read_text(encoding="utf-8")


def code_tabs(tabs: list[tuple[str, str, str]]) -> str:
    """Material content tabs: (label, language, code) each as a `=== "label"` tab."""
    out = []
    for label, language, code in tabs:
        longest = max((len(m) for m in re.findall(r"`+", code)), default=0)
        fence = "`" * max(3, longest + 1)
        body = f"{fence}{language}\n{code.rstrip()}\n{fence}"
        indented = "\n".join(f"    {line}" if line else "" for line in body.splitlines())
        out.append(f'=== "{label}"\n\n{indented}\n')
    return "\n".join(out)


def example_page(example: Example, pages: dict[str, str]) -> str:
    """The pattern page for one example: its README, a recorded run, and its source."""
    page = f"patterns/{example.name}.md"
    directory = f"examples/{example.name}"
    readme_text = drop_title(read(f"{directory}/README.md"))
    if not (example.path / "sample_run.md").exists():
        # Nothing to link to yet: a new example is recorded by scripts/release_check.py --record,
        # and the site must build in the meantime (a link to a missing anchor fails --strict).
        readme_text = SEE_IT_RUN.sub("", readme_text)
    readme = rewrite_links(readme_text, f"{directory}/README.md", page, pages)

    parts = [f"# {example.title}", "", readme, ""]

    transcript = example.path / "sample_run.md"
    if transcript.exists():
        # Its own title is the page's `## Recorded run`; its sections nest beneath it.
        parts += [
            "## Recorded run",
            "",
            shift_headings(drop_title(read(f"{directory}/sample_run.md")), 1, minimum=3),
            "",
        ]

    tabs = [("agent.py", "python", read(f"{directory}/agent.py"))]
    for prompt in example.prompt_files:
        tabs.append((f"prompts/{prompt.name}", "text", prompt.read_text(encoding="utf-8")))
    tabs.append(("example.toml", "toml", read(f"{directory}/example.toml")))
    for name in ("test_example.py", "test_live.py"):
        if (example.path / name).exists():
            tabs.append((name, "python", read(f"{directory}/{name}")))
    parts += [
        "## Source",
        "",
        f"All of it is in [`{directory}/`]({repo_link(directory)}).",
        "",
        code_tabs(tabs),
    ]
    return "\n".join(parts).rstrip() + "\n"


def patterns_index(examples: list[Example]) -> str:
    examples = display_order(examples)
    rows = [f"| [{e.title}]({e.name}.md) | {e.summary} |" for e in examples]
    return "\n".join(
        [
            "# Patterns",
            "",
            "Working example agents for common patterns, each with its source, tests and a recorded "
            "run against a real model. Run one in place, read it, or copy it into your project:",
            "",
            "```bash",
            "uv run python scripts/add_agent.py                      # pick one from a menu",
            "uv run python scripts/add_agent.py router --name support",
            "```",
            "",
            "| Pattern | What it shows |",
            "|---|---|",
            *rows,
            "",
            "Every one returns a [`RunResult`](../guides/agents.md): the output, the total usage, "
            "and one step per agent run.",
            "",
        ]
    )


@dataclass(frozen=True)
class Group:
    """A site page assembled from README sections."""

    path: str
    title: str
    sections: tuple[str, ...]


# README section -> page. A README H2 becomes the page title, and its H3s become H2s.
README_PAGES: tuple[Group, ...] = (
    Group("getting-started.md", "Getting started", ("Quickstart", "Project structure")),
    Group("configuration.md", "Configuration", ("Configuration",)),
    Group("guides/agents.md", "Agents", ("Agents",)),
    Group("guides/usage-limits.md", "Usage limits", ("Usage limits",)),
    Group(
        "guides/tools-and-prompts.md",
        "Tools and prompts",
        ("Adding tools", "Customizing the prompt"),
    ),
    Group("guides/observability.md", "Observability", ("Observability",)),
    Group("guides/evals.md", "Evals", ("Evals",)),
    Group("reference/releasing.md", "Releasing", ("Releasing the template (maintainers)",)),
    Group("reference/docs.md", "Maintaining the docs", ("Documentation site (maintainers)",)),
)

TOP_PAGES = ("getting-started.md", "configuration.md")
GUIDES = (
    "guides/agents.md",
    "guides/usage-limits.md",
    "guides/tools-and-prompts.md",
    "guides/observability.md",
    "guides/evals.md",
)


def page_map(examples: list[Example]) -> dict[str, str]:
    """Where each repo path that the docs cover now lives on the site."""
    pages = {"README.md": "index.md", "AGENTS.md": "reference/design-notes.md"}
    pages["CHANGELOG.md"] = "reference/changelog.md"
    pages["examples"] = "patterns/index.md"
    for example in examples:
        pages[f"examples/{example.name}"] = f"patterns/{example.name}.md"
        pages[f"examples/{example.name}/sample_run.md"] = f"patterns/{example.name}.md#recorded-run"
    return pages


def generate_site(examples: list[Example] | None = None) -> dict[str, str]:
    """Every generated page: {site path: markdown}."""
    examples = display_order(discover() if examples is None else examples)
    pages = page_map(examples)

    readme = read("README.md")
    preamble, sections = split_sections(readme)

    def fix(text: str, page: str, source: str = "README.md") -> str:
        return rewrite_links(text, source, page, pages)

    site: dict[str, str] = {}

    # Home: the README's opening, its Stack, and the patterns at a glance.
    glance = "\n".join(f"- [{e.title}](patterns/{e.name}.md) — {e.summary}" for e in examples)
    # The README's opening links to these docs; on the docs themselves that link goes nowhere.
    opening = preamble.replace(DOCS_LINK, "")
    site["index.md"] = (
        "\n\n".join(
            [
                fix(opening, "index.md"),
                "## Stack\n\n" + fix(section(sections, "Stack"), "index.md"),
                "## Where to start\n\n"
                "- [Getting started](getting-started.md): install, add an agent, run the tests\n"
                "- [Agents](guides/agents.md): the patterns, and what every `run_*` returns\n"
                "- [Configuration](configuration.md): the model, keys and limits\n",
                "## Patterns\n\n" + glance,
            ]
        )
        + "\n"
    )

    # The README's other sections, regrouped into pages.
    for group in README_PAGES:
        bodies = []
        for title in group.sections:
            body = section(sections, title)
            if len(group.sections) > 1:
                body = f"## {title}\n\n{body}"  # its H3s stay H3, beneath this H2
            else:
                body = shift_headings(body, -1, minimum=2)  # the section title is the page title
            bodies.append(fix(body, group.path))
        site[group.path] = f"# {group.title}\n\n" + "\n\n".join(bodies) + "\n"

    # Patterns.
    site["patterns/index.md"] = patterns_index(examples)
    for example in examples:
        site[f"patterns/{example.name}.md"] = example_page(example, pages)

    # Reference pages that are whole files.
    notes = fix(drop_title(read("AGENTS.md")), "reference/design-notes.md", "AGENTS.md")
    site["reference/design-notes.md"] = "# Design notes\n\n" + notes + "\n"
    changelog = fix(drop_title(read("CHANGELOG.md")), "reference/changelog.md", "CHANGELOG.md")
    site["reference/changelog.md"] = "# Changelog\n\n" + changelog + "\n"

    # Whatever path a page took (links rewritten, headings shifted, a transcript pasted in), no
    # list may start without a blank line before it. Idempotent, so already-fixed text is safe.
    return {path: blank_line_before_lists(text) for path, text in site.items()}


def nav(examples: list[Example]) -> list:
    """The site navigation, in MkDocs' nav format, built from the examples that exist."""
    examples = display_order(examples)
    titles = {g.path: g.title for g in README_PAGES}
    return [
        {"Home": "index.md"},
        *({titles[path]: path} for path in TOP_PAGES),
        {"Guides": [{titles[path]: path} for path in GUIDES]},
        {
            "Patterns": [
                {"Overview": "patterns/index.md"},
                *({e.title: f"patterns/{e.name}.md"} for e in examples),
            ]
        },
        {
            "Reference": [
                {"Design notes": "reference/design-notes.md"},
                {titles["reference/releasing.md"]: "reference/releasing.md"},
                {titles["reference/docs.md"]: "reference/docs.md"},
                {"Changelog": "reference/changelog.md"},
            ]
        },
    ]


def build() -> None:
    """Write every page into the MkDocs build (runs under mkdocs-gen-files)."""
    import mkdocs_gen_files

    examples = display_order(discover())
    for path, text in generate_site(examples).items():
        with mkdocs_gen_files.open(path, "w") as out:
            out.write(text)
    # The nav comes from the examples that exist, so a new example needs no edit to mkdocs.yml.
    # MkDocs builds its navigation after this script runs, so setting it here takes effect.
    mkdocs_gen_files.config["nav"] = nav(examples)


if __name__ in {"__main__", "<run_path>"}:  # how mkdocs-gen-files executes this script
    build()
