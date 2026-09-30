"""Extract notified ingredients and their official function text from the MFDS notice ZIP.

The ZIP is the full text of 「건강기능식품의 기준 및 규격」 as published by MFDS. Exactly one hwpx in
it (the standards part) must contain "(1) 기능성 내용"; each item number (e.g. 2-16) and name is
paired with the text between "(1) 기능성 내용" and the next numbered requirement. `effects` records
which official-function-v2 phrases appear in that text; `mentioned_effects` uses the broad keywords
so that differently worded carriers (e.g. "배변활동을 원활히") are not missed. Neither is product
attribution.
"""

import argparse
import hashlib
import html
import io
import json
import re
import zipfile
from collections.abc import Sequence
from pathlib import Path

from claimledger.official_v2 import EffectKey, effect_mentioned, official_effect_keys

REFERENCE_VERSION = "notice-functions-v1"
_TEXT = re.compile(r"<hp:t(?:\s[^>]*)?>(.*?)</hp:t>", re.DOTALL)
_PARAGRAPH = re.compile(r"<hp:p[\s>].*?</hp:p>", re.DOTALL)
_SECTION = re.compile(r"Contents/section(\d+)\.xml")
_HEADING = re.compile(r"^(\d{1,2}-\d{1,3})(?:\s+(\S.{0,60}))?$")
_FUNCTION_START = re.compile(r"^\(1\)\s*기능성\s*내용\s*:?\s*")
_FUNCTION_END = re.compile(r"^\(\d\)|^\d\)|^\d{1,2}-\d{1,3}(?:\s|$)")


class NoticeError(ValueError):
    pass


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Extract notified ingredient function texts")
    parser.add_argument("--notice-zip", type=Path, required=True)
    parser.add_argument("--source-url", required=True)
    parser.add_argument("--notice", required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args(argv)


def _paragraph_text(paragraph: str) -> str:
    text = "".join(_TEXT.findall(paragraph))
    return html.unescape(re.sub(r"<[^>]+>", "", text)).strip()


def notice_lines(zip_path: Path) -> list[str]:
    documents: list[list[str]] = []
    with zipfile.ZipFile(zip_path) as outer:
        for name in sorted(outer.namelist()):
            if not name.endswith(".hwpx"):
                continue
            with zipfile.ZipFile(io.BytesIO(outer.read(name))) as inner:
                sections = sorted(
                    (int(match.group(1)), entry)
                    for entry in inner.namelist()
                    if (match := _SECTION.fullmatch(entry))
                )
                lines = [
                    text
                    for _, entry in sections
                    for paragraph in _PARAGRAPH.findall(inner.read(entry).decode("utf-8"))
                    if (text := _paragraph_text(paragraph))
                ]
            if any(_FUNCTION_START.match(line) for line in lines):
                documents.append(lines)
    if len(documents) != 1:
        raise NoticeError(f"expected one standards document with 기능성 내용, found {len(documents)}")
    return documents[0]


def parse_functions(lines: Sequence[str]) -> list[dict]:
    items: dict[str, dict] = {}
    number = name = None
    awaiting_name = False
    buffer: list[str] | None = None

    def close() -> None:
        # One item may list its functions in more than one block (e.g. 2-49 키토산/키토올리고당);
        # keep every function of the same ingredient rather than the last block only.
        text = " ".join(buffer)
        if number in items:
            if items[number]["name"] != name:
                raise NoticeError(f"item {number} names two ingredients")
            items[number]["function_text"] += " " + text
        else:
            items[number] = {"number": number, "name": name, "function_text": text}

    for line in lines:
        if awaiting_name:
            name, awaiting_name = line, False
            continue
        if buffer is not None:
            if not _FUNCTION_END.match(line):
                buffer.append(line)
                continue
            close()
            buffer = None
        if heading := _HEADING.match(line):
            number, name = heading.group(1), heading.group(2)
            awaiting_name = name is None
            continue
        if (start := _FUNCTION_START.match(line)) and number is not None:
            buffer = [part for part in [line[start.end():].strip()] if part]
    if buffer is not None:
        close()
    return list(items.values())


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        items = parse_functions(notice_lines(args.notice_zip))
    except (NoticeError, OSError, zipfile.BadZipFile, UnicodeDecodeError) as exc:
        print(f"error: {exc}")
        return 3
    payload = {
        "reference_version": REFERENCE_VERSION,
        "source": {
            "source_id": "MFDS-NOTICE-FULL-TEXT",
            "notice": args.notice,
            "url": args.source_url,
            "file_name": args.notice_zip.name,
            "file_sha256": hashlib.sha256(args.notice_zip.read_bytes()).hexdigest().upper(),
        },
        "rule": (
            "items with '(1) 기능성 내용' in the standards document; "
            "effects are official-function-v2 phrases found in the text, not attribution"
        ),
        "item_count": len(items),
        "items": [
            {
                **item,
                "effects": [effect.value for effect in official_effect_keys(item["function_text"])],
                "mentioned_effects": [
                    effect.value for effect in EffectKey if effect_mentioned(item["function_text"], effect)
                ],
            }
            for item in items
        ],
    }
    args.output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    print(f"{len(items)} notified ingredients -> {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
