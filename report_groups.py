"""Group report_generator files into kits. Shared by the web app and auto_upload.py.

Input files are named   <ID>_<access code>.pdf            e.g. KIT00012345_ABCD1234EFGH5678.pdf
Output reports are      mimatest_<ID>_<locale>.pdf        e.g. mimatest_KIT00012345_de-DE.pdf

Each input file is one kit. Its reports are the output PDFs named mimatest_<ID>_<locale>.pdf, found
anywhere under the output folder; they are uploaded to the platform with the kit's access code.
Other output files (.xlsx, Darmbulanz food guides) are never uploaded.
"""

from pathlib import Path

SRC = Path("/home/cts/Git/src")
INPUT_DIR = SRC / "report_generator" / "input"
OUTPUT_DIR = SRC / "report_generator" / "output"


def name_parts(path: Path) -> list[str]:
    return path.stem.split("_")


def locale_of(report_name: str) -> str:
    """"mimatest_KIT00012345_de-DE.pdf" -> "de-DE"."""
    return name_parts(Path(report_name))[-1]


def input_folders() -> list[str]:
    """Input folder choices: "." is the input root itself, the rest are its subfolders."""
    subs = sorted(p.name for p in INPUT_DIR.iterdir() if p.is_dir())
    return ["."] + subs


def index_reports() -> dict[str, dict[str, Path]]:
    """Map kit ID -> {file name: path} for every mimatest_<ID>_<locale>.pdf under the output folder.

    When the same file name exists in several output folders, the newest copy wins.
    """
    newest: dict[str, Path] = {}
    for f in OUTPUT_DIR.rglob("mimatest_*"):
        if not f.is_file() or f.suffix.lower() != ".pdf" or len(name_parts(f)) != 3:
            continue
        if f.name not in newest or f.stat().st_mtime > newest[f.name].stat().st_mtime:
            newest[f.name] = f
    index: dict[str, dict[str, Path]] = {}
    for name, f in newest.items():
        index.setdefault(name_parts(f)[1], {})[name] = f
    return index


def kit_status(files: list[dict]) -> str:
    """"online": every report is on the platform; "partial": some are; "new": none are (or no reports)."""
    online = sum(f["state"] == "online" for f in files)
    if files and online == len(files):
        return "online"
    return "partial" if online else "new"


def build_groups(folder: str, history: dict) -> list[dict]:
    """Kits in one input folder, with each report's state taken from the platform upload history."""
    root = (INPUT_DIR / folder).resolve()
    if root != INPUT_DIR.resolve() and root.parent != INPUT_DIR.resolve():
        raise ValueError(f"Unknown input folder: {folder}")
    reports = index_reports()
    groups = []
    for f in sorted(root.glob("*.pdf")):
        parts = name_parts(f)
        if len(parts) != 2:
            continue
        kit_id, access_code = parts
        files = []
        for name, path in sorted(reports.get(kit_id, {}).items()):
            h = history.get(name, {})
            state = {"inserted": "online", "skipped": "online", "rejected": "rejected"}.get(h.get("result"), "new")
            files.append({
                "name": name,
                "locale": locale_of(name),
                "folder": str(path.parent.relative_to(OUTPUT_DIR)),
                "path": str(path),
                "state": state,
                "reason": h.get("reason"),
                "at": h.get("at"),
            })
        groups.append({
            "id": kit_id,
            "access_code": access_code,
            "folder": folder,
            "input": str(f),
            "files": files,
            "status": kit_status(files),
        })
    return groups
