# Welcome to the Compositor Product Roadmap
 
Note that this GitHub repository is a bit unusual in that it does not contain any source code. Its purpose is solely for **issue tracking**. 
The idea is to have the complete list of all known bugs, issues, and possible improvements out in public, accessible to anybody.
 
### Issues

Under [Issues](https://github.com/ktraunmueller/Compositor/issues), you can find a list of all known issues and planned features.

### Milestones & Themes

Under [Milestones](https://github.com/ktraunmueller/Compositor/milestones), you can find a list of feature _themes_ (_topics_, _epics_), together with milestones for the next upcoming releases. 

### Published Releases

Check the [releases page](https://github.com/ktraunmueller/Compositor/releases) for past and current releases.

### Release Download Statistics

Run the dependency-free reporting script from the repository root:

```sh
./scripts/github_release_downloads.py
```

It fetches GitHub's current asset download counts for release `0.9.0` and every
release published after it. The script prints a summary and creates two local
files:

- `release-downloads.svg` — grouped bars per version for macOS DMG, macOS ZIP
  (Sparkle), Windows x64 MSIX, and Windows ARM64 MSIX; missing assets show `N/A`
- `release-downloads.csv` — the underlying per-asset counts

For authenticated requests, or if GitHub's anonymous API rate limit is too low,
set a personal access token in `GITHUB_TOKEN`. Use `--help` to see options for a
different repository, starting tag, or output paths.
