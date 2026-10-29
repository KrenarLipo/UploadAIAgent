# UploadAIAgent
Automatically uploads the mimatest online

**Botty Upload** is a small local website, with a friendly talking robot, that takes the Mimatest reports
from `report_generator` and uploads them to The_New_App platform, kit by kit, with each kit's access code.
It replaces uploading every language by hand on the platform's admin page.

## Setup

```bash
python3 -m venv .venv            # if this fails: sudo apt install python3.12-venv
.venv/bin/pip install -r requirements.txt
```

The input and output folders are set at the top of `report_groups.py`.

## Every day run

```bash
.venv/bin/python webapp/app.py            # then open http://127.0.0.1:8090
```

1. **Connect** once a day: choose *Local test* (`http://localhost:8083/api`) or *Production*
   (`https://yourtestresults.net/api`) and log in with an admin account. The password is not stored; the
   platform's login token is saved in `.platform_session.json` (readable only by you) and is valid for 24 hours.
2. Pick an input folder, tick the kits and press **Upload**.
3. At the end a report shows what was **uploaded**, what was **already online**, what was **rejected** (with the
   platform's reason) and any errors. Every result is also appended to `logs/uploads/<date>.jsonl`.

## How it works

- Each input file `report_generator/input/<folder>/<ID>_<access code>.pdf` is one **kit**.
- Its reports are the `mimatest_<ID>_<locale>.pdf` files anywhere under `report_generator/output/`
  (newest copy wins). Only these PDFs are uploaded, never `.xlsx` or food guides.
- **Upload** sends each kit's reports with its access code (`POST /api/admin/reports/upload`).
  Kits already online are listed before you confirm, and you can skip them. Sending them again is harmless:
  the platform keeps existing reports.
- What is online is remembered per platform in `upload_history.json`, which drives the badges and language chips.
- **Botty** introduces itself and explains the platform on the first visit. Click it in the corner to see the
  tour again. It talks with the browser's built-in speech (🔊/🔇 button to mute).

To test against a local platform, start its database and backend (port 8083) first.

## Daily auto upload

`auto_upload.py` uploads every kit that is not fully online yet, using the login made on the website.
If there is no valid login (none today, or older than 24 hours), it uploads nothing and says so in the log.

```bash
.venv/bin/python auto_upload.py --dry-run     # preview
.venv/bin/python auto_upload.py --limit 3     # upload at most 3 kits (good for a first try)
.venv/bin/python auto_upload.py               # upload everything not yet online
```

To run it every day at 08:00 (if the computer is off then, it runs at the next boot), edit the path in
`deploy/report-upload.service` if needed, then:

```bash
mkdir -p ~/.config/systemd/user
cp deploy/report-upload.* ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now report-upload.timer
systemctl --user list-timers          # shows the next run
```

Each run is logged to `logs/<date>.log`. To stop it: `systemctl --user disable --now report-upload.timer`.
The 08:00 run uses the login from the day before, so connect on the website at least once a day.

## Project layout

| Path | Purpose |
|---|---|
| `webapp/app.py`, `webapp/templates/index.html` | Botty Upload website |
| `report_groups.py` | Finds the kits, their access codes and their reports |
| `platform_client.py` | Login, upload and upload history for The_New_App platform |
| `auto_upload.py`, `run_daily.sh`, `deploy/` | Daily automatic upload |
| `agent.py`, `tools/`, `sample_data/`, `config.example.yaml` | Earlier food guide agent (see below) |

## Food guide agent (earlier experiment)

A command-line agent built on Claude (`claude-opus-5-5`) that reads a data file (CSV, TSV, Excel or JSON),
turns it into a food guide saved as PDF and Word, and can upload files through a website form with a real browser.
It needs an Anthropic API key and is not used by Botty Upload.

```bash
.venv/bin/playwright install chromium
export ANTHROPIC_API_KEY=sk-ant-...
cp config.example.yaml config.yaml   # then fill in the upload site details
.venv/bin/python agent.py "Make a food guide from sample_data/foods.csv, grouped by category"
```

Before uploading, the agent lists the files and asks `Proceed? [y/N]`; `--yes` skips that.
Upload site settings live in `config.yaml` under `upload:`; usernames and passwords come from the environment
variables named there, never from the file.
