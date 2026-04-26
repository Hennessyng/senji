#!/usr/bin/env python3
"""
Generate 'Senji — Clip URL.shortcut' aligned with the current senji gateway stack.

Flow:
  1. POST /api/convert/url  (sync — returns {markdown, title, source, media})
  2. Parse JSON response → extract title + markdown
  3. URL-encode both values
  4. Open obsidian://new?vault=...&file=Clippings%2F{title}&content={markdown}&overwrite=true
  5. Show "Saved to Obsidian ✓" notification

Usage:
    python shortcuts/senji_url.py
    python shortcuts/senji_url.py --vault "MyVault" --token "your-token"
"""

from __future__ import annotations

import argparse
import plistlib
import subprocess
import uuid
from pathlib import Path

DEFAULT_ENDPOINT = "https://markdown.myloft.cloud/api/convert/url"
DEFAULT_TOKEN = "dev-token"
DEFAULT_VAULT = "SecondBrain"
OUTPUT_FILE = Path(__file__).parent / "Senji \u2014 Clip URL.shortcut"

_OCHAR = "\ufffc"


def _uid() -> str:
    return str(uuid.uuid4()).upper()


def _text(s: str) -> dict:
    return {
        "Value": {"string": s, "attachmentsByRange": {}},
        "WFSerializationType": "WFTextTokenString",
    }


def _share_sheet_url() -> dict:
    return {
        "Value": {
            "string": _OCHAR,
            "attachmentsByRange": {
                "{0, 1}": {"Type": "ExtensionInput"},
            },
        },
        "WFSerializationType": "WFTextTokenString",
    }


def _action_ref(output_name: str, output_uuid: str) -> dict:
    return {
        "Value": {"OutputName": output_name, "OutputUUID": output_uuid, "Type": "ActionOutput"},
        "WFSerializationType": "WFTextTokenAttachment",
    }


def _action_in_text(prefix: str, output_name: str, output_uuid: str, suffix: str = "") -> dict:
    s = prefix + _OCHAR + suffix
    return {
        "Value": {
            "string": s,
            "attachmentsByRange": {
                f"{{{len(prefix)}, 1}}": {
                    "OutputName": output_name,
                    "OutputUUID": output_uuid,
                    "Type": "ActionOutput",
                },
            },
        },
        "WFSerializationType": "WFTextTokenString",
    }


def _dict_value(*kv_pairs: tuple) -> dict:
    return {
        "Value": {
            "WFDictionaryFieldValueItems": [
                {"WFItemType": 0, "WFKey": _text(k), "WFValue": v} for k, v in kv_pairs
            ]
        },
        "WFSerializationType": "WFDictionaryFieldValue",
    }


def _build_actions(endpoint: str, token: str, vault: str) -> list[dict]:
    u_http = _uid()
    u_dict = _uid()
    u_title_val = _uid()
    u_md_val = _uid()
    u_title_text = _uid()
    u_md_text = _uid()
    u_enc_title = _uid()
    u_enc_md = _uid()
    u_url = _uid()

    actions = [
        # 1. POST /api/convert/url — synchronous, returns {markdown, title, source, media}
        {
            "WFWorkflowActionIdentifier": "is.workflow.actions.downloadurl",
            "WFWorkflowActionParameters": {
                "UUID": u_http,
                "WFHTTPMethod": "POST",
                "WFURL": endpoint,
                "WFHTTPBodyType": "JSON",
                "WFJSONValues": _dict_value(
                    ("url", _share_sheet_url()),
                ),
                "WFHTTPHeaders": _dict_value(
                    ("Authorization", _text(f"Bearer {token}")),
                    ("Content-Type", _text("application/json")),
                ),
                "WFShowWebView": False,
            },
        },
        # 2. Parse response body as JSON dictionary
        {
            "WFWorkflowActionIdentifier": "is.workflow.actions.detect.dictionary",
            "WFWorkflowActionParameters": {
                "UUID": u_dict,
                "WFInput": _action_ref("Contents of URL", u_http),
            },
        },
        # 3a. Extract "title" key
        {
            "WFWorkflowActionIdentifier": "is.workflow.actions.getvalueforkey",
            "WFWorkflowActionParameters": {
                "UUID": u_title_val,
                "WFInput": _action_ref("Dictionary", u_dict),
                "WFDictionaryKey": "title",
            },
        },
        # 3b. Extract "markdown" key
        {
            "WFWorkflowActionIdentifier": "is.workflow.actions.getvalueforkey",
            "WFWorkflowActionParameters": {
                "UUID": u_md_val,
                "WFInput": _action_ref("Dictionary", u_dict),
                "WFDictionaryKey": "markdown",
            },
        },
        # 4a. Materialise title as text → URL-encode for obsidian:// filename
        {
            "WFWorkflowActionIdentifier": "is.workflow.actions.gettext",
            "WFWorkflowActionParameters": {
                "UUID": u_title_text,
                "WFTextActionText": _action_in_text("", "Value", u_title_val),
            },
        },
        {
            "WFWorkflowActionIdentifier": "is.workflow.actions.urlencode",
            "WFWorkflowActionParameters": {
                "UUID": u_enc_title,
                "WFEncodeMode": "Encode",
                "WFInput": _action_ref("Text", u_title_text),
            },
        },
        # 4b. Materialise markdown as text → URL-encode for obsidian:// content
        {
            "WFWorkflowActionIdentifier": "is.workflow.actions.gettext",
            "WFWorkflowActionParameters": {
                "UUID": u_md_text,
                "WFTextActionText": _action_in_text("", "Value", u_md_val),
            },
        },
        {
            "WFWorkflowActionIdentifier": "is.workflow.actions.urlencode",
            "WFWorkflowActionParameters": {
                "UUID": u_enc_md,
                "WFEncodeMode": "Encode",
                "WFInput": _action_ref("Text", u_md_text),
            },
        },
    ]

    # 5. Build obsidian:// URI with two embedded URL-encoded variables
    prefix = f"obsidian://new?vault={vault}&file=Clippings%2F"
    middle = "&content="
    suffix = "&overwrite=true"
    url_string = prefix + _OCHAR + middle + _OCHAR + suffix
    enc_title_pos = len(prefix)
    enc_md_pos = len(prefix) + 1 + len(middle)

    actions.append({
        "WFWorkflowActionIdentifier": "is.workflow.actions.gettext",
        "WFWorkflowActionParameters": {
            "UUID": u_url,
            "WFTextActionText": {
                "Value": {
                    "string": url_string,
                    "attachmentsByRange": {
                        f"{{{enc_title_pos}, 1}}": {
                            "OutputName": "URL Encoded Text",
                            "OutputUUID": u_enc_title,
                            "Type": "ActionOutput",
                        },
                        f"{{{enc_md_pos}, 1}}": {
                            "OutputName": "URL Encoded Text",
                            "OutputUUID": u_enc_md,
                            "Type": "ActionOutput",
                        },
                    },
                },
                "WFSerializationType": "WFTextTokenString",
            },
        },
    })

    actions.append({
        "WFWorkflowActionIdentifier": "is.workflow.actions.openurl",
        "WFWorkflowActionParameters": {
            "Show-WFInput": True,
            "WFInput": _action_ref("Text", u_url),
        },
    })

    # 6. Success notification
    actions.append({
        "WFWorkflowActionIdentifier": "is.workflow.actions.notification",
        "WFWorkflowActionParameters": {
            "WFNotificationActionTitle": _text("Saved to Obsidian \u2713"),
            "WFNotificationActionBody": _action_ref("Value", u_title_val),
            "WFNotificationActionSound": False,
        },
    })

    return actions


def build_shortcut(endpoint: str, token: str, vault: str) -> dict:
    return {
        "WFWorkflowMinimumClientVersion": 900,
        "WFWorkflowMinimumClientVersionString": "900",
        "WFWorkflowHasOutputFallback": False,
        "WFWorkflowOutputContentItemClasses": ["WFStringContentItem"],
        "WFWorkflowInputContentItemClasses": ["WFURLContentItem"],
        "WFWorkflowIcon": {
            "WFWorkflowIconGlyphNumber": 61440,
            "WFWorkflowIconStartColor": 946986751,
        },
        "WFWorkflowImportQuestions": [],
        "WFWorkflowTypes": ["NCWidget", "WatchKit", "ActionExtension"],
        "WFWorkflowActions": _build_actions(endpoint, token, vault),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate Senji \u2014 Clip URL.shortcut")
    parser.add_argument("--vault", default=DEFAULT_VAULT, metavar="NAME",
                        help=f"Obsidian vault name in iCloud Drive (default: {DEFAULT_VAULT})")
    parser.add_argument("--token", default=DEFAULT_TOKEN, metavar="TOKEN",
                        help="Bearer token (default: dev-token)")
    parser.add_argument("--endpoint", default=DEFAULT_ENDPOINT, metavar="URL",
                        help=f"Senji convert endpoint (default: {DEFAULT_ENDPOINT})")
    args = parser.parse_args()

    data = build_shortcut(endpoint=args.endpoint, token=args.token, vault=args.vault)

    with OUTPUT_FILE.open("wb") as f:
        plistlib.dump(data, f, fmt=plistlib.FMT_BINARY)

    subprocess.run(["shortcuts", "sign", "-i", str(OUTPUT_FILE), "-o", str(OUTPUT_FILE)], check=True)

    size = OUTPUT_FILE.stat().st_size
    print(f"\u2713 {OUTPUT_FILE}  ({size:,} bytes)")
    print(f"  vault:    iCloud Drive/Obsidian/{args.vault}/Clippings/")
    print(f"  endpoint: {args.endpoint}")
    print()
    print("Import: double-click on macOS, or AirDrop to iPhone")


if __name__ == "__main__":
    main()
