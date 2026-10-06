"""Builds the documentation site from the repository's own files.

Almost nothing here is written twice. The README, AGENTS.md, CHANGELOG.md, CONTRIBUTING.md,
MAINTAINING.md and each example (its README, recorded run, manifest and source) are the sources;
this script turns them into pages, so the docs cannot drift from the code. The exception is two
hand-written guides in docs/pages/ ("Which pattern should I use?" and the FAQ), which are written
with repo-relative links like everything else and published at the paths GUIDE_SOURCES gives them. It runs under `mkdocs-gen-files` (see mkdocs.yml), and its pure
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
HTML_LINK = re.compile(r'\b(href|src|srcset)="([^"]+)"')


SITE_URL = "https://tmtabor.io/agent-template/"  # keep in sync with mkdocs.yml (tested)


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


def slug(title: str) -> str:
    """The anchor a heading gets, on GitHub and in MkDocs: lower case, punctuation dropped."""
    words = re.sub(r"[^\w\s-]", "", title.lower()).split()
    return "-".join(words)


def tabs_from_subsections(body: str) -> str:
    """Turn a section's `###` subsections into Material content tabs.

    Text before the first `###` stays above the tabs. On GitHub the same text is ordinary headed
    sections; on the site each one is a tab. The tab content is indented four spaces, which is how
    Material nests Markdown (code fences included) inside a tab.
    """
    intro: list[str] = []
    tabs: list[tuple[str, list[str]]] = []
    for line, in_fence in outside_fences(body.splitlines()):
        heading = None if in_fence else HEADING.match(line)
        if heading and len(heading.group(1)) == 3:
            tabs.append((heading.group(2), []))
        elif tabs:
            tabs[-1][1].append(line)
        else:
            intro.append(line)
    out = ["\n".join(intro).strip()] if "".join(intro).strip() else []
    for title, lines in tabs:
        content = "\n".join(lines).strip()
        indented = "\n".join(f"    {line}" if line else "" for line in content.splitlines())
        out.append(f'=== "{title}"\n\n{indented}')
    return "\n\n".join(out)


def collapsibles_from_subsections(body: str, *, open_first: bool = True) -> str:
    """Turn a section's `###` subsections into collapsible blocks (`??? usecase "Title"`).

    The same text as `tabs_from_subsections`, laid out as a list of titles that open one at a time
    instead of a row of tabs that scrolls sideways. The first is open so the reader sees what is
    inside. Content is indented four spaces, as for tabs.
    """
    intro: list[str] = []
    blocks: list[tuple[str, list[str]]] = []
    for line, in_fence in outside_fences(body.splitlines()):
        heading = None if in_fence else HEADING.match(line)
        if heading and len(heading.group(1)) == 3:
            blocks.append((heading.group(2), []))
        elif blocks:
            blocks[-1][1].append(line)
        else:
            intro.append(line)
    out = ["\n".join(intro).strip()] if "".join(intro).strip() else []
    for index, (title, lines) in enumerate(blocks):
        content = "\n".join(lines).strip()
        indented = "\n".join(f"    {line}" if line else "" for line in content.splitlines())
        marker = "???+" if open_first and index == 0 else "???"
        out.append(f'{marker} usecase "{title}"\n\n{indented}')
    return "\n\n".join(out)


PICTURE = re.compile(r"<picture>.*?</picture>", re.DOTALL)


def hero_for_site(preamble: str) -> str:
    """The README's centred header, adapted to the site.

    GitHub picks the light or dark logo from the viewer's system setting with `<picture>`; the
    site has its own light/dark switch, which Material drives with `#only-light` / `#only-dark`
    on the image address. The links back to the site itself, which would point at the page the
    reader is already on, are dropped.
    """

    def both_logos(match: re.Match) -> str:
        light = re.search(r'<img src="([^"]+)"', match.group(0))
        dark = re.search(r'srcset="([^"]+)"', match.group(0))
        height = re.search(r'height="(\d+)"', match.group(0))
        attrs = (
            f' alt="agent template" height="{height.group(1)}"'
            if height
            else ' alt="agent template"'
        )
        return (
            f'<img src="{light.group(1)}#only-light"{attrs}>'
            f'<img src="{dark.group(1)}#only-dark"{attrs}>'
        )

    text = PICTURE.sub(both_logos, preamble)
    # The anchor wrapped around the logo, then the "Documentation" link in the row below it.
    url = re.escape(SITE_URL)
    text = re.sub(rf'<a href="{url}">\s*(<img)', r"\1", text)
    text = re.sub(r'(<img[^>]*#only-dark"[^>]*>)\s*</a>', r"\1", text)
    text = re.sub(rf'<a href="{url}">Documentation</a>\s*·\s*', "", text)
    return text


def directory_urls_in_html(text: str) -> str:
    """Point raw-HTML links at the pages MkDocs serves.

    MkDocs rewrites Markdown links to `page.md` for you but leaves an `<a href>` in raw HTML alone,
    and it serves `patterns/index.md` at `patterns/` and `faq.md` at `faq/`.
    """

    def fix(match: re.Match) -> str:
        path, anchor = match.group(1), match.group(2) or ""
        path = (
            path.removesuffix("index.md")
            if path.endswith("index.md")
            else path.removesuffix(".md") + "/"
        )
        return f'href="{path}{anchor}"'

    return re.sub(r'href="([^":#]+\.md)(#[^"]*)?"', fix, text)


RECORDED = re.compile(
    r"\*Recorded \S+ with `([^`]+)` · (\d+) steps? · [\d,]+ tokens · (\$[\d.]+|cost unknown)"
)


def recorded_run_block(transcript: str) -> str:
    """A recording as a closed, collapsible block below the source, titled with its key facts.

    The reader who only wants to know that it was run sees "gemini-3.1-flash-lite · 6 steps · $0.0021"
    and moves on; the one who wants the prompts and tool calls opens it. Its headings become bold
    labels so they stay out of the page's table of contents, and `#recorded-run` is an anchor just
    before the block (extra.js opens the block when a link points there).
    """
    body = drop_title(transcript)
    found = RECORDED.search(body)
    title = "Recorded run"
    if found:
        model, steps, cost = found.groups()
        model = model.split(":", 1)[-1]
        title += f" · {model} · {steps} step{'' if steps == '1' else 's'} · {cost}"
    lines = []
    for line, in_fence in outside_fences(body.splitlines()):
        heading = None if in_fence else HEADING.match(line)
        lines.append(f"**{heading.group(2)}**" if heading else line)
    indented = "\n".join(f"    {line}" if line else "" for line in "\n".join(lines).splitlines())
    return f'[](){{ #recorded-run }}\n\n??? recordedrun "{title}"\n\n{indented}'


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

    def resolve(target: str) -> str | None:
        """The rewritten target, or None to leave the link as it was."""
        if re.match(r"^([a-z][a-z0-9+.-]*:|#|/)", target, re.IGNORECASE):
            return None
        path, _, fragment = target.partition("#")
        resolved = posixpath.normpath(posixpath.join(posixpath.dirname(source), path))
        # A link to a README section lands on the page that now holds that section.
        section_page = pages.get(f"{resolved}#{fragment}") if fragment else None
        mapped = section_page or pages.get(resolved) or pages.get(resolved + "/")
        if mapped:
            mapped_page, _, mapped_fragment = mapped.partition("#")
            anchor = mapped_fragment if section_page else (mapped_fragment or fragment)
            if mapped_page == page:
                return f"#{anchor}" if anchor else "#"  # this very page: its top
            url = posixpath.relpath(mapped_page, posixpath.dirname(page) or ".")
            return url + (f"#{anchor}" if anchor else "")
        if (REPO_ROOT / resolved).exists():
            return repo_link(resolved)
        return None

    def fix(match: re.Match) -> str:
        label, target, title = match.groups()
        url = resolve(target)
        return match.group(0) if url is None else f"[{label}]({url}{title})"

    def fix_html(match: re.Match) -> str:
        attribute, target = match.groups()
        url = resolve(target)
        return match.group(0) if url is None else f'{attribute}="{url}"'

    out = []
    for line, in_fence in outside_fences(blank_line_before_lists(markdown).splitlines()):
        out.append(line if in_fence else HTML_LINK.sub(fix_html, LINK.sub(fix, line)))
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
    """The pattern page for one example: its README, its source, and a collapsed recorded run."""
    page = f"patterns/{example.name}.md"
    directory = f"examples/{example.name}"
    readme_text = drop_title(read(f"{directory}/README.md"))
    if not (example.path / "sample_run.md").exists():
        # Nothing to link to yet: a new example is recorded by scripts/release_check.py --record,
        # and the site must build in the meantime (a link to a missing anchor fails --strict).
        readme_text = SEE_IT_RUN.sub("", readme_text)
    readme = rewrite_links(readme_text, f"{directory}/README.md", page, pages)

    parts = [f"# {example.title}", "", readme, ""]

    tabs = [("agent.py", "python", read(f"{directory}/agent.py"))]
    for prompt in example.prompt_files:
        tabs.append((f"prompts/{prompt.name}", "text", prompt.read_text(encoding="utf-8")))
    tabs.append(("example.toml", "toml", read(f"{directory}/example.toml")))
    for name in ("test_example.py", "test_live.py"):
        if (example.path / name).exists():
            tabs.append((name, "python", read(f"{directory}/{name}")))
    # An example that runs as a service ships the service too: the server, its image, its compose file.
    if example.service_dir.is_dir():
        for path in sorted(example.service_dir.iterdir()):
            if path.is_file():
                language = {".py": "python", ".yml": "yaml"}.get(path.suffix, "dockerfile")
                tabs.append((f"service/{path.name}", language, path.read_text(encoding="utf-8")))
    parts += [
        "## Source",
        "",
        f"All of it is in [`{directory}/`]({repo_link(directory)}).",
        "",
        code_tabs(tabs),
        "",
    ]
    transcript = example.path / "sample_run.md"
    if transcript.exists():
        parts += [recorded_run_block(read(f"{directory}/sample_run.md")), ""]
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
    Group("getting-started.md", "Getting started", ("Setup and commands", "Project structure")),
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
)

# The README sections that make up the home page, in order. "What are you building?" becomes tabs.
HOME_SECTIONS = (
    "Get started",
    "What are you building?",
    "Why this template",
    "Stack",
    "Next steps",
    "Projects using agent-template",
)
TABBED_SECTION = "What are you building?"
# How its subsections are laid out on the home page: "tabs" or "collapsible".
USE_CASE_LAYOUT = "collapsible"

# Hand-written pages (the only ones): repo path -> site path, and the title the page and nav show.
GUIDE_SOURCES = {
    "docs/pages/choosing-a-pattern.md": (
        "guides/choosing-a-pattern.md",
        "Which pattern should I use?",
    ),
    "docs/pages/faq.md": ("faq.md", "FAQ"),
}
# Whole files that become a page each.
FILE_PAGES = {
    "CONTRIBUTING.md": ("contributing.md", "Contributing"),
    "MAINTAINING.md": ("reference/maintaining.md", "Maintaining"),
}
ASSETS = ("logo-light.svg", "logo-dark.svg", "logo-header.svg", "favicon.svg")

TOP_PAGES = ("getting-started.md", "configuration.md")
GUIDES = (
    "guides/choosing-a-pattern.md",
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
    pages["examples/README.md"] = "patterns/index.md"
    for source, (page, _) in {**GUIDE_SOURCES, **FILE_PAGES}.items():
        pages[source] = page
    for name in ASSETS:
        pages[f"docs/assets/{name}"] = f"assets/{name}"
    # A link to a README section (`README.md#usage-limits`) goes to the page that holds it.
    for group in README_PAGES:
        for title in group.sections:
            anchor = f"#{slug(title)}" if len(group.sections) > 1 else ""
            pages[f"README.md#{slug(title)}"] = group.path + anchor
    for title in HOME_SECTIONS:
        pages[f"README.md#{slug(title)}"] = f"index.md#{slug(title)}"
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

    # Home: the README's header and pitch, then its sales sections; the use cases become tabs.
    home_parts = [directory_urls_in_html(fix(hero_for_site(preamble), "index.md"))]
    for title in HOME_SECTIONS:
        body = section(sections, title)
        if title == TABBED_SECTION:
            layout = (
                tabs_from_subsections
                if USE_CASE_LAYOUT == "tabs"
                else collapsibles_from_subsections
            )
            body = layout(body)
        home_parts.append(f"## {title}\n\n" + fix(body, "index.md"))
    site["index.md"] = "\n\n".join(home_parts) + "\n"

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
    for source, (page, title) in {**FILE_PAGES, **GUIDE_SOURCES}.items():
        site[page] = f"# {title}\n\n" + fix(drop_title(read(source)), page, source) + "\n"

    # Whatever path a page took (links rewritten, headings shifted, a transcript pasted in), no
    # list may start without a blank line before it. Idempotent, so already-fixed text is safe.
    return {path: blank_line_before_lists(text) for path, text in site.items()}


def nav(examples: list[Example]) -> list:
    """The site navigation, in MkDocs' nav format, built from the examples that exist."""
    examples = display_order(examples)
    titles = {g.path: g.title for g in README_PAGES}
    titles.update({page: title for page, title in GUIDE_SOURCES.values()})
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
        {"FAQ": "faq.md"},
        {
            "Reference": [
                {"Design notes": "reference/design-notes.md"},
                {"Contributing": "contributing.md"},
                {"Maintaining": "reference/maintaining.md"},
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
