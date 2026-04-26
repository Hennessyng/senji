#!/usr/bin/env python3
from __future__ import annotations
import argparse, plistlib, subprocess, uuid
from pathlib import Path

DEFAULT_ENDPOINT_URL  = "https://markdown.myloft.cloud/api/convert/url"
DEFAULT_ENDPOINT_FILE = "https://markdown.myloft.cloud/api/ingest/file"
DEFAULT_TOKEN = "dev-token"
DEFAULT_VAULT = "SecondBrain"
OUTPUT_FILE   = Path(__file__).parent / "Senji \u2014 Clipper.shortcut"
_OCHAR = "\ufffc"

def _uid(): return str(uuid.uuid4()).upper()

def _text(s):
    return {"Value": {"string": s, "attachmentsByRange": {}}, "WFSerializationType": "WFTextTokenString"}

def _ext_input():
    return {"Value": {"string": _OCHAR, "attachmentsByRange": {"{0, 1}": {"Type": "ExtensionInput"}}}, "WFSerializationType": "WFTextTokenString"}

def _ext_input_ref():
    return {"Value": {"Type": "ExtensionInput"}, "WFSerializationType": "WFTextTokenAttachment"}

def _action_ref(name, uid):
    return {"Value": {"OutputName": name, "OutputUUID": uid, "Type": "ActionOutput"}, "WFSerializationType": "WFTextTokenAttachment"}

def _action_in_text(prefix, name, uid, suffix=""):
    s = prefix + _OCHAR + suffix
    return {"Value": {"string": s, "attachmentsByRange": {f"{{{len(prefix)}, 1}}": {"OutputName": name, "OutputUUID": uid, "Type": "ActionOutput"}}}, "WFSerializationType": "WFTextTokenString"}

def _dict_value(*kv):
    return {"Value": {"WFDictionaryFieldValueItems": [{"WFItemType": 0, "WFKey": _text(k), "WFValue": v} for k, v in kv]}, "WFSerializationType": "WFDictionaryFieldValue"}

def _build_actions(ep_url, ep_file, token, vault):
    u_txt=_uid(); grp=_uid()
    u_http=_uid(); u_dict=_uid(); u_tv=_uid(); u_mv=_uid()
    u_tt=_uid(); u_mt=_uid(); u_et=_uid(); u_em=_uid(); u_obs=_uid()
    u_fhttp=_uid()
    pfx = f"obsidian://new?vault={vault}&file=Clippings%2F"
    mid = "&content="; sfx = "&overwrite=true"
    obs_str = pfx + _OCHAR + mid + _OCHAR + sfx
    tp = len(pfx); mp = len(pfx)+1+len(mid)
    return [
        {"WFWorkflowActionIdentifier":"is.workflow.actions.gettext","WFWorkflowActionParameters":{"UUID":u_txt,"WFTextActionText":_ext_input()}},
        {"WFWorkflowActionIdentifier":"is.workflow.actions.conditional","WFWorkflowActionParameters":{"GroupingIdentifier":grp,"WFControlFlowMode":0,"WFCondition":4,"WFInput":_action_ref("Text",u_txt),"WFConditionalActionString":"http"}},
        {"WFWorkflowActionIdentifier":"is.workflow.actions.downloadurl","WFWorkflowActionParameters":{"UUID":u_http,"WFHTTPMethod":"POST","WFURL":ep_url,"WFHTTPBodyType":"JSON","WFJSONValues":_dict_value(("url",_ext_input())),"WFHTTPHeaders":_dict_value(("Authorization",_text(f"Bearer {token}")),("Content-Type",_text("application/json"))),"WFShowWebView":False}},
        {"WFWorkflowActionIdentifier":"is.workflow.actions.detect.dictionary","WFWorkflowActionParameters":{"UUID":u_dict,"WFInput":_action_ref("Contents of URL",u_http)}},
        {"WFWorkflowActionIdentifier":"is.workflow.actions.getvalueforkey","WFWorkflowActionParameters":{"UUID":u_tv,"WFInput":_action_ref("Dictionary",u_dict),"WFDictionaryKey":"title"}},
        {"WFWorkflowActionIdentifier":"is.workflow.actions.getvalueforkey","WFWorkflowActionParameters":{"UUID":u_mv,"WFInput":_action_ref("Dictionary",u_dict),"WFDictionaryKey":"markdown"}},
        {"WFWorkflowActionIdentifier":"is.workflow.actions.gettext","WFWorkflowActionParameters":{"UUID":u_tt,"WFTextActionText":_action_in_text("","Value",u_tv)}},
        {"WFWorkflowActionIdentifier":"is.workflow.actions.urlencode","WFWorkflowActionParameters":{"UUID":u_et,"WFEncodeMode":"Encode","WFInput":_action_ref("Text",u_tt)}},
        {"WFWorkflowActionIdentifier":"is.workflow.actions.gettext","WFWorkflowActionParameters":{"UUID":u_mt,"WFTextActionText":_action_in_text("","Value",u_mv)}},
        {"WFWorkflowActionIdentifier":"is.workflow.actions.urlencode","WFWorkflowActionParameters":{"UUID":u_em,"WFEncodeMode":"Encode","WFInput":_action_ref("Text",u_mt)}},
        {"WFWorkflowActionIdentifier":"is.workflow.actions.gettext","WFWorkflowActionParameters":{"UUID":u_obs,"WFTextActionText":{"Value":{"string":obs_str,"attachmentsByRange":{f"{{{tp},1}}":{"OutputName":"URL Encoded Text","OutputUUID":u_et,"Type":"ActionOutput"},f"{{{mp},1}}":{"OutputName":"URL Encoded Text","OutputUUID":u_em,"Type":"ActionOutput"}}},"WFSerializationType":"WFTextTokenString"}}},
        {"WFWorkflowActionIdentifier":"is.workflow.actions.openurl","WFWorkflowActionParameters":{"Show-WFInput":True,"WFInput":_action_ref("Text",u_obs)}},
        {"WFWorkflowActionIdentifier":"is.workflow.actions.notification","WFWorkflowActionParameters":{"WFNotificationActionTitle":_text("Saved to Obsidian \u2713"),"WFNotificationActionBody":_action_ref("Value",u_tv),"WFNotificationActionSound":False}},
        {"WFWorkflowActionIdentifier":"is.workflow.actions.conditional","WFWorkflowActionParameters":{"GroupingIdentifier":grp,"WFControlFlowMode":1}},
        {"WFWorkflowActionIdentifier":"is.workflow.actions.downloadurl","WFWorkflowActionParameters":{"UUID":u_fhttp,"WFHTTPMethod":"POST","WFURL":ep_file,"WFHTTPBodyType":"Form","WFFormValues":_dict_value(("file",_ext_input())),"WFHTTPHeaders":_dict_value(("Authorization",_text(f"Bearer {token}"))),"WFShowWebView":False}},
        {"WFWorkflowActionIdentifier":"is.workflow.actions.notification","WFWorkflowActionParameters":{"WFNotificationActionTitle":_text("Senji \u2014 Queued \u2713"),"WFNotificationActionBody":_text("File queued for processing"),"WFNotificationActionSound":False}},
        {"WFWorkflowActionIdentifier":"is.workflow.actions.conditional","WFWorkflowActionParameters":{"GroupingIdentifier":grp,"WFControlFlowMode":2}},
    ]

def build_shortcut(ep_url, ep_file, token, vault):
    return {"WFWorkflowMinimumClientVersion":900,"WFWorkflowMinimumClientVersionString":"900","WFWorkflowHasOutputFallback":False,"WFWorkflowInputContentItemClasses":["WFURLContentItem","WFGenericFileContentItem"],"WFWorkflowIcon":{"WFWorkflowIconGlyphNumber":61440,"WFWorkflowIconStartColor":946986751},"WFWorkflowImportQuestions":[],"WFWorkflowTypes":["NCWidget","WatchKit","ActionExtension"],"WFWorkflowActions":_build_actions(ep_url,ep_file,token,vault)}

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--vault",default=DEFAULT_VAULT); p.add_argument("--token",default=DEFAULT_TOKEN)
    p.add_argument("--endpoint-url",default=DEFAULT_ENDPOINT_URL); p.add_argument("--endpoint-file",default=DEFAULT_ENDPOINT_FILE)
    a = p.parse_args()
    data = build_shortcut(a.endpoint_url, a.endpoint_file, a.token, a.vault)
    with OUTPUT_FILE.open("wb") as f: plistlib.dump(data,f,fmt=plistlib.FMT_BINARY)
    subprocess.run(["shortcuts","sign","-i",str(OUTPUT_FILE),"-o",str(OUTPUT_FILE)],check=True)
    print(f"\u2713 {OUTPUT_FILE}  ({OUTPUT_FILE.stat().st_size:,} bytes)")
    print(f"  vault: iCloud Drive/Obsidian/{a.vault}/Clippings/")
    print("Usage: Share URL or file \u2192 Shortcuts \u2192 Senji \u2014 Clipper")

if __name__=="__main__": main()
