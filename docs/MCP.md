# Use MediaHarvest from an AI assistant (MCP)

MediaHarvest has an MCP server built in. MCP (Model Context Protocol) is the
standard way AI assistants call outside tools. Claude, Cursor, VS Code and
many other assistants speak it.

Once it's connected, you ask in plain words and the assistant does the rest:

- "Summarise this talk for me: https://youtu.be/..." The assistant reads the
  video's transcript, then summarises it.
- "Turn this cooking video into a recipe with the amounts."
- "Save the audio of this video as MP3."
- "Is there a 4K version of this video? How big is it?"
- "Download these three lectures in 720p and tell me when they're done."

The server is part of MediaHarvest and starts with it, at
**http://localhost:8081/mcp**. There is nothing extra to install or run on the
MediaHarvest side.

## Connect your assistant

Start MediaHarvest first (the desktop shortcut, or `docker compose up -d`).

**Claude Code:**

```bash
claude mcp add --transport http mediaharvest http://localhost:8081/mcp
```

**VS Code** (GitHub Copilot agent mode). Add to `.vscode/mcp.json` in your
project, or run *MCP: Add Server* from the command palette:

```json
{
  "servers": {
    "mediaharvest": { "type": "http", "url": "http://localhost:8081/mcp" }
  }
}
```

**Cursor.** Add to `~/.cursor/mcp.json`:

```json
{
  "mcpServers": {
    "mediaharvest": { "url": "http://localhost:8081/mcp" }
  }
}
```

**Claude Desktop** starts its tools as programs on your computer, so it
reaches MediaHarvest through the small `mcp-remote` bridge. This needs
[Node.js](https://nodejs.org). In Claude Desktop open *Settings → Developer →
Edit Config* and add:

```json
{
  "mcpServers": {
    "mediaharvest": {
      "command": "npx",
      "args": ["-y", "mcp-remote@0.15.2", "http://localhost:8081/mcp"]
    }
  }
}
```

Then restart Claude Desktop.

**Any other assistant:** give it the address `http://localhost:8081/mcp` as a
"Streamable HTTP" server. If you changed the port or set `URL_PREFIX`, the
address changes the same way as the web page's.

To check it works, ask: *"What MediaHarvest tools do you have?"*

## The tools

| Tool | What it does | Changes anything |
|---|---|---|
| `get_transcript` | The words spoken in a video, as plain text, from its subtitles or the site's automatic captions. Pick a language with a code such as `en`, `hi` or `de`. A long transcript comes in parts of 30,000 characters, and the assistant asks for the next part by itself. | No. Nothing is saved. |
| `preview` | The title, uploader, length, whether it's live, and every format on offer with its size. | No |
| `download` | Saves the video, its audio, its subtitles or its thumbnail, in the quality and format you ask for. | Adds a download |
| `list_downloads` | What is downloading now with its progress, and the 50 newest finished files. | No |
| `cancel_download` | Stops a download that is queued or running. Finished files stay. | Stops a download |

`download` takes the same choices as the web page:

| kind | quality | format |
|---|---|---|
| `video` | `best`, `worst`, or a height such as `1080` or `720` | `any`, `mp4` or `ios` |
| `audio` | `best`, or a bitrate such as `320`, `192` or `128` | `auto`, `m4a`, `mp3`, `opus`, `wav` or `flac` |
| `captions` | | `srt`, `txt` or `vtt` |
| `thumbnail` | | |

Leave format empty for the usual choice. **folder** is a folder inside your
download folder, or empty. Assistants read all this from the server by
themselves, so you don't have to spell it out.

## Where the files go

Into the same download folder as downloads from the web page, and they show
in its **Completed** tab too. `list_downloads` gives each finished file a
`file_url`. Put `http://localhost:8081` in front of it to fetch the file.

## Safety

- **The same checks as the web page.** Links to addresses on your own network
  are refused, and the per-download yt-dlp options (which can run commands)
  can't be reached through MCP.
- **Web pages can't use it.** A request that comes from a page in a browser is
  refused, unless that page's address is listed in `CORS_ALLOWED_ORIGINS`. So
  a site you visit can't drive MediaHarvest behind your back. Assistants
  aren't web pages, so they connect normally.
- **No login, like the web page.** Anything that can reach the port can use it.
  By default that is only this computer. Before you open it to your network,
  put a reverse proxy with a login in front (see the README).
- **A transcript is the video's own words.** Someone could write instructions
  into a video's captions. A good assistant treats the transcript as text to
  read, not as orders to follow.

## For developers

- Streamable HTTP, stateless, with JSON replies. Each request stands alone,
  with no session to keep.
- Protocol version 2026-07-28, and the 2025 versions for older clients
  (2025-11-25, 2025-06-18, 2025-03-26).
- Built with the official [MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk),
  served from the same aiohttp server and port as the web page.
- The tools call the same code as the web page. Code: `app/mcp_server.py`.
  Tests: `app/tests/test_mcp_server.py`.
- Listed in the official [MCP Registry](https://registry.modelcontextprotocol.io/v0/servers?search=io.github.MohanVishe/mediaharvest)
  as `io.github.MohanVishe/mediaharvest`, from `server.json`. Every `v*` tag
  publishes the new version there.
- Try it with the MCP Inspector:

  ```bash
  npx @modelcontextprotocol/inspector@2.13.0 --cli http://localhost:8081/mcp --transport http --method tools/list
  ```
