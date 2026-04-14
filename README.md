# medianame

[![Tests](https://github.com/psclkoch/medianame/actions/workflows/tests.yml/badge.svg)](https://github.com/psclkoch/medianame/actions/workflows/tests.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.9+](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/downloads/)

CLI tool to create [Plex](https://www.plex.tv/)- or [Jellyfin](https://jellyfin.org/)-compatible folder structures for movies and TV shows.

Search by title, confirm, done — medianame creates properly named folders with the correct metadata tags so your media server can match them automatically.

## What it does

```
$ medianame inception
  🔍 Inception (2010) — Movie — starring Leonardo DiCaprio, Joseph Gordon-Levitt
     Correct? (Enter/n):
  ✅ tt1375666 confirmed.
✅ Created: Inception (2010) {imdb-tt1375666}

$ medianame breaking bad
  🔍 Breaking Bad (2008) — TV Show — starring Bryan Cranston, Aaron Paul
     Correct? (Enter/n):
  📺 Seasons to create (TMDB: 5, Enter = accept):
  ✅ tmdb-1396 confirmed.
✅ Created: Breaking Bad (2008) {tmdb-1396}
   ✅ Season 01
   ✅ Season 02
   ✅ Season 03
   ✅ Season 04
   ✅ Season 05
```

### Naming conventions

medianame supports two naming presets:

**Plex** — [naming docs](https://support.plex.tv/articles/naming-and-organizing-your-movie-media-files/):
- Movies: `Title (Year) {imdb-ttXXXXXXX}`
- TV shows: `Title (Year) {tmdb-XXXXX}` with `Season 01`, `Season 02`, … subfolders

**Jellyfin** — [naming docs](https://jellyfin.org/docs/general/server/media/movies):
- Movies: `Title (Year) [imdbid-ttXXXXXXX]` or `[tmdbid-XXXXX]`
- TV shows: `Title (Year) [tmdbid-XXXXX]` or `[imdbid-ttXXXXXXX]`

Unlike Plex, Jellyfin lets you choose either IMDb or TMDB IDs for both media types — configurable during setup.

## Installation

**Requirements:** Python 3.9+ and [pipx](https://pipx.pypa.io/) (recommended) or pip.

```bash
# Clone the repository
git clone https://github.com/psclkoch/medianame.git
cd medianame

# Install with pipx (recommended)
pipx install -e .

# Or with pip
pip install -e .
```

On first run, medianame will walk you through the setup:

```
$ medianame
Not configured yet. Starting setup...

==================================================
  🎬 medianame — First-time setup
==================================================

1) OMDb API Key (for movie lookups via IMDb ID)
2) TMDB Read Access Token (for title search, TV shows, cast)
3) Movie folder (root of your movie library)
4) TV show folder (root of your series library)
5) Media server (plex / jellyfin)
6) Movie ID source (only for Jellyfin: imdb / tmdb)
7) TV show ID source (only for Jellyfin: imdb / tmdb)

✅ Configuration saved: ~/.config/medianame/config.json
```

Your configuration is stored in `~/.config/medianame/config.json`. Run `medianame setup` at any time to change it.

## Usage

```bash
medianame                        # Interactive mode — enter titles one by one
medianame <title>                # Direct search (e.g. medianame the matrix)
medianame -n <title>             # Dry run — show what would be created
medianame -o /path <title>       # Override target path for this run
medianame -f movies.txt          # Batch mode — process IMDb URLs from a file
medianame --preset jellyfin ...  # Override naming preset for this run
medianame setup                  # (Re)configure API keys, paths, preset
medianame help                   # Show detailed help
```

### Input formats

In interactive mode, you can enter:

| Input | Result |
|---|---|
| `breaking bad` | Title search (movies + TV via TMDB) |
| `https://www.imdb.com/title/tt1375666/` | Direct IMDb URL → movie |
| `tt1375666` | IMDb ID → movie |
| `https://www.themoviedb.org/tv/1396-breaking-bad` | TMDB URL → TV show |

### Batch mode

Create a text file with one IMDb URL or `tt`-ID per line:

```
https://www.imdb.com/title/tt0133093/
https://www.imdb.com/title/tt1375666/
tt0167260
```

Then run:

```bash
medianame -f movies.txt
```

Successfully processed entries are automatically removed from the file (a `.bak` backup is created).

## How it works

1. **Title search** uses TMDB's `/search/multi` endpoint — one search returns both movies and TV shows
2. **Movies** are tagged with the preferred ID format (`{imdb-...}` / `[imdbid-...]` / `[tmdbid-...]`)
3. **TV shows** are tagged with the preferred ID format and get Season subfolders
4. When Jellyfin + TMDB movie IDs are requested from an IMDb input, `/find` resolves IMDb → TMDB
5. When Jellyfin + IMDb TV IDs are requested, `external_ids` on TMDB provides the IMDb ID
6. Folders are created directly in your configured library paths

## Upgrading from plexname (v1.0)

medianame v1.1 is the renamed successor of plexname v1.0. If you had v1.0 installed:

```bash
pipx uninstall plexname
cd ~/Desktop/IMDB   # or wherever your clone lives
git pull
pipx install -e .
```

Your existing `~/.config/plexname/config.json` is **automatically migrated** to `~/.config/medianame/config.json` on first run. Plex naming is the default, so your existing folders continue to work without changes.

## API keys

medianame uses two free APIs:

- **[OMDb API](https://www.omdbapi.com/)** — for movie lookups by IMDb ID. Free tier: 1,000 requests/day.
- **[TMDB API](https://www.themoviedb.org/documentation/api)** — for title search, TV show data, and cast info. Free for non-commercial use.

## License

MIT
