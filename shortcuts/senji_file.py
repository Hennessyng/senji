#!/usr/bin/env python3
from __future__ import annotations

import argparse
import plistlib
import subprocess
import uuid
from pathlib import Path

DEFAULT_ENDPOINT = "https://markdown.myloft.cloud/api/ingest/file"
DEFAULT_TOKEN = "dev-token"
OUTPUT_FILE = Path(__file__).parent / "Senji \u2014 Upload File.shortcut"

_OCHAR = "\ufffc"


def _uid() -> str:
    return str(uuid.uuid4()).upper()


def _text(s: str) -> dict:
    return {
        "Value": {"string": s, "attachmentsByRange": {}},
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


def _action_ref(output_name: str, output_uuid: str) -> dict:
    return {
        "Value": {"OutputName": output_name, "OutputUUID": output_uuid, "Type": "ActionOutput"},
        "WFSerializationType": "WFTextTokenAttachment",
    }


def _share_sheet_file() -> dict:
    return {
        "Value": {
            "string": _OCHAR,
            "attachmentsByRange": {
                "{0, 1}": {"Type": "ExtensionInput"},
            },
        },
        "WFSerializationType": "WFTextTokenString",
    }


def _build_actions(endpoint: str, token: str) -> list[dict]:
    u_http = _uid()

    return [
        # 1. POST multipart/form-data to /api/ingest/file — async, returns {job_id, status}
        {
            "WFWorkflowActionIdentifier": "is.workflow.actions.downloadurl",
            "WFWorkflowActionParameters": {
                "UUID": u_http,
                "WFHTTPMethod": "POST",
                "WFURL": endpoint,
                "WFHTTPBodyType": "Form",
                "WFFormValues": _dict_value(
                    ("file", _share_sheet_file()),
                ),
                "WFHTTPHeaders": _dict_value(
                    ("Authorization", _text(f"Bearer {token}")),
                ),
                "WFShowWebView": False,
            },
        },
        # 2. Notify — ingest is async, file queued for processing
        {
            "WFWorkflowActionIdentifier": "is.workflow.actions.notification",
            "WFWorkflowActionParameters": {
                "WFNotificationActionTitle": _text("Senji \u2014 Queued \u2713"),
                "WFNotificationActionBody": _text("File queued for processing"),
                "WFNotificationActionSound": False,
            },
        },
    ]


def build_shortcut(endpoint: str, token: str) -> dict:
    return {
        "WFWorkflowMinimumClientVersion": 900,
        "WFWorkflowMinimumClientVersionString": "900",
        "WFWorkflowHasOutputFallback": False,
        "WFWorkflowInputContentItemClasses": ["WFGenericFileContentItem"],
        "WFWorkflowIcon": {
            "WFWorkflowIconGlyphNumber": 61440,
            "WFWorkflowIconStartColor": 946986751,
        },
        "WFWorkflowImportQuestions": [],
        "WFWorkflowTypes": ["NCWidget", "WatchKit", "ActionExtension"],
        "WFWorkflowActions": _build_actions(endpoint, token),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate Senji \u2014 Upload File.shortcut")
    parser.add_argument("--token", default=DEFAULT_TOKEN, metavar="TOKEN",
                        help="Bearer token (default: dev-token)")
    parser.add_argument("--endpoint", default=DEFAULT_ENDPOINT, metavar="URL",
                        help=f"Senji ingest endpoint (default: {DEFAULT_ENDPOINT})")
    args = parser.parse_args()

    data = build_shortcut(endpoint=args.endpoint, token=args.token)

    with OUTPUT_FILE.open("wb") as f:
        plistlib.dump(data, f, fmt=plistlib.FMT_BINARY)

    subprocess.run(["shortcuts", "sign", "-i", str(OUTPUT_FILE), "-o", str(OUTPUT_FILE)], check=True)

    size = OUTPUT_FILE.stat().st_size
    print(f"\u2713 {OUTPUT_FILE}  ({size:,} bytes)")
    print(f"  endpoint: {args.endpoint}")
    print()
    print("Import: double-click on macOS, or AirDrop to iPhone")


if __name__ == "__main__":
    main()
