"""
Create Plex-compatible folders from IMDb links / TMDB.

Reads a text file with IMDb URLs (or tt-IDs), queries the OMDb API for
title and year, and creates Plex-compatible folders:
    MovieTitle (Year) {imdb-ttXXXXXXXX}

TV shows are looked up via TMDB and created as:
    ShowTitle (Year) {tmdb-XXXXX}

Usage:
    plexname                        # Interactive mode (enter titles)
    plexname <title>                # Direct search
    plexname -n <title>             # Dry run (show only, no changes)
    plexname -i <title>             # Interactive: dry run + confirmation
    plexname -o /path/to/movies     # Override target path (movies + series)
    plexname -f movies.txt          # Use a different input file
    plexname -p                     # Prompt for titles (skip input file)
    # When the input file is empty, prompt mode starts automatically.
"""

import argparse
import os
import re
import shutil
import time

import requests


# --- Configuration (loaded at startup from ~/.config/plexname/config.json) ---

API_KEY = None
TMDB_TOKEN = None
MOVIE_PATH = None
SERIES_PATH = None
INPUT_FILE = "movies.txt"


MAX_RETRIES = 3
RETRY_DELAY = 2  # seconds between retries

# Cache for fetched data (avoids duplicate API calls)
_movie_cache = {}
_tmdb_cache = {}


def get_movie_data(imdb_id):
    """
    Fetch movie data from the OMDb API (with retry on transient errors).

    Args:
        imdb_id: IMDb ID (e.g. tt0133093)

    Returns:
        dict with Title, Year etc. on success, None otherwise.
    """
    if imdb_id in _movie_cache:
        return _movie_cache[imdb_id]
    url = f"https://www.omdbapi.com/?i={imdb_id}&apikey={API_KEY}"
    last_error = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = requests.get(url, timeout=10)
            data = response.json()
            if data.get("Response") in ("True", "False"):
                return data
            last_error = data.get("Error", "Unknown API error")
            break
        except Exception as e:
            last_error = str(e)
            if attempt < MAX_RETRIES:
                print(f"  ⚠️ Attempt {attempt}/{MAX_RETRIES} failed, retrying in {RETRY_DELAY}s...")
                time.sleep(RETRY_DELAY)
            else:
                print(f"Error for {imdb_id} after {MAX_RETRIES} attempts: {last_error}")
                return None
    return None


def _tmdb_request(endpoint, params=None):
    """
    Make an authenticated TMDB API request.

    Args:
        endpoint: API path (e.g. /search/multi)
        params: Query parameters as dict

    Returns:
        JSON response as dict.
    """
    url = f"https://api.themoviedb.org/3{endpoint}"
    headers = {
        "Authorization": f"Bearer {TMDB_TOKEN}",
        "accept": "application/json",
    }
    response = requests.get(url, headers=headers, params=params or {}, timeout=10)
    return response.json()


def get_tmdb_details(tmdb_id, media_type):
    """
    Fetch detail data (title, year, cast) from TMDB.

    Args:
        tmdb_id: TMDB ID (e.g. 1396)
        media_type: "tv" or "movie"

    Returns:
        dict with Response, Title, Year, Actors (and imdbID for movies).
        None on error.
    """
    cache_key = f"{media_type}-{tmdb_id}"
    if cache_key in _tmdb_cache:
        return _tmdb_cache[cache_key]

    endpoint = f"/{'tv' if media_type == 'tv' else 'movie'}/{tmdb_id}"
    try:
        data = _tmdb_request(endpoint, {"append_to_response": "credits"})
    except Exception as e:
        print(f"  ❌ TMDB error: {e}")
        return None

    if "id" not in data:
        return None

    cast = data.get("credits", {}).get("cast", [])
    actors = ", ".join(c["name"] for c in cast[:2]) if cast else "N/A"

    if media_type == "tv":
        result = {
            "Response": "True",
            "Title": data.get("name", ""),
            "Year": (data.get("first_air_date") or "")[:4],
            "Actors": actors,
            "Seasons": data.get("number_of_seasons"),
        }
    else:
        result = {
            "Response": "True",
            "Title": data.get("title", ""),
            "Year": (data.get("release_date") or "")[:4],
            "imdbID": data.get("imdb_id", ""),
            "Actors": actors,
        }
        # Populate movie cache so get_movie_data() finds it
        if result.get("imdbID"):
            _movie_cache[result["imdbID"]] = result

    _tmdb_cache[cache_key] = result
    return result


def remove_processed_links(processed_ids, input_file):
    """
    Remove processed IMDb links from the input file.
    Comment lines (#) and blank lines are preserved.
    Creates a backup (.bak) before overwriting.
    """
    if not processed_ids or not os.path.exists(input_file):
        return
    with open(input_file, "r", encoding="utf-8") as f:
        lines = f.readlines()
    new_lines = []
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            new_lines.append(line)
            continue
        match = re.search(r"tt\d+", line)
        if match and match.group() in processed_ids:
            continue  # Remove this line
        new_lines.append(line)
    backup_path = input_file + ".bak"
    shutil.copy2(input_file, backup_path)
    with open(input_file, "w", encoding="utf-8") as f:
        f.writelines(new_lines)
    print(f"📦 Backup saved: {backup_path}")
    print(f"🗑️ {len(processed_ids)} IMDb link(s) removed from {input_file}.")


def _can_write_to(path):
    """Check if the target path is writable."""
    if not os.path.exists(path):
        return False
    return os.access(path, os.W_OK)


def _prompt_seasons(known_seasons=None):
    """
    Ask the user how many seasons to create.

    Args:
        known_seasons: Known season count from TMDB (used as suggestion).

    Returns:
        Number of seasons (int), at least 1.
    """
    if known_seasons:
        prompt = f"  📺 Seasons to create (TMDB: {known_seasons}, Enter = accept): "
    else:
        prompt = "  📺 How many seasons to create? "
    try:
        user_input = input(prompt).strip()
    except (EOFError, KeyboardInterrupt):
        print()
        return known_seasons or 1
    if not user_input and known_seasons:
        return known_seasons
    try:
        n = int(user_input)
        return max(1, n)
    except ValueError:
        if known_seasons:
            return known_seasons
        return 1


def search_by_title(title):
    """
    Search for a movie or TV show by title via the TMDB API.

    Stage 1: Best match from /search/multi with confirmation
             (title, year, type, cast).
    Stage 2: On rejection, numbered list of top 5 results.

    Args:
        title: Search term (movie or show title).

    Returns:
        Tuple (id, media_type, seasons) on success:
            - Movie: ("tt1375666", "movie", None)
            - TV:    ("1396", "tv", 5)
        None on error or cancellation.
    """
    try:
        data = _tmdb_request("/search/multi", {"query": title})
    except Exception as e:
        print(f"  ❌ Search error: {e}")
        return None

    results = [r for r in data.get("results", [])
               if r.get("media_type") in ("movie", "tv")]

    if not results:
        print(f"  ❌ No results for \"{title}\".")
        return None

    # Stage 1: Best match with details
    best = results[0]
    tmdb_id = str(best["id"])
    media_type = best["media_type"]

    details = get_tmdb_details(tmdb_id, media_type)
    if details and details.get("Response") == "True":
        type_label = "TV Show" if media_type == "tv" else "Movie"
        actors = details.get("Actors", "N/A")
        print(f"  🔍 {details['Title']} ({details['Year']}) — {type_label} — starring {actors}")
        try:
            answer = input("     Correct? (Enter/n): ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print()
            return None
        if answer in ("", "j", "ja", "y", "yes"):
            if media_type == "tv":
                seasons = _prompt_seasons(details.get("Seasons"))
                print(f"  ✅ tmdb-{tmdb_id} confirmed.")
                return (tmdb_id, "tv", seasons)
            else:
                imdb_id = details.get("imdbID", "")
                if not imdb_id:
                    print("  ❌ No IMDb ID found for this movie.")
                    return None
                print(f"  ✅ {imdb_id} confirmed.")
                return (imdb_id, "movie", None)

    # Stage 2: List search
    display_results = results[:5]
    print(f"  Results for \"{title}\":")
    for i, r in enumerate(display_results, 1):
        type_label = "TV Show" if r["media_type"] == "tv" else "Movie"
        if r["media_type"] == "tv":
            name = r.get("name", "?")
            date = r.get("first_air_date", "")
        else:
            name = r.get("title", "?")
            date = r.get("release_date", "")
        year = date[:4] if date else "?"
        print(f"    [{i}] {name} ({year}) — {type_label}")

    try:
        choice = input("  Pick a number (or empty = skip): ").strip()
    except (EOFError, KeyboardInterrupt):
        print()
        return None

    if not choice:
        return None
    try:
        idx = int(choice) - 1
        if 0 <= idx < len(display_results):
            chosen = display_results[idx]
            tmdb_id = str(chosen["id"])
            media_type = chosen["media_type"]
            details = get_tmdb_details(tmdb_id, media_type)
            if details and details.get("Response") == "True":
                if media_type == "tv":
                    seasons = _prompt_seasons(details.get("Seasons"))
                    print(f"  ✅ tmdb-{tmdb_id} confirmed.")
                    return (tmdb_id, "tv", seasons)
                else:
                    imdb_id = details.get("imdbID", "")
                    if imdb_id:
                        print(f"  ✅ {imdb_id} confirmed.")
                        return (imdb_id, "movie", None)
                    print("  ❌ No IMDb ID found for this movie.")
        else:
            print("  Invalid selection.")
    except ValueError:
        print("  Invalid input.")
    return None


def _prompt_for_links():
    """
    Interactively ask the user for IMDb URLs, TMDB URLs, or titles.
    Empty input ends the prompt.

    Returns:
        List of tuples (id, media_type, seasons):
            - Movie: (imdb_id, "movie", None)
            - TV:    (tmdb_id, "tv", 5)
    """
    print("Enter IMDb URL, TMDB URL, or title (empty line to start processing):")
    seen = set()
    entries = []
    while True:
        try:
            user_input = input("  > ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not user_input:
            break

        # Detect TMDB URL: themoviedb.org/tv/1396-...
        tmdb_match = re.search(r"themoviedb\.org/tv/(\d+)", user_input)
        if tmdb_match:
            tmdb_id = tmdb_match.group(1)
            key = f"tmdb-{tmdb_id}"
            if key not in seen:
                seen.add(key)
                details = get_tmdb_details(tmdb_id, "tv")
                known_seasons = details.get("Seasons") if details else None
                seasons = _prompt_seasons(known_seasons)
                entries.append((tmdb_id, "tv", seasons))
            continue

        # Detect IMDb URL or tt-ID
        imdb_match = re.search(r"tt\d+", user_input)
        if imdb_match:
            imdb_id = imdb_match.group()
            if imdb_id not in seen:
                seen.add(imdb_id)
                entries.append((imdb_id, "movie", None))
            continue

        # Treat input as title search (movie or TV show)
        result = search_by_title(user_input)
        if result:
            entry_id, media_type, seasons = result
            key = entry_id if media_type == "movie" else f"tmdb-{entry_id}"
            if key not in seen:
                seen.add(key)
                entries.append(result)
                break  # Proceed to processing
    return entries


def process_list(dry_run=False, interactive=False, output_path=None, input_file=None, prompt_mode=False, direct_title=None):
    """
    Read the input file (or prompt interactively), deduplicate IDs,
    and create Plex folders for movies and TV shows.

    Args:
        dry_run: If True, show planned actions without creating folders.
        interactive: If True, show dry run then ask for confirmation.
        output_path: Override the default target path (applies to movies and series).
        input_file: Override the default input file.
        prompt_mode: If True, skip the input file and prompt interactively.
        direct_title: If set, search for this title directly
                      (e.g. "plexname breaking bad").
    """
    movie_path = output_path if output_path is not None else MOVIE_PATH
    series_path = output_path if output_path is not None else SERIES_PATH
    file_path = input_file if input_file is not None else INPUT_FILE
    use_from_file = True

    # Check target path (only in file mode without dry run / interactive)
    if not dry_run and not interactive and not prompt_mode:
        if not os.path.exists(movie_path):
            print(f"❌ ABORT: Path '{movie_path}' not found. NAS connected?")
            return
        if os.path.exists(movie_path) and not _can_write_to(movie_path):
            print(f"❌ ABORT: No write permissions for '{movie_path}'.")
            return

    valid_count = 0
    if direct_title:
        # Direct search: title was passed as argument
        result = search_by_title(direct_title)
        if result:
            entries = [result]
        else:
            entries = []
        use_from_file = False
    elif prompt_mode:
        entries = _prompt_for_links()
        use_from_file = False
    else:
        if not os.path.exists(file_path):
            print(f"File {file_path} not found!")
            return

        with open(file_path, "r", encoding="utf-8") as f:
            lines = f.readlines()

        seen = set()
        entries = []
        for line in lines:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            match = re.search(r"tt\d+", line)
            if not match:
                print(f"Invalid URL skipped: {line}")
                continue
            valid_count += 1
            imdb_id = match.group()
            if imdb_id not in seen:
                seen.add(imdb_id)
                entries.append((imdb_id, "movie", None))

        if not entries:
            entries = _prompt_for_links()
            use_from_file = False

    if not entries:
        print("Nothing to process.")
        return

    if use_from_file and valid_count > len(entries):
        print(f"ℹ️ {valid_count - len(entries)} duplicate(s) skipped → {len(entries)} unique entries")

    mode = "Dry run" if (dry_run or interactive) else "Processing"
    print(f"{mode}: {len(entries)} entries...")

    to_create = []  # For interactive: (folder_name, full_path, seasons) tuples
    successfully_processed = set()  # IMDb IDs for file cleanup
    count_created = 0
    count_existing = 0
    count_failed = 0

    for idx, (entry_id, media_type, seasons) in enumerate(entries, 1):
        if len(entries) > 1:
            print(f"  [{idx}/{len(entries)}] ", end="")

        # Fetch data and determine target path
        if media_type == "tv":
            data = get_tmdb_details(entry_id, "tv")
            id_tag = f"tmdb-{entry_id}"
            target_path = series_path
        else:
            data = get_movie_data(entry_id)
            id_tag = f"imdb-{entry_id}"
            target_path = movie_path

        if data and data.get("Response") == "True":
            title = data["Title"]
            year = data["Year"]

            # Year range like "1999–2000" → use first year only
            year = str(year).split("–")[0].split("-")[0].strip()

            # Folder name: remove invalid characters (/:*?"<>|\ etc.)
            clean_title = re.sub(r'[<>:"/\\|?*]', '', title)
            clean_year = re.sub(r'[<>:"/\\|?*]', '', year) or "0000"
            folder_name = f"{clean_title} ({clean_year}) {{{id_tag}}}"

            full_path = os.path.join(target_path, folder_name)
            exists = os.path.exists(full_path)

            if media_type == "movie":
                successfully_processed.add(entry_id)

            if dry_run or interactive:
                status = "would create" if not exists else "already exists"
                print(f"📋 {status}: {folder_name}")
                if seasons:
                    for s in range(1, seasons + 1):
                        print(f"   📋 Season {s:02d}")
                if not exists:
                    to_create.append((folder_name, full_path, seasons))
                    count_created += 1
                else:
                    count_existing += 1
            elif not exists:
                if not os.path.exists(target_path):
                    print(f"❌ Path '{target_path}' not found. NAS connected?")
                    count_failed += 1
                    continue
                os.makedirs(full_path)
                print(f"✅ Created: {folder_name}")
                if seasons:
                    for s in range(1, seasons + 1):
                        season_path = os.path.join(full_path, f"Season {s:02d}")
                        os.makedirs(season_path)
                        print(f"   ✅ Season {s:02d}")
                count_created += 1
            else:
                print(f"ℹ️ Already exists: {folder_name}")
                count_existing += 1
        else:
            print(f"❌ Error for ID {entry_id}: {data.get('Error') if data else 'No response'}")
            count_failed += 1

        # Rate limiting
        time.sleep(0.2)

    # Summary
    summary_parts = []
    if count_created:
        summary_parts.append(f"{count_created} created")
    if count_existing:
        summary_parts.append(f"{count_existing} already existed")
    if count_failed:
        summary_parts.append(f"{count_failed} failed")
    if summary_parts:
        print(f"\n📊 Summary: {', '.join(summary_parts)}")

    # Normal mode: remove processed links from input file
    if use_from_file and not dry_run and not interactive and successfully_processed:
        remove_processed_links(successfully_processed, file_path)

    # Interactive: create folders after confirmation (no repeated API calls)
    if interactive and to_create:
        paths_needed = set(os.path.dirname(fp) for _, fp, _ in to_create)
        for p in paths_needed:
            if not os.path.exists(p):
                print(f"❌ ABORT: Path '{p}' not found. NAS connected?")
                return
            if not _can_write_to(p):
                print(f"❌ ABORT: No write permissions for '{p}'.")
                return
        answer = input(f"\nCreate {len(to_create)} folder(s)? (y/n): ").strip().lower()
        if answer in ("j", "ja", "y", "yes"):
            for folder_name, full_path, seasons in to_create:
                os.makedirs(full_path)
                print(f"✅ Created: {folder_name}")
                if seasons:
                    for s in range(1, seasons + 1):
                        season_path = os.path.join(full_path, f"Season {s:02d}")
                        os.makedirs(season_path)
                        print(f"   ✅ Season {s:02d}")
            if use_from_file and successfully_processed:
                remove_processed_links(successfully_processed, file_path)
        else:
            print("Cancelled.")


def _show_help():
    """Display detailed help text."""
    movie_path = MOVIE_PATH or "<not configured>"
    series_path = SERIES_PATH or "<not configured>"
    lines = [
        "🎬 plexname — Create Plex-compatible folders from IMDb/TMDB",
        "",
        "Usage:",
        "  plexname                      Interactive mode (enter titles)",
        "  plexname <title>              Direct search (e.g. plexname breaking bad)",
        "  plexname -n <title>           Dry run: show what would be created",
        "  plexname -i <title>           Interactive: show first, then confirm",
        "  plexname -f movies.txt        Process IMDb URLs from file",
        "  plexname -o /path <title>     Override target path (movies + series)",
        "  plexname setup                (Re)configure API keys and paths",
        "  plexname help                 Show this help",
        "",
        "Input formats:",
        "  breaking bad                  Title search (movies + TV via TMDB)",
        "  https://imdb.com/title/tt...  IMDb URL → movie",
        "  tt1375666                     IMDb ID → movie",
        "  https://themoviedb.org/tv/... TMDB URL → TV show",
        "",
        "Folder format:",
        f"  Movies:  Inception (2010) {{imdb-tt1375666}}      → {movie_path}",
        f"  Series:  Breaking Bad (2008) {{tmdb-1396}}         → {series_path}",
        "           └── Season 01, Season 02, ...",
    ]
    print("\n".join(lines))


def _load_config():
    """Load configuration and set module globals."""
    global API_KEY, TMDB_TOKEN, MOVIE_PATH, SERIES_PATH
    import config
    cfg = config.get_config()
    API_KEY = cfg["omdb_api_key"]
    TMDB_TOKEN = cfg["tmdb_token"]
    MOVIE_PATH = cfg["movie_path"]
    SERIES_PATH = cfg["series_path"]


def main():
    parser = argparse.ArgumentParser(
        prog="plexname",
        description="Create Plex-compatible folders from IMDb/TMDB",
    )
    parser.add_argument("title", nargs="*", help="Movie or TV show title (starts direct search)")
    parser.add_argument("-n", "--dry-run", action="store_true", help="Show what would be created (no changes)")
    parser.add_argument("-i", "--interactive", action="store_true", help="Dry run, then confirm: create folders? (y/n)")
    parser.add_argument("-o", "--output", metavar="PATH", help="Override target path for Plex folders")
    parser.add_argument("-f", "--file", metavar="FILE", dest="input_file", help="Alternative input file (default: movies.txt)")
    parser.add_argument("-p", "--prompt", action="store_true", help="Prompt for movies/series (skip input file)")
    args = parser.parse_args()

    # Handle setup and help before loading config
    if args.title and args.title[0].lower() == "setup":
        import config
        config.run_setup()
        return

    if args.title and args.title[0].lower() == "help":
        # Load config if available, but don't force setup
        import config
        cfg = config.load_config()
        if cfg:
            global MOVIE_PATH, SERIES_PATH
            MOVIE_PATH = cfg["movie_path"]
            SERIES_PATH = cfg["series_path"]
        _show_help()
        return

    # Load configuration (triggers setup on first run)
    _load_config()

    if args.title:
        # Direct search: "plexname breaking bad" → join title words
        title = " ".join(args.title)
        process_list(dry_run=args.dry_run, interactive=args.interactive,
                     output_path=args.output, input_file=args.input_file,
                     prompt_mode=True, direct_title=title)
    elif args.input_file:
        # File mode: only when -f is explicitly given
        process_list(dry_run=args.dry_run, interactive=args.interactive,
                     output_path=args.output, input_file=args.input_file)
    else:
        # No arguments or -p → interactive prompt
        process_list(dry_run=args.dry_run, interactive=args.interactive,
                     output_path=args.output, prompt_mode=True)


if __name__ == "__main__":
    main()
