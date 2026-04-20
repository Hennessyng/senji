#!/usr/bin/env python3
"""
Generate senji-clipper.shortcut — Apple Shortcuts web clipper for senji.

Compatible with iOS 16+ and macOS 13+.
Import: double-click on Mac, or AirDrop to iPhone.

When triggered from Share Sheet on any URL:
  1. POSTs to senji → receives Obsidian-formatted markdown
  2. Saves [title].md to iCloud Drive/Obsidian/[vault]/Clippings/
  3. Shows "Saved to Obsidian ✓" notification

Usage:
    python scripts/generate_shortcut.py --vault "MyVault"
    python scripts/generate_shortcut.py --vault "MyVault" --token "your-token" --output senji-clipper.shortcut
"""

from __future__ import annotations

import argparse
import plistlib
import subprocess
import uuid
from pathlib import Path

DEFAULT_ENDPOINT = "https://markdown.myloft.cloud/api/convert/url"
DEFAULT_TOKEN = "dev-token"
DEFAULT_VAULT = "SeconBrain"

_OCHAR = "\ufffc"


def _uid() -> str:
    return str(uuid.uuid4()).upper()


def _text(s: str) -> dict:
    return {
        "Value": {"string": s, "attachmentsByRange": {}},
        "WFSerializationType": "WFTextTokenString",
    }


def _text_with_var(prefix: str, var_name: str, suffix: str = "") -> dict:
    s = prefix + _OCHAR + suffix
    return {
        "Value": {
            "string": s,
            "attachmentsByRange": {
                f"{{{len(prefix)}, 1}}": {"Type": "Variable", "VariableName": var_name},
            },
        },
        "WFSerializationType": "WFTextTokenString",
    }


def _magic(output_name: str, output_uuid: str) -> dict:
    return {
        "Value": {"OutputName": output_name, "OutputUUID": output_uuid, "Type": "ActionOutput"},
        "WFSerializationType": "WFTextTokenAttachment",
    }


def _var(name: str) -> dict:
    return {
        "Value": {"Type": "Variable", "VariableName": name},
        "WFSerializationType": "WFTextTokenAttachment",
    }


def _ext_input() -> dict:
    return {
        "Value": {"Type": "ExtensionInput"},
        "WFSerializationType": "WFTextTokenAttachment",
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
    u_get_md = _uid()
    u_get_title = _uid()
    u_filename = _uid()

    return [
        {
            "WFWorkflowActionIdentifier": "is.workflow.actions.downloadurl",
            "WFWorkflowActionParameters": {
                "UUID": u_http,
                "WFHTTPMethod": "POST",
                "WFURL": endpoint,
                "WFHTTPBodyType": "JSON",
                "WFHTTPInputBody": _dict_value(
                    ("url", _ext_input()),
                ),
                "WFHTTPHeaders": _dict_value(
                    ("Authorization", _text(f"Bearer {token}")),
                    ("Content-Type", _text("application/json")),
                ),
                "WFShowWebView": False,
            },
        },
        {
            "WFWorkflowActionIdentifier": "is.workflow.actions.getdictionaryvalue",
            "WFWorkflowActionParameters": {
                "UUID": u_get_md,
                "WFDictionaryKey": "markdown",
                "WFInput": _magic("URL Results", u_http),
            },
        },
        {
            "WFWorkflowActionIdentifier": "is.workflow.actions.setvariable",
            "WFWorkflowActionParameters": {
                "WFVariableName": "Markdown",
                "WFInput": _magic("Dictionary Value", u_get_md),
            },
        },
        {
            "WFWorkflowActionIdentifier": "is.workflow.actions.getdictionaryvalue",
            "WFWorkflowActionParameters": {
                "UUID": u_get_title,
                "WFDictionaryKey": "title",
                "WFInput": _magic("URL Results", u_http),
            },
        },
        {
            "WFWorkflowActionIdentifier": "is.workflow.actions.setvariable",
            "WFWorkflowActionParameters": {
                "WFVariableName": "Title",
                "WFInput": _magic("Dictionary Value", u_get_title),
            },
        },
        {
            "WFWorkflowActionIdentifier": "is.workflow.actions.text",
            "WFWorkflowActionParameters": {
                "UUID": u_filename,
                "WFTextActionText": _text_with_var("", "Title", ".md"),
            },
        },
        {
            "WFWorkflowActionIdentifier": "is.workflow.actions.savefile",
            "WFWorkflowActionParameters": {
                "WFInput": _var("Markdown"),
                "WFFileDestinationPath": f"Obsidian/{vault}/Clippings",
                "WFFilename": _magic("Text", u_filename),
                "SaveNotAskEachTime": True,
                "SelectMultiple": False,
            },
        },
        {
            "WFWorkflowActionIdentifier": "is.workflow.actions.notification",
            "WFWorkflowActionParameters": {
                "WFNotificationActionTitle": _text("Saved to Obsidian \u2713"),
                "WFNotificationActionBody": _var("Title"),
                "WFNotificationActionSound": False,
            },
        },
    ]


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
        "WFWorkflowTypes": ["NCWidget", "WatchKit"],
        "WFWorkflowActions": _build_actions(endpoint, token, vault),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate senji-clipper.shortcut")
    parser.add_argument(
        "--vault",
        default=DEFAULT_VAULT,
        metavar="NAME",
        help="Obsidian vault folder name in iCloud Drive (default: MyVault)",
    )
    parser.add_argument(
        "--token", default=DEFAULT_TOKEN, metavar="TOKEN", help="Bearer token (default: dev-token)"
    )
    parser.add_argument(
        "--endpoint",
        default=DEFAULT_ENDPOINT,
        metavar="URL",
        help=f"Senji API URL (default: {DEFAULT_ENDPOINT})",
    )
    parser.add_argument(
        "--output",
        default="senji-clipper.shortcut",
        metavar="FILE",
        help="Output file path (default: senji-clipper.shortcut)",
    )
    args = parser.parse_args()

    data = build_shortcut(endpoint=args.endpoint, token=args.token, vault=args.vault)

    out = Path(args.output)
    with out.open("wb") as f:
        plistlib.dump(data, f, fmt=plistlib.FMT_BINARY)

    subprocess.run(["shortcuts", "sign", "-i", str(out), "-o", str(out)], check=True)

    size = out.stat().st_size
    print(f"\u2713 {out}  ({size:,} bytes)")
    print(f"  vault:    iCloud Drive/Obsidian/{args.vault}/Clippings/")
    print(f"  endpoint: {args.endpoint}")
    print()
    print("Import:")
    print("  macOS \u2014 double-click senji-clipper.shortcut")
    print("  iOS   \u2014 AirDrop to iPhone \u2192 tap to import")
    print()
    print("Usage: Share any URL \u2192 Shortcuts \u2192 Senji Clipper")


if __name__ == "__main__":
    main()
