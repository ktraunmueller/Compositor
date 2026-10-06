#!/usr/bin/env python3
"""Fetch GitHub release download counts and render a version bar chart."""

from __future__ import annotations

import argparse
import csv
import html
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


DEFAULT_REPOSITORY = "ktraunmueller/Compositor"
DEFAULT_SINCE_TAG = "0.9.0"
DEFAULT_CHART = "release-downloads.svg"
DEFAULT_CSV = "release-downloads.csv"
API_VERSION = "2022-11-28"
SERIES = (
    ("macOS DMG", "#0969da"),
    ("macOS ZIP (Sparkle)", "#8250df"),
    ("Windows x64 MSIX", "#1a7f37"),
    ("Windows ARM64 MSIX", "#bc4c00"),
)


def asset_series(name: str) -> str | None:
    name = name.lower()
    if name.endswith(".dmg"):
        return "macOS DMG"
    if name.endswith(".zip") and "macos" in name:
        return "macOS ZIP (Sparkle)"
    if name.endswith(".msix"):
        if "arm64" in name:
            return "Windows ARM64 MSIX"
        if "x64" in name or "amd64" in name:
            return "Windows x64 MSIX"
    return None


def series_counts(release: Release) -> dict[str, int | None]:
    counts: dict[str, int | None] = dict.fromkeys(label for label, _ in SERIES)
    for asset in release.assets:
        label = asset_series(asset.name)
        if label is not None:
            counts[label] = (counts[label] or 0) + asset.downloads
    return counts


@dataclass(frozen=True)
class Asset:
    name: str
    downloads: int
    url: str


@dataclass(frozen=True)
class Release:
    tag: str
    published_at: datetime
    assets: tuple[Asset, ...]

    @property
    def downloads(self) -> int:
        return sum(asset.downloads for asset in self.assets)


def parse_github_date(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def github_request(url: str, token: str | None) -> tuple[object, dict[str, str]]:
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": API_VERSION,
        "User-Agent": "compositor-release-downloads",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"

    request = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            body = json.load(response)
            response_headers = {key.lower(): value for key, value in response.headers.items()}
            return body, response_headers
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")
        try:
            message = json.loads(detail).get("message", detail)
        except json.JSONDecodeError:
            message = detail
        raise RuntimeError(f"GitHub API returned HTTP {error.code}: {message}") from error
    except urllib.error.URLError as error:
        raise RuntimeError(f"Could not reach the GitHub API: {error.reason}") from error


def fetch_releases(repository: str, token: str | None) -> list[dict]:
    encoded_repository = "/".join(urllib.parse.quote(part, safe="") for part in repository.split("/"))
    releases: list[dict] = []

    for page in range(1, 101):
        url = (
            f"https://api.github.com/repos/{encoded_repository}/releases"
            f"?per_page=100&page={page}"
        )
        result, _ = github_request(url, token)
        if not isinstance(result, list):
            raise RuntimeError("GitHub returned an unexpected response for the releases endpoint")
        releases.extend(result)
        if len(result) < 100:
            return releases

    raise RuntimeError("Stopped after 10,000 releases; narrow the requested release range")


def releases_since(raw_releases: list[dict], since_tag: str) -> list[Release]:
    baseline = next((release for release in raw_releases if release.get("tag_name") == since_tag), None)
    if baseline is None:
        raise RuntimeError(f"Could not find the baseline release tag {since_tag!r}")

    baseline_value = baseline.get("published_at") or baseline.get("created_at")
    if not baseline_value:
        raise RuntimeError(f"Baseline release {since_tag!r} has no publication date")
    baseline_date = parse_github_date(baseline_value)

    releases: list[Release] = []
    for raw_release in raw_releases:
        if raw_release.get("draft"):
            continue
        published_value = raw_release.get("published_at")
        if not published_value:
            continue
        published_at = parse_github_date(published_value)
        if published_at < baseline_date:
            continue

        assets = tuple(
            Asset(
                name=str(asset.get("name", "unnamed asset")),
                downloads=int(asset.get("download_count", 0)),
                url=str(asset.get("browser_download_url", "")),
            )
            for asset in raw_release.get("assets", [])
        )
        releases.append(
            Release(
                tag=str(raw_release.get("tag_name", "untagged")),
                published_at=published_at,
                assets=assets,
            )
        )

    releases.sort(key=lambda release: release.published_at, reverse=True)
    return releases


def write_csv(path: Path, releases: list[Release]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.writer(file)
        writer.writerow(
            ["version", "published_at", "total_downloads", "asset_name", "asset_downloads", "asset_url"]
        )
        for release in releases:
            if not release.assets:
                writer.writerow(
                    [release.tag, release.published_at.isoformat(), release.downloads, "", 0, ""]
                )
                continue
            for asset in release.assets:
                writer.writerow(
                    [
                        release.tag,
                        release.published_at.isoformat(),
                        release.downloads,
                        asset.name,
                        asset.downloads,
                        asset.url,
                    ]
                )


def nice_axis_max(value: int) -> int:
    if value <= 5:
        return 5
    magnitude = 10 ** (len(str(value)) - 1)
    normalized = value / magnitude
    step = 1 if normalized <= 1 else 2 if normalized <= 2 else 5 if normalized <= 5 else 10
    return step * magnitude


def render_svg(repository: str, since_tag: str, releases: list[Release], generated_at: datetime) -> str:
    width = 1200
    left = 235
    right = 105
    top = 180
    bottom = 84
    bar_height = 22
    row_height = len(SERIES) * 30 + 30
    height = top + max(len(releases), 1) * row_height + bottom
    chart_width = width - left - right
    largest = max((count or 0 for release in releases for count in series_counts(release).values()), default=0)
    axis_max = nice_axis_max(largest)

    def x_for(value: int) -> float:
        return left + (value / axis_max) * chart_width

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-labelledby="title description">',
        "<title id=\"title\">Downloads per release</title>",
        f'<description id="description">Downloads by installer type for each release from {html.escape(since_tag)} onward.</description>',
        "<style>",
        "text { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; fill: #1f2328; }",
        ".title { font-size: 28px; font-weight: 700; }",
        ".subtitle { font-size: 14px; fill: #59636e; }",
        ".version { font-size: 15px; font-weight: 600; }",
        ".date, .tick { font-size: 12px; fill: #59636e; }",
        ".value { font-size: 14px; font-weight: 700; }",
        ".grid { stroke: #d1d9e0; stroke-width: 1; }",
        "</style>",
        '<rect width="100%" height="100%" fill="#ffffff"/>',
        '<text class="title" x="40" y="48">Downloads per release</text>',
        (
            f'<text class="subtitle" x="40" y="76">Installer downloads '
            f'from {html.escape(since_tag)} onward</text>'
        ),
        (
            f'<text class="subtitle" x="40" y="99">Updated {generated_at.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")} '
            f'from github.com/{html.escape(repository)}</text>'
        ),
    ]

    for index, (label, color) in enumerate(SERIES):
        legend_x = 40 + index * 285
        parts.append(f'<rect x="{legend_x}" y="125" width="14" height="14" rx="3" fill="{color}"/>')
        parts.append(f'<text class="subtitle" x="{legend_x + 22}" y="137">{label}</text>')

    for tick_index in range(6):
        tick_value = round(axis_max * tick_index / 5)
        x = x_for(tick_value)
        parts.append(f'<line class="grid" x1="{x:.1f}" y1="{top - 18}" x2="{x:.1f}" y2="{height - bottom + 7}"/>')
        parts.append(f'<text class="tick" x="{x:.1f}" y="{height - bottom + 31}" text-anchor="middle">{tick_value:,}</text>')

    if not releases:
        parts.append(f'<text class="subtitle" x="{left}" y="{top + 24}">No releases found.</text>')

    for index, release in enumerate(releases):
        y = top + index * row_height
        parts.extend(
            [
                f'<text class="version" x="40" y="{y + 14}">{html.escape(release.tag)}</text>',
                f'<text class="date" x="40" y="{y + 32}">{release.published_at:%Y-%m-%d}</text>',
                f'<text class="value" x="40" y="{y + 57}">Total: {release.downloads:,}</text>',
            ]
        )
        counts = series_counts(release)
        for series_index, (label, color) in enumerate(SERIES):
            count = counts[label]
            bar_y = y + series_index * 30
            bar_width = x_for(count or 0) - left
            value = f"{count:,}" if count is not None else "N/A"
            parts.append(
                f'<rect x="{left}" y="{bar_y}" width="{bar_width:.1f}" height="{bar_height}" rx="3" fill="{color}">'
                f'<title>{html.escape(release.tag)} — {label}: {value}</title></rect>'
            )
            parts.append(f'<text class="value" x="{x_for(count or 0) + 10:.1f}" y="{bar_y + 16}">{value}</text>')

    parts.extend(
        [
            f'<text class="subtitle" x="{left + chart_width / 2:.1f}" y="{height - 18}" text-anchor="middle">Downloads</text>',
            "</svg>",
        ]
    )
    return "\n".join(parts) + "\n"


def print_summary(releases: list[Release]) -> None:
    version_width = max([len(release.tag) for release in releases] + [7])
    print(f"{'Version':<{version_width}}  Published   " + "  ".join(f"{label:>20}" for label, _ in SERIES) + f"  {'Total':>10}")
    for release in releases:
        print(
            f"{release.tag:<{version_width}}  {release.published_at:%Y-%m-%d}  "
            + "  ".join(f"{count:>20,}" if count is not None else f"{'N/A':>20}" for count in series_counts(release).values())
            + f"  {release.downloads:>10,}"
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Fetch GitHub release asset download counts and create an SVG bar chart."
    )
    parser.add_argument("--repo", default=DEFAULT_REPOSITORY, help="GitHub repository in owner/name form")
    parser.add_argument(
        "--since-tag",
        default=DEFAULT_SINCE_TAG,
        help="include this release and every release published after it",
    )
    parser.add_argument("--output", type=Path, default=Path(DEFAULT_CHART), help="SVG output path")
    parser.add_argument("--csv", type=Path, default=Path(DEFAULT_CSV), help="CSV output path")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        raw_releases = fetch_releases(args.repo, os.environ.get("GITHUB_TOKEN"))
        releases = releases_since(raw_releases, args.since_tag)
        generated_at = datetime.now(timezone.utc)

        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            render_svg(args.repo, args.since_tag, releases, generated_at), encoding="utf-8"
        )
        write_csv(args.csv, releases)
    except (OSError, RuntimeError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1

    print_summary(releases)
    print(f"\nWrote {args.output} and {args.csv}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
