"""Explicit opt-in LaunchAgent. Never installed by the normal installer."""
import argparse
import os
from pathlib import Path
import plistlib
import subprocess
import sys
from app import default_root

LABEL='local.canada-prediction-finder.paper'

def main():
    p=argparse.ArgumentParser();p.add_argument('action',choices=['enable','disable']);a=p.parse_args()
    if sys.platform!='darwin':raise SystemExit('Autostart is macOS-only.')
    target=Path.home()/'Library'/'LaunchAgents'/(LABEL+'.plist')
    domain='gui/'+str(os.getuid())
    # Only the single app-owned LaunchAgent is affected.
    subprocess.run(['launchctl','bootout',domain+'/'+LABEL],check=False,capture_output=True)
    if a.action=='disable':
        target.unlink(missing_ok=True);print('Login autostart disabled. Your ledger has not been deleted.');return
    root=Path(__file__).resolve().parent
    py=root/'.venv'/'bin'/'python'
    if not py.is_file():raise SystemExit('Run Install.command first.')
    data=default_root()/'paper';data.mkdir(parents=True,exist_ok=True)
    target.parent.mkdir(parents=True,exist_ok=True)
    agent={'Label':LABEL,'ProgramArguments':[str(py),str(root/'app.py'),'run'],
           'WorkingDirectory':str(root),'RunAtLoad':True,
           'KeepAlive':{'SuccessfulExit':False},'ThrottleInterval':60,
           'StandardOutPath':str(data/'launch-stdout.log'),'StandardErrorPath':str(data/'launch-stderr.log'),
           'EnvironmentVariables':{'PYTHONUNBUFFERED':'1'}}
    target.write_bytes(plistlib.dumps(agent));target.chmod(0o600)
    subprocess.run(['launchctl','bootstrap',domain,str(target)],check=True)
    print('Login autostart enabled for PAPER research only. Open http://127.0.0.1:8765 to view it.')
    print('Keep this application folder in place. Autostart does not prevent sleep.')

if __name__=='__main__':main()
