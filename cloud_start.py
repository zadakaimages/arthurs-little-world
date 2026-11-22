"""Cloud entrypoint: public bind, persistent SQLite, required owner secret."""
import os
from pathlib import Path
os.environ['ARTHUR_HOST']='0.0.0.0'
os.environ['ARTHUR_PORT']=os.environ.get('PORT','8080')
os.environ['ARTHUR_DB']=os.environ.get('ARTHUR_DB','/data/arthur.sqlite3')
Path(os.environ['ARTHUR_DB']).parent.mkdir(parents=True,exist_ok=True)
if len(os.environ.get('ARTHUR_OWNER_TOKEN',''))<24:
    raise SystemExit('Set a secret ARTHUR_OWNER_TOKEN of at least 24 characters in Railway Variables.')
import server
server.main()
