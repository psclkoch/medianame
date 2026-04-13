"""
Configuration management for plexname.

Stores API keys and paths in ~/.config/plexname/config.json.
On first run, the user is prompted interactively for all values.
"""

import json
import os
import stat

CONFIG_DIR = os.path.join(os.path.expanduser("~"), ".config", "plexname")
CONFIG_PATH = os.path.join(CONFIG_DIR, "config.json")

REQUIRED_KEYS = ["omdb_api_key", "tmdb_token", "movie_path", "series_path"]


def load_config():
    """
    Read configuration from ~/.config/plexname/config.json.

    Returns:
        dict with all config values, or None if the file is missing
        or incomplete.
    """
    if not os.path.exists(CONFIG_PATH):
        return None
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            cfg = json.load(f)
    except (json.JSONDecodeError, OSError):
        return None
    for key in REQUIRED_KEYS:
        if not cfg.get(key):
            return None
    return cfg


def save_config(cfg):
    """Save configuration and set restrictive file permissions."""
    os.makedirs(CONFIG_DIR, exist_ok=True)
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)
    # Owner read/write only (file contains API tokens)
    os.chmod(CONFIG_PATH, stat.S_IRUSR | stat.S_IWUSR)


def run_setup():
    """
    Interactive setup: prompts the user for API keys and paths.

    Returns:
        dict with the complete configuration.
    """
    print("=" * 50)
    print("  🎬 plexname — First-time setup")
    print("=" * 50)

    existing = load_config() or {}

    # 1. OMDb API Key
    print()
    print("1) OMDb API Key (for movie lookups via IMDb ID)")
    print("   Get a free key: https://www.omdbapi.com/apikey.aspx")
    print("   → Choose 'FREE', enter your email, key arrives by mail.")
    default = existing.get("omdb_api_key", "")
    omdb_key = _prompt_value("   API Key", default)

    # 2. TMDB Token
    print()
    print("2) TMDB Read Access Token (for title search, TV shows, cast)")
    print("   Create account: https://www.themoviedb.org/signup")
    print("   Get token: https://www.themoviedb.org/settings/api")
    print("   → Copy the long 'API Read Access Token' (not the short API key).")
    default = existing.get("tmdb_token", "")
    tmdb_token = _prompt_value("   Token", default)

    # 3. Movie path
    print()
    print("3) Plex movie folder (root of your movie library)")
    print("   Example: /Volumes/NAS/Movies or /mnt/media/movies")
    default = existing.get("movie_path", "")
    movie_path = _prompt_value("   Path", default)

    # 4. Series path
    print()
    print("4) Plex TV show folder (root of your series library)")
    print("   Example: /Volumes/NAS/TV or /mnt/media/tv")
    default = existing.get("series_path", "")
    series_path = _prompt_value("   Path", default)

    cfg = {
        "omdb_api_key": omdb_key,
        "tmdb_token": tmdb_token,
        "movie_path": movie_path,
        "series_path": series_path,
    }

    save_config(cfg)
    print()
    print(f"✅ Configuration saved: {CONFIG_PATH}")
    print("   Reconfigure anytime: plexname setup")
    print()
    return cfg


def get_config():
    """
    Load configuration. Starts setup if not yet configured.

    Returns:
        dict with all config values.
    """
    cfg = load_config()
    if cfg is not None:
        return cfg
    print("Not configured yet. Starting setup...\n")
    return run_setup()


def _prompt_value(label, default=""):
    """Prompt for a value, showing the existing value as a default if available."""
    if default:
        preview = default if len(default) <= 30 else default[:20] + "..." + default[-7:]
        entry = input(f"{label} [{preview}]: ").strip()
        return entry if entry else default
    else:
        while True:
            entry = input(f"{label}: ").strip()
            if entry:
                return entry
            print("   Input required.")
