"""Configure Arthur's model connection locally. Keys never enter the game page."""
import argparse
import getpass
import os
from pathlib import Path
import re
import secrets
import tempfile
from settings import SETTINGS_FILE, read_settings


def write_settings(values,path=SETTINGS_FILE):
    path=Path(path)
    descriptor,name=tempfile.mkstemp(prefix='.arthur-settings-',dir=path.parent)
    try:
        os.chmod(name,0o600)
        with os.fdopen(descriptor,'w',encoding='utf-8') as stream:
            stream.write('# Private Arthur settings. Do not share this file.\n')
            for key,value in values.items():
                if '\n' in str(value) or '\r' in str(value):raise ValueError('A setting must occupy one line.')
                stream.write(f'{key}={value}\n')
        os.replace(name,path)
    finally:
        Path(name).unlink(missing_ok=True)


def main():
    parser=argparse.ArgumentParser(description='Connect Arthur to an OpenAI API model. API use is billed separately by your API account.')
    parser.add_argument('--share',action='store_true',help='Also enable LAN viewing and create a private owner access code for your phone.')
    parser.add_argument('--skip-ai','--local-only',dest='skip_ai',action='store_true',help='Skip the API prompts, retaining any existing model configuration.')
    args=parser.parse_args()
    values=read_settings()
    print('Arthur’s conversation setup')
    print('Use an OpenAI API key from your own account. It stays on this computer.')
    print('The game sends your messages, relevant saved memories, and world context to the model.')
    if not args.skip_ai:
        key=getpass.getpass('API key (hidden; Enter keeps an existing key): ').strip()
        if key:
            if len(key)<20 or len(key)>1000 or any(c.isspace() for c in key):parser.error('That key format is not valid. Nothing was saved.')
            values['OPENAI_API_KEY']=key
        if not values.get('OPENAI_API_KEY') and not os.environ.get('OPENAI_API_KEY'):
            print('No API key configured. Arthur will use local conversation and autonomous behavior.')
        model=input('Model [gpt-6.1-terra]: ').strip() or values.get('ARTHUR_MODEL','gpt-6.1-terra')
        if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._:-]{0,99}',model) or model.startswith('sk-'):parser.error('Use a model ID, not an API key or URL.')
        values['ARTHUR_MODEL']=model
    values.setdefault('ARTHUR_AI_AUTONOMY','1')
    values.setdefault('ARTHUR_THINK_INTERVAL','180')
    values.setdefault('ARTHUR_MAX_AI_CALLS_PER_HOUR','40')
    if args.share:
        values['ARTHUR_HOST']='0.0.0.0'
        if len(values.get('ARTHUR_OWNER_TOKEN',''))<24:values['ARTHUR_OWNER_TOKEN']=secrets.token_urlsafe(32)
    write_settings(values)
    print('Saved. Restart Arthur with: python3 server.py')
    print('The connection is not verified until a model reply succeeds. No API request was made by setup.')
    if args.share:
        print('\nOn your phone, open the computer’s local IP on port 8765, then expand Owner access.')
        print('Private owner access code (keep this to yourself):')
        print(values['ARTHUR_OWNER_TOKEN'])
        print('Other visitors can watch, but cannot read your conversations or control Arthur.')


if __name__=='__main__':main()
