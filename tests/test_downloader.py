import tempfile
import unittest
from pathlib import Path

import yt_dlp

from t_music.downloader import (ARCHIVE_FILENAME, Downloader, DownloadOptions,
                                DownloadSummary, _Logger)

SONG = {"id": "abc123xyz00", "title": "My Song", "ext": "webm",
        "extractor": "youtube", "extractor_key": "Youtube"}


class SkipLogicTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.out = Path(self.tmp.name)
        self.logs: list[str] = []
        self.dl = Downloader(DownloadOptions(output_dir=self.out), log=self.logs.append)
        self.summary = DownloadSummary()
        self.params = self.dl._build_params(self.summary)
        self.ydl = yt_dlp.YoutubeDL(self.params)
        self.dl._filter_holder["ydl"] = self.ydl
        self.filter = self.params["match_filter"]

    def tearDown(self):
        self.ydl.close()
        self.tmp.cleanup()

    def test_single_song_path_has_no_subfolder(self):
        self.assertEqual(self.dl.expected_path(self.ydl, dict(SONG)), self.out / "My Song.mp3")

    def test_playlist_song_goes_into_playlist_folder(self):
        info = dict(SONG, playlist_title="Road Trip", playlist="Road Trip")
        self.dl.use_template(self.ydl, is_playlist=True)
        self.assertEqual(self.dl.expected_path(self.ydl, info),
                         self.out / "Road Trip" / "My Song.mp3")

    def test_playlist_without_subfolder_option(self):
        self.dl.options.playlist_subfolder = False
        self.dl.use_template(self.ydl, is_playlist=True)
        info = dict(SONG, playlist_title="Road Trip")
        self.assertEqual(self.dl.expected_path(self.ydl, info), self.out / "My Song.mp3")

    def test_new_song_is_not_skipped(self):
        self.assertIsNone(self.filter(dict(SONG), incomplete=False))
        self.assertEqual(self.summary.skipped, [])

    def test_incomplete_info_never_skips(self):
        (self.out / "My Song.mp3").touch()
        self.assertIsNone(self.filter(dict(SONG), incomplete=True))

    def test_existing_file_is_skipped_and_added_to_archive(self):
        (self.out / "My Song.mp3").touch()
        reason = self.filter(dict(SONG), incomplete=False)
        self.assertIn("already exists", reason)
        self.assertEqual(self.summary.skipped, ["My Song"])
        archive = (self.out / ARCHIVE_FILENAME).read_text()
        self.assertIn("youtube abc123xyz00", archive)
        self.assertTrue(self.ydl.in_download_archive(dict(SONG)))

    def test_file_in_other_format_does_not_count(self):
        (self.out / "My Song.m4a").touch()
        self.assertIsNone(self.filter(dict(SONG), incomplete=False))

    def test_archive_messages_are_counted_as_skipped(self):
        summary = DownloadSummary()
        logs: list[str] = []
        _Logger(logs.append, summary).debug(
            "[download] My Song: has already been recorded in the archive")
        self.assertEqual(summary.skipped, ["My Song"])
        self.assertEqual(logs, ["Skipping (already downloaded): My Song"])


class OptionsTests(unittest.TestCase):
    def test_video_mode_merges_to_mp4_without_audio_extraction(self):
        dl = Downloader(DownloadOptions(output_dir=Path("."), audio_format="mp4 (video)"))
        params = dl._build_params(DownloadSummary())
        self.assertEqual(params["merge_output_format"], "mp4")
        self.assertNotIn("FFmpegExtractAudio", [p["key"] for p in params["postprocessors"]])

    def test_wav_skips_cover_art(self):
        dl = Downloader(DownloadOptions(output_dir=Path("."), audio_format="wav"))
        params = dl._build_params(DownloadSummary())
        self.assertFalse(params["writethumbnail"])


if __name__ == "__main__":
    unittest.main()
