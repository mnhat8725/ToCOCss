# Usage

## Setup checklist

1. **LDPlayer** running, logged into Clash of Clans, on your main village.
2. **ADB local connection enabled**: LDPlayer → Settings → Others →
   *ADB local connection* = on. (Verification: `adb connect 127.0.0.1:5555`)
3. **Python 3.10+** virtual env created and `requirements.txt` installed.
4. **Model present** at `models/best.pt` (or change `config.model_path`).
5. **Buttons calibrated** (below).

## Calibrate buttons (`calibrate.py`)

This is the only per-install / per-game-update setup:

```
python tools/calibrate.py
```

1. The tool connects via ADB and shows a screenshot of your current screen.
2. Navigate the game to each button's screen as you go, and press **Recapture**
   to grab a fresh screenshot of whatever is on the emulator now — the current
   row/selection is kept, so you don't restart the tool between screens (the
   status line shows `Recaptured HH:MM:SS`).
3. Click the button described at the top, in order:
   - **Attack button** (village screen, bottom-right cluster)
   - **Find Match** (green button)
   - **Next base** (on the search screen)
   - **Attack** (confirm match)
   - **Goblin troop** (bottom troop bar)
   - **Surrender button** (in battle, bottom-left)
   - **Surrender confirm** (red button on the quit dialog)
   - **Return Home** (post-battle screen)
   - **Retry spot 1/2/3** (the three taps made when a resource scan fails)
4. `Undo` / `Clear selected` / `Clear all` are available if you mis-click.
5. Press **Save** — this writes `controls` to `settings.json`.

Recalibrate after a game update that moves button positions; there is no model
retraining involved.

To re-fix just **one** button later (e.g. a single spot moved): click its row
in the progress list on the left, navigate the game to that button's screen and
press **Recapture**, click its new spot on the screenshot, then press **Save** —
the other buttons keep their saved positions. `Undo` reverses the last click,
and `Clear selected` unsets only the currently selected button.

> Note: if you calibrated with an older version of this project, your
> `settings.json` will be missing buttons that were once YOLO-detected
> (`nxt_btn`, `s_goblin`, `surr`). The bot refuses to farm
> ("Run tools/calibrate.py first") until you calibrate once more with the current
> version.

> Tip: calibrate while on the exact screens the bot will click, i.e. have the
> main village up (for Attack + Find Match), then the attack screen (Attack),
> then in a battle (Surrender), then the victory screen (Return Home). Press
> **Recapture** between screens so each click lands on the right screenshot —
> the bot uses the same relative spots every time, so a single calibration on
> your normal screen is usually enough for the Attack/Find/Attack buttons, but
> being on the actual screen for each click makes it unambiguous.

## Run the farm

Easiest: double-click **`run.bat`**. On first run it offers to create the
`.venv` and install the dependencies (a few GB, several minutes), then verifies
they import, warns if `models\best.pt` is missing, and starts `main.py`. Later
runs just verify the environment and launch.

Manual:

```
.venv\Scripts\Activate.ps1
python main.py
```

On startup, `main.py` connects via ADB to the configured port (default
`127.0.0.1:5555`, first LDPlayer instance) and shows an error dialog if the
connection fails. There is no window picking.

## GUI

| Control | Description |
|---------|-------------|
| Thresholds (Gold / Elixir / Dark Elixir) | Minimum resources on a base before attacking |
| Goals (Gold / Elixir / Dark Elixir) | Total farmed before the bot stops and alerts you |
| **Start** | Begin farming (blocked with an alert if buttons are uncalibrated) |
| **Stop** | Graceful stop against the current phase |
| Log viewer | Live messages from the worker |
| **F12** | Emergency stop (global hotkey) |

The window stays visible while farming — the **Stop Farm (F12)** button remains
clickable for the whole run, so you always have an on-screen way to stop. You can
also minimize it yourself; input and capture use ADB, not the desktop, so the
bot keeps running either way. The status line shows
`running - press F12 or Stop Farm` while active.

## What the upgraded bot does

See [the current upgrade guide](../progress/UPGRADE_GUIDE_VI.md) for all new controls.

- Loads YOLO, OCR and Smart Farm before navigation.
- Verifies home/menu/preview/battle/results with template evidence across frames.
- Uses Smart Farm for full-resource buildings and the existing detector + OCR for numbers.
- Requires stable readable threshold resources before attacking.
- Executes the existing goblin row strategy through validated, cancellable actions.
- Limits deployment by `attack.max_waves` (3) and `attack.time_limit` (30 seconds).
- Reads post-battle loot using two agreeing observations rather than the maximum OCR value.
- Stops on unknown screen states and records screenshots and structured events.

Detection loss does not measure destruction or loot. `attack.drain_ratio` is
no longer used. Stop is checked between individual taps, not only between waves.

## Tuning timings

`settings.json` accepts `waits`, `attack` and `vision` settings. Example:

```json
{
  "waits": {"surr_conf": 1.0, "return_home": 1.5},
  "attack": {"time_limit": 30, "max_waves": 3},
  "vision": {"state_timeout": 12, "template_threshold": 0.85}
}
```

Post-battle polling uses `scan_post_interval` (0.3 seconds) and
`scan_post_timeout` (12 seconds). A real zero can be confirmed; an unreadable
resource is not a confirmed zero. At timeout only confirmed values are counted.

Each tap line in the log shows the wait that followed it, e.g.
`tap surr_conf at (987, 603) [0.617, 0.670] wait 1.0s`. The full per-step
timings (and the scan graces) are written to `logs/bot.log` at DEBUG level.
See `docs/CONFIGURATION.md` for the full key list and defaults.

## Getting notified (optional)

The bot can push a phone notification through [ntfy.sh](https://ntfy.sh) so you
know if something fails while you are away. It is **off by default**.

1. Install the **ntfy** app (iOS/Android) and subscribe to a topic name you
   invent, e.g. `coc-farm-8f3a91d2`. Pick something long and random — anyone who
   knows the name can read the topic on the public server.
2. In `settings.json`, enable it with the **same** topic:

   ```json
   "notifications": { "enabled": true, "ntfy_topic": "coc-farm-8f3a91d2" }
   ```

3. Start the bot. You will get a push when:
   - the farm loop hits an **error** (the emulator screen is attached),
   - a session **completes** its goals (current totals + average drain attached),
   - the bot **refuses to start** because buttons are not calibrated.

Errors and completion attach a screenshot saved to `logs/error_<timestamp>.jpg`
(downscaled and JPEG-compressed to fit ntfy.sh's 2 MB attachment limit; if an
upload still fails, the alert is sent as text). An ADB connection failure at
startup is text-only (there is no capture to attach). Notifications are
best-effort: a network problem never stops the farm loop, and failures are only
written to `logs/bot.log`. See `docs/CONFIGURATION.md` for the full key list.

## Useful commands

```bash
python tools/calibrate.py         # (re)calibrate the 11 buttons
python tools/pinpoint.py 986 603          # crosshair over guest-pixel (986, 603)
python tools/pinpoint.py --button surr_conf   # crosshair over a calibrated button's spot
python main.py              # run the GUI bot
adb connect 127.0.0.1:5555  # verify the first LDPlayer instance is reachable
adb -s 127.0.0.1:5555 shell wm size   # print guest resolution
```