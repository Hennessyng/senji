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
DEFAULT_VAULT = "SecondBrain"

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
        "Value": {
            "string": _OCHAR,
            "attachmentsByRange": {
                "{0, 1}": {"Type": "ExtensionInput"},
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


def _magic_text(prefix: str, output_name: str, output_uuid: str, suffix: str = "") -> dict:
    """Embed an action output inside a text string (e.g. title + '.md')."""
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


def _build_actions(endpoint: str, token: str, vault: str, debug: bool = False) -> list[dict]:
    u_http = _uid()
    u_dict = _uid()
    u_title_val = _uid()
    u_md_val = _uid()
    u_title_text = _uid()
    u_md_text = _uid()
    u_enc_title = _uid()
    u_enc_md = _uid()
    u_url = _uid()

    def _debug_show(label: str, source_uuid: str, source_name: str) -> list[dict]:
        tmp = _uid()
        return [
            {
                "WFWorkflowActionIdentifier": "is.workflow.actions.gettext",
                "WFWorkflowActionParameters": {
                    "UUID": tmp,
                    "WFTextActionText": _magic_text("", source_name, source_uuid),
                },
            },
            {
                "WFWorkflowActionIdentifier": "is.workflow.actions.showresult",
                "WFWorkflowActionParameters": {
                    "Text": _magic_text(f"{label}: ", "Text", tmp),
                },
            },
        ]

    actions = [
        {
            "WFWorkflowActionIdentifier": "is.workflow.actions.downloadurl",
            "WFWorkflowActionParameters": {
                "UUID": u_http,
                "WFHTTPMethod": "POST",
                "WFURL": endpoint,
                "WFHTTPBodyType": "JSON",
                "WFJSONValues": _dict_value(
                    ("url", _ext_input()),
                ),
                "WFHTTPHeaders": _dict_value(
                    ("Authorization", _text(f"Bearer {token}")),
                    ("Content-Type", _text("application/json")),
                ),
                "WFShowWebView": False,
            },
        },
    ]

    if debug:
        actions.extend(_debug_show("DEBUG 1: Raw API response", u_http, "Contents of URL"))

    actions.append(
        {
            "WFWorkflowActionIdentifier": "is.workflow.actions.detect.dictionary",
            "WFWorkflowActionParameters": {
                "UUID": u_dict,
                "WFInput": _magic("Contents of URL", u_http),
            },
        },
    )

    if debug:
        actions.extend(_debug_show("DEBUG 2: Parsed dictionary", u_dict, "Dictionary"))

    actions.extend([
        {
            "WFWorkflowActionIdentifier": "is.workflow.actions.getvalueforkey",
            "WFWorkflowActionParameters": {
                "UUID": u_title_val,
                "WFInput": _magic("Dictionary", u_dict),
                "WFDictionaryKey": "title",
            },
        },
        {
            "WFWorkflowActionIdentifier": "is.workflow.actions.getvalueforkey",
            "WFWorkflowActionParameters": {
                "UUID": u_md_val,
                "WFInput": _magic("Dictionary", u_dict),
                "WFDictionaryKey": "markdown",
            },
        },
    ])

    if debug:
        actions.extend(_debug_show("DEBUG 3: Extracted title", u_title_val, "Value"))
        actions.extend(_debug_show("DEBUG 4: Extracted markdown", u_md_val, "Value"))

    # Materialize title as text → URL-encode
    actions.extend([
        {
            "WFWorkflowActionIdentifier": "is.workflow.actions.gettext",
            "WFWorkflowActionParameters": {
                "UUID": u_title_text,
                "WFTextActionText": _magic_text("", "Value", u_title_val),
            },
        },
        {
            "WFWorkflowActionIdentifier": "is.workflow.actions.urlencode",
            "WFWorkflowActionParameters": {
                "UUID": u_enc_title,
                "WFEncodeMode": "Encode",
                "WFInput": _magic("Text", u_title_text),
            },
        },
    ])

    # Materialize markdown as text → URL-encode
    actions.extend([
        {
            "WFWorkflowActionIdentifier": "is.workflow.actions.gettext",
            "WFWorkflowActionParameters": {
                "UUID": u_md_text,
                "WFTextActionText": _magic_text("", "Value", u_md_val),
            },
        },
        {
            "WFWorkflowActionIdentifier": "is.workflow.actions.urlencode",
            "WFWorkflowActionParameters": {
                "UUID": u_enc_md,
                "WFEncodeMode": "Encode",
                "WFInput": _magic("Text", u_md_text),
            },
        },
    ])

    # Build obsidian:// URI with two embedded encoded variables
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
            "WFInput": _magic("Text", u_url),
        },
    })

    if debug:
        actions.extend(_debug_show("DEBUG 5: Obsidian URL", u_url, "Text"))

    actions.append({
        "WFWorkflowActionIdentifier": "is.workflow.actions.notification",
        "WFWorkflowActionParameters": {
            "WFNotificationActionTitle": _text("Saved to Obsidian \u2713"),
            "WFNotificationActionBody": _magic("Value", u_title_val),
            "WFNotificationActionSound": False,
        },
    })

    return actions


def build_shortcut(endpoint: str, token: str, vault: str, debug: bool = False) -> dict:
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
        "WFWorkflowActions": _build_actions(endpoint, token, vault, debug=debug),
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
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Add alert actions after each step for debugging",
    )
    args = parser.parse_args()

    data = build_shortcut(endpoint=args.endpoint, token=args.token, vault=args.vault, debug=args.debug)

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
