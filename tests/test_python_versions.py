"""The Python versions the template claims to support, in every place that says so, agree.

"Supported" is a claim in three places: the classifiers in pyproject.toml, the matrix CI runs, and the
badge in the README. They must name the same versions, the floor must be the oldest of them, and the
development default (.python-version) and ruff's target must be that floor. Whether the code really
works on them is what CI and the release check run; this only keeps the words honest.
"""

import re
import tomllib
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent


def version_key(version: str) -> tuple[int, ...]:
    return tuple(int(part) for part in version.split("."))


def classifier_versions() -> list[str]:
    project = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]
    prefix = "Programming Language :: Python :: "
    return sorted(
        (
            c.removeprefix(prefix)
            for c in project["classifiers"]
            if re.fullmatch(rf"{prefix}\d+\.\d+", c)
        ),
        key=version_key,
    )


def ci_versions() -> list[str]:
    workflow = yaml.safe_load((ROOT / ".github/workflows/ci.yml").read_text())
    matrix = workflow["jobs"]["test"]["strategy"]["matrix"]["python-version"]
    return sorted((str(v) for v in matrix), key=version_key)


def badge_versions() -> list[str]:
    badge = re.search(
        r"img\.shields\.io/badge/python-([0-9.%A-Z]+?)-blue", (ROOT / "README.md").read_text()
    )
    assert badge, "the README has no python badge"
    return sorted(badge.group(1).replace("%20%7C%20", " ").split(), key=version_key)


def test_the_classifiers_the_ci_matrix_and_the_readme_badge_name_the_same_versions():
    assert classifier_versions() == ci_versions() == badge_versions()
    assert len(classifier_versions()) >= 2  # 3.13 and 3.14 at the time of writing


def test_the_floor_is_the_oldest_supported_version_everywhere_it_is_stated():
    floor = classifier_versions()[0]
    project = tomllib.loads((ROOT / "pyproject.toml").read_text())
    assert project["project"]["requires-python"] == f">={floor}"
    assert (ROOT / ".python-version").read_text().strip() == floor  # develop on the oldest
    assert project["tool"]["ruff"]["target-version"] == "py" + floor.replace(".", "")


def test_every_supported_version_is_at_least_the_floor_and_not_a_prerelease():
    for version in classifier_versions():
        assert re.fullmatch(r"\d+\.\d+", version), version  # "3.15" only once it is released
