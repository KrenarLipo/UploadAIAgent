"""Upload every kit that is not fully online yet to The_New_App platform, e.g. once a day from a timer.

Uses the login saved when you connect on the website (valid 24 hours). If there is none, nothing is
uploaded and the log says to connect first.

For each kit (input PDF -> its mimatest_<ID>_<locale>.pdf reports, see report_groups.py):
  - reports not online yet   -> uploaded with the kit's access code
  - all reports online       -> left alone
  - no reports yet           -> waits; picked up on a later run

Usage:
    .venv/bin/python auto_upload.py              # upload
    .venv/bin/python auto_upload.py --dry-run    # only show what would be uploaded
"""

import argparse
import sys
from datetime import datetime

import platform_client as pc
import report_groups as rg


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dry-run", action="store_true", help="Show what would be uploaded without sending anything")
    parser.add_argument("--limit", type=int, default=0, help="Upload at most this many kits (0 = no limit), e.g. for a first test")
    args = parser.parse_args()

    print(f"=== {datetime.now():%Y-%m-%d %H:%M:%S} Botty Upload: daily run{' (dry run)' if args.dry_run else ''}")
    session = pc.load_session()
    if not session:
        print("Not connected (no login, or it is older than 24 hours). "
              "Open http://localhost:8090 and connect to the platform. Nothing was uploaded.")
        return 2
    print(f"Platform: {pc.PLATFORMS[session['platform']]['label']} ({session['api']}) as {session['username']}, "
          f"login valid until {session['expires_at']}")

    to_send, waiting, online = [], [], 0
    seen: set[str] = set()
    history = pc.load_history(session["platform"])
    for folder in rg.input_folders():
        for g in rg.build_groups(folder, history):
            if g["id"] in seen:  # same kit in several input folders: handle it once
                continue
            seen.add(g["id"])
            if not g["files"]:
                waiting.append(g["id"])
            elif g["status"] == "online":
                online += 1
            else:
                to_send.append(g)
    left = to_send[args.limit:] if args.limit else []
    to_send = to_send[:args.limit] if args.limit else to_send

    uploaded, already, rejected, errors, not_sent = [], [], [], [], []
    for i, g in enumerate(to_send):
        if args.dry_run:
            uploaded.append(f"{g['id']}: {', '.join(f['locale'] for f in g['files'] if f['state'] != 'online')}")
            continue
        try:
            result = pc.upload_kit(session, g)
        except pc.NotConnected as e:  # login expired: the remaining kits would fail the same way
            errors.append(f"{g['id']}: {e}")
            not_sent = [k["id"] for k in to_send[i + 1:]]
            break
        except pc.PlatformError as e:
            errors.append(f"{g['id']}: {e}")
            continue
        outcomes = pc.record_result(session["platform"], g["id"], result)
        for state, bucket in (("inserted", uploaded), ("skipped", already)):
            names = [n for n, o in outcomes.items() if o["result"] == state]
            if names:
                bucket.append(f"{g['id']}: {', '.join(rg.locale_of(n) for n in names)}")
        rejected += [f"{g['id']}: {n} ({o['reason']})" for n, o in outcomes.items() if o["result"] == "rejected"]

    sections = (("Uploaded" + (" (would be)" if args.dry_run else ""), uploaded),
                ("Already online, not uploaded", already), ("Rejected by the platform", rejected),
                ("Errors", errors), ("Not sent (login expired)", not_sent),
                (f"Left for a later run (--limit {args.limit})", [g["id"] for g in left]),
                ("Waiting for reports", waiting))
    for title, items in sections:
        if items:
            print(f"{title} ({len(items)}):")
            print("\n".join(f"  {i}" for i in items))
    print(f"Summary: {len(uploaded)} kit(s) uploaded, {len(already)} already online, {len(rejected)} file(s) rejected, "
          f"{len(errors)} error(s), {online} kit(s) were fully online before, {len(waiting)} waiting for reports")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
