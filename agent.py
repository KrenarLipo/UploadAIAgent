"""Food guide agent: reads a data file, builds a PDF + DOCX food guide, and uploads files to a website.

Usage:
    python agent.py "Make a food guide from data/foods.csv, then upload it and the PDFs in inbox/"
    python agent.py --yes "..."        # skip the upload confirmation prompt
"""

import argparse
import sys
from pathlib import Path

import anthropic
import yaml

from tools import ALL_TOOLS, configure_upload

MODEL = "claude-opus-5-5"

SYSTEM_PROMPT = """You are an assistant that takes over repetitive office work for the user:
turning structured food data into a clear, well-organized food guide, and uploading files to a website.

How to work:
- Read the data file first and base the guide only on what is in it. Do not invent foods, nutrients or numbers.
  If a value the guide needs is missing, leave it out and mention it in your final summary.
- Organize the guide for a reader, not as a raw dump: group items into sensible sections
  (e.g. by category or meal), and use tables for numeric data with readable column names and units.
- Generate the guide with generate_food_guide; it produces both a PDF and a DOCX.
- Only call upload_files when the user's request asks for an upload. Upload exactly the files they asked for.
- Finish with a short summary: what you created (with paths), what was uploaded, and anything that needs attention."""


def load_config(path: Path) -> dict:
    if not path.is_file():
        return {}
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("task", help="What you want the agent to do, in plain language.")
    parser.add_argument("--config", default="config.yaml", type=Path, help="Path to config.yaml (default: ./config.yaml)")
    parser.add_argument("--yes", action="store_true", help="Upload without asking for confirmation.")
    args = parser.parse_args()

    config = load_config(args.config)
    configure_upload(config, auto_confirm=args.yes)

    client = anthropic.Anthropic()
    runner = client.beta.messages.tool_runner(
        model=config.get("model", MODEL),
        max_tokens=16000,
        system=SYSTEM_PROMPT,
        tools=ALL_TOOLS,
        thinking={"type": "adaptive"},
        output_config={"effort": config.get("effort", "high")},
        # If Claude declines a request, re-run it server-side on Anthropic's recommended fallback model.
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
        messages=[{"role": "user", "content": args.task}],
        max_iterations=30,
    )

    final = None
    try:
        for message in runner:
            final = message
            for block in message.content:
                if block.type == "text" and block.text.strip():
                    print(f"\n{block.text}")
                elif block.type == "tool_use":
                    print(f"  -> {block.name}")
                elif block.type == "fallback":
                    print(f"  ({block.from_.model} declined; continued on {block.to.model})")
    except (anthropic.AuthenticationError, TypeError) as e:
        if isinstance(e, TypeError) and "authentication" not in str(e):
            raise
        print("Not authenticated: set ANTHROPIC_API_KEY (or run `ant auth login`).", file=sys.stderr)
        return 1

    if final is None:
        return 1
    if final.stop_reason == "refusal":
        print("\nThe model declined this request.", file=sys.stderr)
        return 1
    if final.stop_reason == "max_tokens":
        print("\nStopped: the response hit the token limit.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
