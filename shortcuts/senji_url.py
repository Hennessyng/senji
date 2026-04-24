#!/usr/bin/env python3
import plistlib
import uuid

def _uid():
    return str(uuid.uuid4()).upper()

def _text(s):
    return {"WFSerializationType": "WFTextSerializationObject", "string": s}

def _var(name):
    return {
        "string": f"￼{name}￼",
        "attachmentsByRange": {str(i): {"Type": "ActionOutput", "OutputName": name, "OutputUUID": _uid()} for i in range(len(name))}
    }

def _dict_value(key, val):
    return {"Key": key, "Value": {"string": val, "attachmentsByRange": {}}}

def _ask_for_text(prompt):
    return {
        "WFWorkflowActionIdentifier": "is.workflow.actions.ask",
        "WFWorkflowActionParameters": {
            "WFInputActionString": _text(prompt),
            "WFAskActionRequestType": 0
        }
    }

def _post_url(url, headers_dict, body_dict):
    return {
        "WFWorkflowActionIdentifier": "is.workflow.actions.downloadurl",
        "WFWorkflowActionParameters": {
            "WFURLActionURL": _text(url),
            "WFHTTPMethod": 1,
            "WFHTTPHeaders": {"Authorization": _text("Bearer {API_TOKEN}")},
            "WFHTTPBodyType": "JSON",
            "WFJSONValues": body_dict
        }
    }

def _notification(text):
    return {
        "WFWorkflowActionIdentifier": "is.workflow.actions.notification",
        "WFWorkflowActionParameters": {"WFNotificationActionBody": _text(text)}
    }

def _alert(title, body):
    return {
        "WFWorkflowActionIdentifier": "is.workflow.actions.alert",
        "WFWorkflowActionParameters": {
            "WFAlertActionTitle": _text(title),
            "WFAlertActionMessage": _text(body)
        }
    }

# Build shortcut
actions = [
    {
        "WFWorkflowActionIdentifier": "is.workflow.actions.getcliipboardcontents",
        "WFWorkflowActionParameters": {}
    },
    _post_url(
        "https://markdown.myloft.cloud/api/ingest/url",
        {"Authorization": "Bearer {API_TOKEN}"},
        {"url": {"string": "￼Clipboard￼"}, "tags": []}
    ),
    _notification("Queued: ￼Result￼"),
    _alert("Error", "￼Result￼")
]

shortcut = {
    "WFWorkflowTypes": 1,
    "WFWorkflowInputTypes": ["public.url"],
    "WFWorkflowActions": actions,
    "WFWorkflowClientVersion": {"WFWorkflowMinimumClientRelease": 900, "WFWorkflowMinimumClientVersion": 900}
}

if __name__ == "__main__":
    with open("Senji — Clip URL.shortcut", "wb") as f:
        plistlib.dump(shortcut, f)
    print("✓ Senji — Clip URL.shortcut created")
