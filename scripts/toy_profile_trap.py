"""Toy of the profile-environment config trap. Stdlib only."""
import json, os, pathlib, subprocess, sys, tempfile

CODE = r'''
import json, os, pathlib
def app_home():
    return pathlib.Path(os.environ.get("APP_HOME") or pathlib.Path.home() / ".app")
def fleet_root():
    h = app_home()
    return h.parent.parent if h.parent.name == "profiles" else h
def load_config():                      # reads the CURRENT profile's file; missing keys -> {}
    p = app_home() / "config.json"
    return json.loads(p.read_text()) if p.exists() else {}
def reviewer_buggy(assignee):
    return (load_config().get("reviewer_map") or {}).get(assignee)
def reviewer_fixed(assignee):
    p = fleet_root() / "config.json"
    cfg = json.loads(p.read_text()) if p.exists() else load_config()
    return (cfg.get("reviewer_map") or {}).get(assignee)
def gate(assignee):                     # fail-open: no reviewer configured => exempt
    return "allow(exempt)" if reviewer_buggy(assignee) is None else "block(needs review)"
def gate_fixed(assignee):
    return "allow(exempt)" if reviewer_fixed(assignee) is None else "block(needs review)"
import sys; print(sys.argv[1], gate("worker-a"), gate_fixed("worker-a"))
'''
with tempfile.TemporaryDirectory() as td:
    root = pathlib.Path(td) / ".app"
    (root / "profiles" / "worker-a").mkdir(parents=True)
    (root / "config.json").write_text(json.dumps({"reviewer_map": {"worker-a": "reviewer-b"}}))
    (root / "profiles" / "worker-a" / "config.json").write_text("{}")
    for label, home in (("default-home", root), ("profile-home", root / "profiles" / "worker-a")):
        env = dict(os.environ, APP_HOME=str(home))
        print(subprocess.run([sys.executable, "-c", CODE, label], env=env, capture_output=True, text=True).stdout.strip())
