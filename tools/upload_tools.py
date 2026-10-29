"""Tool that uploads files through a website's form using a real browser (Playwright).

The site details live in config.yaml under `upload:`; credentials come from environment
variables so they never reach the model or the config file.
"""

import os
from pathlib import Path

from anthropic import beta_tool

CONFIG: dict = {}
AUTO_CONFIRM = False


def configure(config: dict, auto_confirm: bool) -> None:
    global CONFIG, AUTO_CONFIRM
    CONFIG = config.get("upload", {}) or {}
    AUTO_CONFIRM = auto_confirm


@beta_tool
def upload_files(paths: list[str]) -> str:
    """Upload one or more files (e.g. PDFs or the generated guide) to the configured website.

    The user is asked to confirm before anything is uploaded, unless they started the agent with --yes.

    Args:
        paths: Files to upload.
    """
    if not CONFIG.get("upload_page_url"):
        return "Error: no upload site configured. Fill in the `upload:` section of config.yaml."

    files = [Path(p).expanduser().resolve() for p in paths]
    missing = [str(f) for f in files if not f.is_file()]
    if missing:
        return f"Error: these files do not exist: {', '.join(missing)}"

    if not AUTO_CONFIRM:
        print(f"\nThe agent wants to upload {len(files)} file(s) to {CONFIG['upload_page_url']}:")
        for f in files:
            print(f"  - {f}")
        if input("Proceed? [y/N] ").strip().lower() != "y":
            return "The user declined the upload. Do not retry; tell them what was skipped."

    from playwright.sync_api import sync_playwright

    selectors = CONFIG.get("selectors", {})
    one_at_a_time = CONFIG.get("one_file_per_submit", True)
    results = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=CONFIG.get("headless", False))
        page = browser.new_page()
        try:
            login = CONFIG.get("login")
            if login:
                page.goto(login["url"])
                page.fill(login["username_selector"], os.environ[login["username_env"]])
                page.fill(login["password_selector"], os.environ[login["password_env"]])
                page.click(login["submit_selector"])
                page.wait_for_load_state("networkidle")

            batches = [[f] for f in files] if one_at_a_time else [files]
            for batch in batches:
                page.goto(CONFIG["upload_page_url"])
                page.set_input_files(selectors.get("file_input", "input[type=file]"), [str(f) for f in batch])
                if selectors.get("submit"):
                    page.click(selectors["submit"])
                if selectors.get("success_text"):
                    page.get_by_text(selectors["success_text"]).first.wait_for(timeout=30_000)
                else:
                    page.wait_for_load_state("networkidle")
                results += [f"uploaded: {f.name}" for f in batch]
        except KeyError as e:
            return f"Error: missing config value or environment variable {e}. Uploaded so far: {results}"
        except Exception as e:
            shot = Path("output/upload-error.png")
            shot.parent.mkdir(exist_ok=True)
            page.screenshot(path=str(shot), full_page=True)
            return f"Error during upload: {e}. Screenshot saved to {shot}. Uploaded so far: {results}"
        finally:
            browser.close()
    return "\n".join(results)
