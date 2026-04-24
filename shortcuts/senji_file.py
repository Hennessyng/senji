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

def _bearer_token(var_name):
    prefix = "Bearer "
    var_part = f"￼{var_name}￼"
    return {
        "string": prefix + var_part,
        "attachmentsByRange": {
            str(len(prefix) + i): {"Type": "Variable", "OutputName": var_name, "OutputUUID": _uid()}
            for i in range(len(var_name))
        }
    }

def _post_file(url, file_var):
    return {
        "WFWorkflowActionIdentifier": "is.workflow.actions.downloadurl",
        "WFWorkflowActionParameters": {
            "WFURLActionURL": _text(url),
            "WFHTTPMethod": 1,
            "WFHTTPHeaders": {"Authorization": _bearer_token("API_TOKEN")},
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
    _post_file(
        "https://markdown.myloft.cloud/api/ingest/file",
        _var("Shortcut Input")
    ),
    {
        "WFWorkflowActionIdentifier": "is.workflow.actions.conditional",
        "WFWorkflowActionParameters": {
            "WFInput": _var("Status Code"),
            "WFControlFlowCondition": 0,
            "WFConditionalActionString": "202"
        }
    },
    _notification("Uploaded: ￼Result￼"),
    {
        "WFWorkflowActionIdentifier": "is.workflow.actions.conditional",
        "WFWorkflowActionParameters": {
            "WFInput": _var("Status Code"),
            "WFControlFlowCondition": 2
        }
    },
    _alert("Error", "￼Result￼")
]

shortcut = {
    "WFWorkflowTypes": 1,
    "WFWorkflowInputTypes": ["public.data"],
    "WFWorkflowActions": actions,
    "WFWorkflowClientVersion": {"WFWorkflowMinimumClientRelease": 900, "WFWorkflowMinimumClientVersion": 900}
}

if __name__ == "__main__":
    with open("Senji — Clip File.shortcut", "wb") as f:
        plistlib.dump(shortcut, f)
    print("✓ Senji — Clip File.shortcut created")
