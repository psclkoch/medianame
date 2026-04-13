"""
Tests for movie_fix.py — Plex folder creation from IMDb links / TMDB.
"""
import os
import re
import shutil
import tempfile
import unittest
from unittest.mock import patch

import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import movie_fix


class TestMovieFix(unittest.TestCase):
    """Test scenarios for movie_fix.py"""

    def setUp(self):
        """Create temporary directories for each test."""
        self.temp_dir = tempfile.mkdtemp()
        self.temp_input_dir = tempfile.mkdtemp()
        self.original_movie_path = movie_fix.MOVIE_PATH
        self.original_input_file = movie_fix.INPUT_FILE
        movie_fix.MOVIE_PATH = self.temp_dir

    def tearDown(self):
        """Clean up."""
        movie_fix.MOVIE_PATH = self.original_movie_path
        movie_fix.INPUT_FILE = self.original_input_file
        shutil.rmtree(self.temp_dir, ignore_errors=True)
        shutil.rmtree(self.temp_input_dir, ignore_errors=True)

    def test_imdb_id_extraction(self):
        """tt-number is extracted from various URL formats."""
        test_cases = [
            ("https://www.imdb.com/title/tt0133093/", "tt0133093"),
            ("https://imdb.com/title/tt0133093", "tt0133093"),
            ("https://www.imdb.com/title/tt0133093/reviews", "tt0133093"),
            ("tt0133093", "tt0133093"),
            ("  tt0133093  ", "tt0133093"),
        ]
        for url, expected in test_cases:
            match = re.search(r'tt\d+', url.strip())
            self.assertIsNotNone(match, f"No match for: {url}")
            self.assertEqual(match.group(), expected)

    def test_invalid_url_skipped(self):
        """Invalid URLs are skipped — falls through to prompt mode with empty input."""
        movie_fix.INPUT_FILE = self._create_input_file([
            "https://www.google.com",
            "no-tt-number",
            "  ",
        ])
        with patch('movie_fix.get_movie_data', return_value=None):
            with patch('builtins.input', return_value=""):
                movie_fix.process_list()
        self.assertEqual(len(self._get_created_folders()), 0)

    def test_valid_movie_creates_folder(self):
        """Valid movie creates a Plex-format folder."""
        movie_fix.INPUT_FILE = self._create_input_file([
            "https://www.imdb.com/title/tt0133093/"
        ])
        mock_response = {
            "Response": "True",
            "Title": "The Matrix",
            "Year": "1999",
        }
        with patch('movie_fix.get_movie_data', return_value=mock_response):
            movie_fix.process_list()

        folders = self._get_created_folders()
        self.assertEqual(len(folders), 1)
        self.assertIn("The Matrix", folders[0])
        self.assertIn("(1999)", folders[0])
        self.assertIn("{imdb-tt0133093}", folders[0])

    def test_special_characters_removed(self):
        """Special characters are removed from folder names."""
        movie_fix.INPUT_FILE = self._create_input_file([
            "https://www.imdb.com/title/tt0133093/"
        ])
        mock_response = {
            "Response": "True",
            "Title": "Star Wars: Episode IV - A New Hope",
            "Year": "1977",
        }
        with patch('movie_fix.get_movie_data', return_value=mock_response):
            movie_fix.process_list()

        folders = self._get_created_folders()
        self.assertEqual(len(folders), 1)
        self.assertNotIn(":", folders[0])
        self.assertNotIn("/", folders[0])
        self.assertNotIn("\\", folders[0])

    def test_duplicate_not_recreated(self):
        """Already existing folder is not recreated."""
        movie_fix.INPUT_FILE = self._create_input_file([
            "https://www.imdb.com/title/tt0133093/",
            "https://www.imdb.com/title/tt0133093/",  # duplicate
        ])
        mock_response = {
            "Response": "True",
            "Title": "The Matrix",
            "Year": "1999",
        }
        with patch('movie_fix.get_movie_data', return_value=mock_response):
            movie_fix.process_list()

        folders = self._get_created_folders()
        self.assertEqual(len(folders), 1)

    def test_api_error_handled(self):
        """API errors are handled gracefully."""
        movie_fix.INPUT_FILE = self._create_input_file([
            "https://www.imdb.com/title/tt9999999/"
        ])
        mock_response = {"Response": "False", "Error": "Incorrect IMDb ID"}
        with patch('movie_fix.get_movie_data', return_value=mock_response):
            movie_fix.process_list()

        self.assertEqual(len(self._get_created_folders()), 0)

    def test_path_not_found_aborts(self):
        """Aborts when target path does not exist."""
        movie_fix.MOVIE_PATH = "/nonexistent/path/xyz123"
        movie_fix.INPUT_FILE = self._create_input_file(["tt0133093"])
        with patch('movie_fix.get_movie_data') as mock_api:
            movie_fix.process_list()
            mock_api.assert_not_called()

    def test_empty_input_file(self):
        """Empty file → prompt mode; empty input → no API call."""
        movie_fix.INPUT_FILE = self._create_input_file([])
        with patch('movie_fix.get_movie_data') as mock_api:
            with patch('builtins.input', return_value=""):
                movie_fix.process_list()
            mock_api.assert_not_called()
        self.assertEqual(len(self._get_created_folders()), 0)

    def test_deduplication_single_api_call(self):
        """Duplicate entries in input file → only 1 API call per tt-ID."""
        movie_fix.INPUT_FILE = self._create_input_file([
            "https://www.imdb.com/title/tt0133093/",
            "tt0133093",
            "https://imdb.com/title/tt0133093/reviews",
        ])
        mock_response = {"Response": "True", "Title": "The Matrix", "Year": "1999"}
        with patch("movie_fix.get_movie_data", return_value=mock_response) as mock_api:
            movie_fix.process_list()
        self.assertEqual(mock_api.call_count, 1)
        folders = self._get_created_folders()
        self.assertEqual(len(folders), 1)

    def test_dry_run_creates_nothing(self):
        """Dry run creates no folders."""
        movie_fix.INPUT_FILE = self._create_input_file(["tt0133093"])
        mock_response = {"Response": "True", "Title": "The Matrix", "Year": "1999"}
        with patch("movie_fix.get_movie_data", return_value=mock_response):
            movie_fix.process_list(dry_run=True)
        self.assertEqual(len(self._get_created_folders()), 0)

    def test_year_n_a_handling(self):
        """Year 'N/A' from OMDb is handled (no / in path)."""
        movie_fix.INPUT_FILE = self._create_input_file(["tt0133093"])
        mock_response = {
            "Response": "True",
            "Title": "Test Film",
            "Year": "N/A",
        }
        with patch('movie_fix.get_movie_data', return_value=mock_response):
            movie_fix.process_list()

        folders = self._get_created_folders()
        self.assertEqual(len(folders), 1)
        self.assertIn("NA", folders[0])
        self.assertNotIn("/", folders[0])

    def test_interactive_confirm_creates_folders(self):
        """Interactive mode with 'j' → folders are created."""
        movie_fix.INPUT_FILE = self._create_input_file(["tt0133093"])
        mock_response = {"Response": "True", "Title": "The Matrix", "Year": "1999"}
        with patch("movie_fix.get_movie_data", return_value=mock_response):
            with patch("builtins.input", return_value="j"):
                movie_fix.process_list(interactive=True)
        folders = self._get_created_folders()
        self.assertEqual(len(folders), 1)
        self.assertIn("The Matrix", folders[0])

    def test_interactive_decline_creates_nothing(self):
        """Interactive mode with 'n' → no folders created."""
        movie_fix.INPUT_FILE = self._create_input_file(["tt0133093"])
        mock_response = {"Response": "True", "Title": "The Matrix", "Year": "1999"}
        with patch("movie_fix.get_movie_data", return_value=mock_response):
            with patch("builtins.input", return_value="n"):
                movie_fix.process_list(interactive=True)
        self.assertEqual(len(self._get_created_folders()), 0)

    def test_interactive_all_exist_no_prompt(self):
        """Interactive mode, all folders exist → input() is not called."""
        movie_fix.INPUT_FILE = self._create_input_file(["tt0133093"])
        os.makedirs(os.path.join(self.temp_dir, "The Matrix (1999) {imdb-tt0133093}"))
        mock_response = {"Response": "True", "Title": "The Matrix", "Year": "1999"}
        with patch("movie_fix.get_movie_data", return_value=mock_response):
            with patch("builtins.input") as mock_input:
                movie_fix.process_list(interactive=True)
                mock_input.assert_not_called()

    def test_interactive_path_missing_on_confirm_aborts(self):
        """Interactive mode, target path missing on confirm → no folder created."""
        movie_fix.MOVIE_PATH = "/nonexistent/path/xyz789"
        movie_fix.INPUT_FILE = self._create_input_file(["tt0133093"])
        mock_response = {"Response": "True", "Title": "The Matrix", "Year": "1999"}
        with patch("movie_fix.get_movie_data", return_value=mock_response):
            with patch("builtins.input", return_value="j"):
                movie_fix.process_list(interactive=True)
        self.assertEqual(len(self._get_created_folders()), 0)

    def test_year_range_extraction(self):
        """Year range '1999–2000' is reduced to the first year."""
        movie_fix.INPUT_FILE = self._create_input_file(["tt0133093"])
        mock_response = {
            "Response": "True",
            "Title": "Test Film",
            "Year": "1999–2000",  # en-dash
        }
        with patch("movie_fix.get_movie_data", return_value=mock_response):
            movie_fix.process_list()
        folders = self._get_created_folders()
        self.assertEqual(len(folders), 1)
        self.assertIn("(1999)", folders[0])
        self.assertNotIn("2000", folders[0])

    def test_year_range_ascii_hyphen(self):
        """Year range '1999-2000' (ASCII hyphen) is reduced to the first year."""
        movie_fix.INPUT_FILE = self._create_input_file(["tt0133093"])
        mock_response = {
            "Response": "True",
            "Title": "Test Film",
            "Year": "1999-2000",
        }
        with patch("movie_fix.get_movie_data", return_value=mock_response):
            movie_fix.process_list()
        folders = self._get_created_folders()
        self.assertEqual(len(folders), 1)
        self.assertIn("(1999)", folders[0])

    def test_utf8_umlauts_in_title(self):
        """Umlauts in movie title are preserved correctly."""
        movie_fix.INPUT_FILE = self._create_input_file(["tt0133093"])
        mock_response = {
            "Response": "True",
            "Title": "München",
            "Year": "2005",
        }
        with patch('movie_fix.get_movie_data', return_value=mock_response):
            movie_fix.process_list()
        folders = self._get_created_folders()
        self.assertEqual(len(folders), 1)
        self.assertIn("München", folders[0])
        self.assertIn("(2005)", folders[0])

    def test_tt_id_in_middle_of_line(self):
        """tt-number in the middle of a line is recognized."""
        movie_fix.INPUT_FILE = self._create_input_file([
            "See tt0133093 for details",
        ])
        mock_response = {"Response": "True", "Title": "The Matrix", "Year": "1999"}
        with patch("movie_fix.get_movie_data", return_value=mock_response):
            movie_fix.process_list()
        folders = self._get_created_folders()
        self.assertEqual(len(folders), 1)
        self.assertIn("tt0133093", folders[0])

    def test_multiple_different_movies(self):
        """Multiple movies → multiple folders."""
        movie_fix.INPUT_FILE = self._create_input_file(["tt0133093", "tt0167260"])
        def mock_get_movie(imdb_id):
            if imdb_id == "tt0133093":
                return {"Response": "True", "Title": "The Matrix", "Year": "1999"}
            return {"Response": "True", "Title": "The Lord of the Rings", "Year": "2003"}
        with patch("movie_fix.get_movie_data", side_effect=mock_get_movie):
            movie_fix.process_list()
        folders = self._get_created_folders()
        self.assertEqual(len(folders), 2)
        folder_names = " ".join(folders)
        self.assertIn("The Matrix", folder_names)
        self.assertIn("The Lord of the Rings", folder_names)

    def test_get_movie_data_returns_none(self):
        """API error (None) → no folder, no crash."""
        movie_fix.INPUT_FILE = self._create_input_file(["tt0133093"])
        with patch("movie_fix.get_movie_data", return_value=None):
            movie_fix.process_list()
        self.assertEqual(len(self._get_created_folders()), 0)

    def test_interactive_accepts_ja_as_confirmation(self):
        """Interactive mode accepts 'ja' as confirmation."""
        movie_fix.INPUT_FILE = self._create_input_file(["tt0133093"])
        mock_response = {"Response": "True", "Title": "The Matrix", "Year": "1999"}
        with patch("movie_fix.get_movie_data", return_value=mock_response):
            with patch("builtins.input", return_value="ja"):
                movie_fix.process_list(interactive=True)
        folders = self._get_created_folders()
        self.assertEqual(len(folders), 1)

    def test_prompt_mode_creates_folder_from_input(self):
        """Prompt mode: entered link creates a folder, movies.txt is not used."""
        mock_response = {"Response": "True", "Title": "The Matrix", "Year": "1999"}
        with patch("movie_fix.get_movie_data", return_value=mock_response):
            with patch("builtins.input", side_effect=["tt0133093", ""]):
                movie_fix.process_list(prompt_mode=True)
        folders = self._get_created_folders()
        self.assertEqual(len(folders), 1)
        self.assertIn("The Matrix", folders[0])

    def test_prompt_mode_empty_input_creates_nothing(self):
        """Prompt mode with immediate empty input → no processing."""
        with patch("movie_fix.get_movie_data") as mock_api:
            with patch("builtins.input", return_value=""):
                movie_fix.process_list(prompt_mode=True)
            mock_api.assert_not_called()
        self.assertEqual(len(self._get_created_folders()), 0)

    def test_prompt_mode_multiple_links(self):
        """Prompt mode with multiple links → multiple folders."""
        def mock_get_movie(imdb_id):
            if imdb_id == "tt0133093":
                return {"Response": "True", "Title": "The Matrix", "Year": "1999"}
            return {"Response": "True", "Title": "Inception", "Year": "2010"}
        with patch("movie_fix.get_movie_data", side_effect=mock_get_movie):
            with patch("builtins.input", side_effect=["tt0133093", "tt1375666", ""]):
                movie_fix.process_list(prompt_mode=True)
        folders = self._get_created_folders()
        self.assertEqual(len(folders), 2)
        self.assertIn("The Matrix", " ".join(folders))
        self.assertIn("Inception", " ".join(folders))

    def test_prompt_mode_invalid_input_then_valid(self):
        """Prompt mode: invalid input is skipped, valid input is processed."""
        mock_response = {"Response": "True", "Title": "The Matrix", "Year": "1999"}
        with patch("movie_fix.get_movie_data", return_value=mock_response):
            with patch("builtins.input", side_effect=["invalid", "tt0133093", ""]):
                movie_fix.process_list(prompt_mode=True)
        folders = self._get_created_folders()
        self.assertEqual(len(folders), 1)

    def test_remove_processed_links_creates_backup(self):
        """After processing, links are removed from file and a backup is created."""
        input_path = self._create_input_file(["tt0133093"])
        movie_fix.INPUT_FILE = input_path
        mock_response = {"Response": "True", "Title": "The Matrix", "Year": "1999"}
        with patch("movie_fix.get_movie_data", return_value=mock_response):
            movie_fix.process_list()
        with open(input_path, encoding="utf-8") as f:
            content = f.read()
        self.assertNotIn("tt0133093", content)
        self.assertTrue(os.path.exists(input_path + ".bak"))
        with open(input_path + ".bak", encoding="utf-8") as f:
            bak_content = f.read()
        self.assertIn("tt0133093", bak_content)

    def test_prompt_mode_does_not_modify_file(self):
        """Prompt mode does not modify movies.txt (use_from_file=False)."""
        input_path = self._create_input_file(["tt0133093"])
        movie_fix.INPUT_FILE = input_path
        mock_response = {"Response": "True", "Title": "The Matrix", "Year": "1999"}
        with patch("movie_fix.get_movie_data", return_value=mock_response):
            with patch("builtins.input", side_effect=["tt0133093", ""]):
                movie_fix.process_list(prompt_mode=True)
        with open(input_path, encoding="utf-8") as f:
            content = f.read()
        self.assertIn("tt0133093", content)
        self.assertFalse(os.path.exists(input_path + ".bak"))

    def test_custom_output_path(self):
        """-o overrides target path."""
        custom_dir = os.path.join(self.temp_dir, "custom_movies")
        os.makedirs(custom_dir)
        movie_fix.INPUT_FILE = self._create_input_file(["tt0133093"])
        mock_response = {"Response": "True", "Title": "The Matrix", "Year": "1999"}
        with patch("movie_fix.get_movie_data", return_value=mock_response):
            movie_fix.process_list(output_path=custom_dir)
        folders = [f for f in os.listdir(custom_dir) if os.path.isdir(os.path.join(custom_dir, f))]
        self.assertEqual(len(folders), 1)
        self.assertIn("The Matrix", folders[0])

    def test_custom_input_file(self):
        """-f overrides input file."""
        other_input = os.path.join(self.temp_input_dir, "other.txt")
        with open(other_input, "w", encoding="utf-8") as f:
            f.write("tt0133093\n")
        mock_response = {"Response": "True", "Title": "The Matrix", "Year": "1999"}
        with patch("movie_fix.get_movie_data", return_value=mock_response):
            movie_fix.process_list(input_file=other_input)
        folders = self._get_created_folders()
        self.assertEqual(len(folders), 1)

    def test_file_not_found(self):
        """Missing input file → error message, no processing."""
        movie_fix.INPUT_FILE = "/nonexistent/file_xyz.txt"
        with patch("movie_fix.get_movie_data") as mock_api:
            movie_fix.process_list()
            mock_api.assert_not_called()
        self.assertEqual(len(self._get_created_folders()), 0)

    def test_empty_file_fallback_prompt_with_link(self):
        """Empty file → prompt mode → entered link is processed."""
        movie_fix.INPUT_FILE = self._create_input_file([])
        mock_response = {"Response": "True", "Title": "The Matrix", "Year": "1999"}
        with patch("movie_fix.get_movie_data", return_value=mock_response):
            with patch("builtins.input", side_effect=["tt0133093", ""]):
                movie_fix.process_list()
        folders = self._get_created_folders()
        self.assertEqual(len(folders), 1)

    # --- TV show tests (TMDB) ---

    def test_series_prompt_creates_tmdb_folder_with_seasons(self):
        """TV show via title search creates folder with tmdb tag and Season subfolders."""
        self.series_dir = tempfile.mkdtemp()
        movie_fix.SERIES_PATH = self.series_dir
        search_response = {"results": [
            {"id": 1396, "media_type": "tv", "name": "Breaking Bad", "first_air_date": "2008-01-20"},
        ]}
        details_response = {
            "id": 1396, "name": "Breaking Bad", "first_air_date": "2008-01-20",
            "number_of_seasons": 5,
            "credits": {"cast": [{"name": "Bryan Cranston"}, {"name": "Aaron Paul"}]},
        }
        with patch("movie_fix._tmdb_request", side_effect=[search_response, details_response]):
            with patch("builtins.input", side_effect=["breaking bad", "", "", ""]):
                movie_fix.process_list(prompt_mode=True)
        folders = [f for f in os.listdir(self.series_dir)
                   if os.path.isdir(os.path.join(self.series_dir, f))]
        self.assertEqual(len(folders), 1)
        self.assertIn("Breaking Bad", folders[0])
        self.assertIn("{tmdb-1396}", folders[0])
        self.assertIn("(2008)", folders[0])
        series_path = os.path.join(self.series_dir, folders[0])
        season_dirs = sorted(os.listdir(series_path))
        self.assertEqual(len(season_dirs), 5)
        self.assertEqual(season_dirs[0], "Season 01")
        self.assertEqual(season_dirs[4], "Season 05")
        shutil.rmtree(self.series_dir, ignore_errors=True)

    def test_movie_via_tmdb_search_uses_imdb_tag(self):
        """Movie via TMDB title search creates folder with imdb tag."""
        search_response = {"results": [
            {"id": 27205, "media_type": "movie", "title": "Inception", "release_date": "2010-07-16"},
        ]}
        details_response = {
            "id": 27205, "title": "Inception", "release_date": "2010-07-16",
            "imdb_id": "tt1375666",
            "credits": {"cast": [{"name": "Leonardo DiCaprio"}]},
        }
        with patch("movie_fix._tmdb_request", side_effect=[search_response, details_response]):
            with patch("movie_fix.get_movie_data", return_value={
                "Response": "True", "Title": "Inception", "Year": "2010",
            }):
                with patch("builtins.input", side_effect=["inception", "", ""]):
                    movie_fix.process_list(prompt_mode=True)
        folders = self._get_created_folders()
        self.assertEqual(len(folders), 1)
        self.assertIn("Inception", folders[0])
        self.assertIn("{imdb-tt1375666}", folders[0])

    def test_tmdb_url_recognized_as_series(self):
        """TMDB URL is recognized as a TV show."""
        self.series_dir = tempfile.mkdtemp()
        movie_fix.SERIES_PATH = self.series_dir
        mock_details = {
            "Response": "True", "Title": "Breaking Bad", "Year": "2008",
            "Actors": "Bryan Cranston", "Seasons": 5,
        }
        with patch("movie_fix.get_tmdb_details", return_value=mock_details):
            with patch("builtins.input", side_effect=[
                "https://www.themoviedb.org/tv/1396-breaking-bad", "", ""
            ]):
                movie_fix.process_list(prompt_mode=True)
        folders = [f for f in os.listdir(self.series_dir)
                   if os.path.isdir(os.path.join(self.series_dir, f))]
        self.assertEqual(len(folders), 1)
        self.assertIn("{tmdb-1396}", folders[0])
        shutil.rmtree(self.series_dir, ignore_errors=True)

    def test_series_different_target_path(self):
        """TV shows go to SERIES_PATH, not MOVIE_PATH."""
        self.series_dir = tempfile.mkdtemp()
        movie_fix.SERIES_PATH = self.series_dir
        mock_details = {
            "Response": "True", "Title": "Breaking Bad", "Year": "2008",
            "Actors": "Bryan Cranston", "Seasons": 1,
        }
        with patch("movie_fix.get_tmdb_details", return_value=mock_details):
            with patch("builtins.input", side_effect=[
                "https://www.themoviedb.org/tv/1396-breaking-bad", "", ""
            ]):
                movie_fix.process_list(prompt_mode=True)
        # Movie folder must be empty
        self.assertEqual(len(self._get_created_folders()), 0)
        # Series folder must have content
        series_folders = [f for f in os.listdir(self.series_dir)
                          if os.path.isdir(os.path.join(self.series_dir, f))]
        self.assertEqual(len(series_folders), 1)
        shutil.rmtree(self.series_dir, ignore_errors=True)

    def _create_input_file(self, lines):
        """Helper: create a temporary input file (not in the target directory)."""
        path = os.path.join(self.temp_input_dir, "test_movies.txt")
        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
        return path

    def _get_created_folders(self):
        """Return only directories in the target path (no files)."""
        return [f for f in os.listdir(self.temp_dir)
                if os.path.isdir(os.path.join(self.temp_dir, f))]


if __name__ == "__main__":
    unittest.main(verbosity=2)
