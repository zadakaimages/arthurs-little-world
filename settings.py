"""Load a small local settings file without evaluating shell code."""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SETTINGS_FILE = ROOT / 'arthur.env'
ALLOWED = {'OPENAI_API_KEY','ARTHUR_MODEL','ARTHUR_HOST','ARTHUR_PORT','ARTHUR_DB',
           'ARTHUR_OWNER_TOKEN','ARTHUR_AI_AUTONOMY','ARTHUR_THINK_INTERVAL',
           'ARTHUR_MAX_AI_CALLS_PER_HOUR'}


def read_settings(path=SETTINGS_FILE):
    result = {}
    if not Path(path).is_file():return result
    for line in Path(path).read_text(encoding='utf-8').splitlines():
        line=line.strip()
        if not line or line.startswith('#') or '=' not in line:continue
        name,value=line.split('=',1);name=name.strip();value=value.strip()
        if name in ALLOWED and '\x00' not in value:result[name]=value
    return result


def load_settings(path=SETTINGS_FILE):
    for name,value in read_settings(path).items():os.environ.setdefault(name,value)


def bounded_int(name,default,minimum,maximum):
    try:return max(minimum,min(maximum,int(os.environ.get(name,str(default)))))
    except (ValueError,TypeError):return default
