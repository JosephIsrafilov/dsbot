import asyncio
import logging
import os
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import discord
import yt_dlp
from discord.ext import commands
from dotenv import load_dotenv


logging.basicConfig(level=logging.INFO)

PROJECT_ROOT = Path(__file__).resolve().parent
load_dotenv(PROJECT_ROOT / ".env")

YTDL_OPTIONS = {
    "format": "bestaudio/best",
    "noplaylist": True,
    "quiet": True,
    "default_search": "ytsearch",
    "source_address": "0.0.0.0",
}

FFMPEG_EXECUTABLE = os.getenv("FFMPEG_EXECUTABLE", "ffmpeg")

FFMPEG_OPTIONS = {
    "before_options": "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5",
    "options": "-vn",
}

ytdl = yt_dlp.YoutubeDL(YTDL_OPTIONS)


def format_duration(duration: Optional[int], is_live: bool) -> str:
    if is_live:
        return "Live"
    if duration is None:
        return "N/A"
    minutes, seconds = divmod(duration, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours:d}:{minutes:02d}:{seconds:02d}"
    return f"{minutes:d}:{seconds:02d}"


@dataclass
class MusicTrack:
    source: discord.AudioSource
    title: str
    webpage_url: str
    duration: str
    requester: discord.Member


class MusicPlayer:
    def __init__(self, bot: commands.Bot, guild_id: int):
        self.bot = bot
        self.guild_id = guild_id
        self.queue: asyncio.Queue[MusicTrack] = asyncio.Queue()
        self.pending: deque[MusicTrack] = deque()
        self.current: Optional[MusicTrack] = None
        self.voice_client: Optional[discord.VoiceClient] = None
        self.next = asyncio.Event()
        self.player_task = bot.loop.create_task(self.player_loop())

    async def player_loop(self) -> None:
        await self.bot.wait_until_ready()
        while not self.bot.is_closed():
            self.next.clear()
            try:
                track = await self.queue.get()
            except asyncio.CancelledError:
                break

            if self.pending:
                self.pending.popleft()

            self.current = track
            voice = self.voice_client

            if voice is None or not voice.is_connected():
                logging.warning("Voice client missing for guild %s; dropping track '%s'", self.guild_id, track.title)
                track.source.cleanup()
                self.current = None
                continue

            def after_playback(error: Optional[Exception]) -> None:
                if error:
                    logging.exception("Playback error: %s", error)
                track.source.cleanup()
                self.bot.loop.call_soon_threadsafe(self.next.set)

            voice.play(track.source, after=after_playback)
            await self.next.wait()
            self.current = None

    async def enqueue(self, track: MusicTrack) -> None:
        self.pending.append(track)
        await self.queue.put(track)

    def clear(self) -> None:
        while not self.queue.empty():
            try:
                track = self.queue.get_nowait()
            except asyncio.QueueEmpty:
                break
            track.source.cleanup()
        self.pending.clear()

    def teardown(self) -> None:
        self.clear()
        if self.player_task:
            self.player_task.cancel()


class MusicBot(commands.Bot):
    def __init__(self) -> None:
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(command_prefix="!", intents=intents)
        self.players: dict[int, MusicPlayer] = {}

    def get_player(self, guild: discord.Guild) -> MusicPlayer:
        player = self.players.get(guild.id)
        if player is None:
            player = MusicPlayer(self, guild.id)
            self.players[guild.id] = player
        return player

    async def on_ready(self) -> None:
        logging.info("Logged in as %s (ID: %s)", self.user, self.user.id if self.user else "unknown")


bot = MusicBot()


async def create_track(ctx: commands.Context, search: str) -> MusicTrack:
    loop = asyncio.get_running_loop()

    def extract() -> dict:
        return ytdl.extract_info(search, download=False)

    data = await loop.run_in_executor(None, extract)

    if "entries" in data and data["entries"]:
        data = data["entries"][0]

    stream_url = data["url"]
    title = data.get("title", "Unknown title")
    webpage_url = data.get("webpage_url", data.get("original_url", search))
    is_live = data.get("is_live", False)
    duration = format_duration(data.get("duration"), is_live)

    audio_source = discord.FFmpegPCMAudio(stream_url, executable=FFMPEG_EXECUTABLE, **FFMPEG_OPTIONS)
    return MusicTrack(
        source=audio_source,
        title=title,
        webpage_url=webpage_url,
        duration=duration,
        requester=ctx.author,
    )


async def ensure_voice(ctx: commands.Context) -> None:
    if ctx.author.voice is None or ctx.author.voice.channel is None:
        raise commands.CommandError("You must be connected to a voice channel to use this command.")

    destination = ctx.author.voice.channel
    voice_client = ctx.voice_client

    if voice_client is None:
        await destination.connect(timeout=10)
    elif voice_client.channel != destination:
        await voice_client.move_to(destination)

    player = bot.get_player(ctx.guild)
    player.voice_client = ctx.voice_client


@bot.command(name="join")
async def join(ctx: commands.Context) -> None:
    try:
        await ensure_voice(ctx)
    except commands.CommandError as exc:
        await ctx.send(str(exc))
        return

    await ctx.send(f"Connected to `{ctx.voice_client.channel}`.")


@bot.command(name="play")
async def play(ctx: commands.Context, *, query: str) -> None:
    try:
        await ensure_voice(ctx)
    except commands.CommandError as exc:
        await ctx.send(str(exc))
        return

    player = bot.get_player(ctx.guild)

    try:
        track = await create_track(ctx, query)
    except yt_dlp.utils.DownloadError:
        await ctx.send("Could not retrieve audio from that link.")
        return
    except Exception as exc:  # pylint: disable=broad-except
        logging.exception("Unexpected error while retrieving audio: %s", exc)
        await ctx.send("Something went wrong while processing your request.")
        return

    await player.enqueue(track)

    embed = discord.Embed(title="Queued", description=f"[{track.title}]({track.webpage_url})", color=discord.Color.blurple())
    embed.add_field(name="Requested by", value=track.requester.mention)
    embed.add_field(name="Duration", value=track.duration)
    await ctx.send(embed=embed)


@bot.command(name="skip")
async def skip(ctx: commands.Context) -> None:
    voice_client = ctx.voice_client
    if voice_client is None or not voice_client.is_playing():
        await ctx.send("Nothing is playing right now.")
        return

    voice_client.stop()
    await ctx.send("Skipped the current track.")


@bot.command(name="pause")
async def pause(ctx: commands.Context) -> None:
    voice_client = ctx.voice_client
    if voice_client is None or not voice_client.is_playing():
        await ctx.send("Nothing is playing right now.")
        return
    voice_client.pause()
    await ctx.send("Paused playback.")


@bot.command(name="resume")
async def resume(ctx: commands.Context) -> None:
    voice_client = ctx.voice_client
    if voice_client is None or not voice_client.is_paused():
        await ctx.send("Playback is not paused.")
        return
    voice_client.resume()
    await ctx.send("Resumed playback.")


@bot.command(name="stop")
async def stop(ctx: commands.Context) -> None:
    voice_client = ctx.voice_client
    if voice_client is None:
        await ctx.send("I'm not connected to a voice channel.")
        return

    player = bot.get_player(ctx.guild)
    player.clear()
    voice_client.stop()
    await ctx.send("Cleared the queue and stopped playback.")


@bot.command(name="queue")
async def show_queue(ctx: commands.Context) -> None:
    player = bot.get_player(ctx.guild)
    if player.current is None and not player.pending:
        await ctx.send("The queue is empty.")
        return

    embed = discord.Embed(title="Music Queue", color=discord.Color.green())

    if player.current:
        embed.add_field(
            name="Now playing",
            value=f"[{player.current.title}]({player.current.webpage_url}) • {player.current.duration}\nRequested by {player.current.requester.mention}",
            inline=False,
        )

    if player.pending:
        upcoming_lines = []
        for index, track in enumerate(player.pending, start=1):
            upcoming_lines.append(f"{index}. [{track.title}]({track.webpage_url}) • {track.duration} — requested by {track.requester.display_name}")
        embed.add_field(name="Up next", value="\n".join(upcoming_lines), inline=False)

    await ctx.send(embed=embed)


@bot.command(name="leave")
async def leave(ctx: commands.Context) -> None:
    voice_client = ctx.voice_client
    if voice_client is None:
        await ctx.send("I'm not connected to a voice channel.")
        return

    player = bot.get_player(ctx.guild)
    player.clear()
    await voice_client.disconnect()
    await ctx.send("Disconnected and cleared the queue.")


def main() -> None:
    token = os.getenv("DISCORD_TOKEN")
    if not token:
        raise RuntimeError("Set the DISCORD_TOKEN environment variable before running the bot.")
    bot.run(token)


if __name__ == "__main__":
    main()
