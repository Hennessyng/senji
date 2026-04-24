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

def _ask_for_text(prompt):
    return {
        "WFWorkflowActionIdentifier": "is.workflow.actions.ask",
        "WFWorkflowActionParameters": {
            "WFInputActionString": _text(prompt),
            "WFAskActionRequestType": 0
        }
    }

def _post_file(url, file_var):
    return {
        "WFWorkflowActionIdentifier": "is.workflow.actions.downloadurl",
        "WFWorkflowActionParameters": {
            "WFURLActionURL": _text(url),
            "WFHTTPMethod": 1,
            "WFHTTPHeaders": {"Authorization": _text("Bearer {API_TOKEN}")},
            "WFHTTPBodyType": "Form",
            "WFFormValues": [
                {
                    "Key": "file",
                    "Value": file_var
                }
            ]
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
        "WFWorkflowActionIdentifier": "is.workflow.actions.ask.for.document",
        "WFWorkflowActionParameters": {
            "WFInputActionString": _text("Choose file to upload"),
            "WFAskActionRequestType": 18
        }
    },
    _post_file(
        "https://markdown.myloft.cloud/api/ingest/file",
        _var("Provided Media")
    ),
    _notification("Uploaded: ￼Result￼"),
    _alert("Error", "￼Result￼")
]

shortcut = {
    "WFWorkflowTypes": 1,
    "WFWorkflowInputTypes": ["public.data"],
    "WFWorkflowActions": actions,
    "WFWorkflowClientVersion": {"WFWorkflowMinimumClientRelease": 900, "WFWorkflowMinimumClientVersion": 900}
}

if __name__ == "__main__":
    with open("Senji — Upload File.shortcut", "wb") as f:
        plistlib.dump(shortcut, f)
    print("✓ Senji — Upload File.shortcut created")
