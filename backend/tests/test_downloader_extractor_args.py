import os
from pathlib import Path

import pytest

from backend.app.utils import downloader as dl


def setup_module(module):
    # Ensure no leftover env leaks into tests
    os.environ.pop("DOWNLOAD_YTDLP_EXTRACTOR_ARGS", None)


def test_resolve_extractor_args_defaults(monkeypatch):
    monkeypatch.delenv("DOWNLOAD_YTDLP_EXTRACTOR_ARGS", raising=False)
    monkeypatch.setattr(dl.settings, "download_extractor_args", "youtube:player_client=android", raising=False)
    assert dl._resolve_extractor_args() == "youtube:player_client=android"


def test_resolve_extractor_args_env_override(monkeypatch):
    monkeypatch.setenv("DOWNLOAD_YTDLP_EXTRACTOR_ARGS", "youtube:player_client=web")
    monkeypatch.setattr(dl.settings, "download_extractor_args", None, raising=False)
    assert dl._resolve_extractor_args() == "youtube:player_client=web"


def test_resolve_extractor_args_disable(monkeypatch):
    monkeypatch.setenv("DOWNLOAD_YTDLP_EXTRACTOR_ARGS", "none")
    monkeypatch.setattr(dl.settings, "download_extractor_args", "youtube:player_client=android", raising=False)
    assert dl._resolve_extractor_args() is None


@pytest.mark.parametrize("audio_fmt", ["mp3", "m4a"])
def test_build_command_includes_extractor_args(monkeypatch, audio_fmt):
    monkeypatch.setenv("DOWNLOAD_YTDLP_EXTRACTOR_ARGS", "youtube:player_client=android")
    cmd = dl._build_ytdlp_command(
        ytdlp_path="/opt/venv/bin/yt-dlp",
        ffmpeg_path="/usr/bin/ffmpeg",
    tmp_out=Path("/music/output"),
        url="https://youtu.be/test",
        audio_fmt=audio_fmt,
        allow_embed=True,
        add_metadata=True,
        embed_thumb=True,
        clean_tags=True,
        metadata_args=["-metadata artist=\"Test\"", "-metadata title=\"Song\""],
    )
    assert "--extractor-args" in cmd
    idx = cmd.index("--extractor-args")
    assert cmd[idx + 1] == "youtube:player_client=android"


def test_build_command_includes_extra_args(monkeypatch):
    monkeypatch.setenv("YT_DLP_EXTRA_ARGS", "--force-ipv4 -f bestaudio")
    cmd = dl._build_ytdlp_command(
        ytdlp_path="/opt/venv/bin/yt-dlp",
        ffmpeg_path="/usr/bin/ffmpeg",
        tmp_out=Path("/music/output"),
        url="https://youtu.be/test",
        audio_fmt="mp3",
        allow_embed=True,
        add_metadata=True,
        embed_thumb=True,
        clean_tags=True,
        metadata_args=["-metadata artist=\"Test\"", "-metadata title=\"Song\""],
    )
    assert "--force-ipv4" in cmd
    assert "-f" in cmd
    assert "bestaudio" in cmd


def test_build_command_both_extractor_and_extra_args(monkeypatch):
    monkeypatch.setenv("DOWNLOAD_YTDLP_EXTRACTOR_ARGS", "youtube:player_client=web")
    monkeypatch.setenv("YT_DLP_EXTRA_ARGS", "--ignore-config --no-playlist")
    cmd = dl._build_ytdlp_command(
        ytdlp_path="/opt/venv/bin/yt-dlp",
        ffmpeg_path="/usr/bin/ffmpeg",
        tmp_out=Path("/music/output"),
        url="https://youtu.be/test",
        audio_fmt="m4a",
        allow_embed=True,
        add_metadata=False,
        embed_thumb=False,
        clean_tags=True,
        metadata_args=["-metadata artist=\"Test\""],
    )
    # Both should be present
    assert "--extractor-args" in cmd
    extractor_idx = cmd.index("--extractor-args")
    assert cmd[extractor_idx + 1] == "youtube:player_client=web"
    assert "--ignore-config" in cmd
    assert "--no-playlist" in cmd
