# Discord Music Bot

A lightweight Discord music bot written in Python that joins a voice channel and streams audio from YouTube (or any other source supported by `yt-dlp`) when you paste a link.

## Features

- Queue songs with `!play <YouTube URL or search query>`
- View the queue with `!queue`
- Pause/resume and skip tracks
- Automatically reconnects to the requester's voice channel

## Requirements

- Python 3.10 or newer
- `ffmpeg` available on your system `PATH`
- A Discord bot token with the **Message Content Intent** enabled

### Installing ffmpeg

- **Ubuntu / Debian**: `sudo apt-get install ffmpeg`
- **Windows**: download a static build from [https://www.gyan.dev/ffmpeg/builds/](https://www.gyan.dev/ffmpeg/builds/) and add the `bin` folder to your `PATH`
- **macOS**: `brew install ffmpeg`

## Setup

1. (Recommended) Create a virtual environment
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # Windows: .venv\Scripts\activate
   ```
2. Install dependencies
   ```bash
   pip install -r requirements.txt
   ```
3. Copy `.env.example` to `.env` (next to `bot.py`) and paste your bot token:
   ```bash
   cp .env.example .env
   # edit .env and set DISCORD_TOKEN=<your token>
   ```
4. Run the bot
   ```bash
   python bot.py
   ```
## Getting Started

Ensure .env (same folder as bot.py) contains your real token on one line: DISCORD_TOKEN=....
Invite the bot to your Discord server using the OAuth2 URL with scopes bot (and applications.commands if you want slash commands) plus permissions like Connect, Speak, View Channel, Send Messages.
In the Developer Portal’s Bot tab verify MESSAGE CONTENT INTENT stays enabled.
From the project root run python bot.py—the console will show Logged in as … when ready.


## Commands

- `!join` – connect the bot to your voice channel
- `!play <url or search>` – fetch audio and queue it for playback
- `!skip` – skip the currently playing track
- `!pause` / `!resume` – control playback
- `!queue` – show the upcoming tracks
- `!stop` – stop playback and clear the queue
- `!leave` – disconnect from voice and clear the queue



## FAQ

- **ffmpeg was not found**  
  Install ffmpeg and ensure it’s on your `PATH`, or set an absolute path in the environment, e.g. `setx FFMPEG_EXECUTABLE "C:\ffmpeg\bin\ffmpeg.exe"` and restart the terminal before running the bot.

## Notes

- The bot uses `yt-dlp` to extract audio streams. Most direct media links (YouTube, SoundCloud, etc.) are supported.
- Playback requires `ffmpeg`. If you receive an error mentioning `ffmpeg`, verify it is installed and accessible from the command line.
- For production use, consider running the bot inside a process manager (e.g. `systemd`, `pm2`, or Docker) and keeping dependencies pinned to known versions.
