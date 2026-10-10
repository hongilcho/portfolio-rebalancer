"""Reset rehearsal into a NEW local DB from the saved archive. No production IO."""
from datetime import datetime,timezone
import hashlib,json,subprocess
from pathlib import Path
import psycopg2
from psycopg2 import sql
from clone_local_rehearsal import ROOT,BIN,LOCAL,pg_environment,fingerprint


def main():
    pointer=ROOT/'backups/local_rehearsal/current.json'
    info=json.loads(pointer.read_text(encoding='utf-8'))
    directory=Path(info['directory'])
    if not directory.is_absolute():directory=ROOT/directory
    directory=directory.resolve()
    if not directory.is_relative_to((ROOT/'backups/local_rehearsal').resolve()):raise RuntimeError('Archive must be inside ignored rehearsal storage')
    metadata=json.loads((directory/'metadata.json').read_text(encoding='utf-8'))
    archive=directory/'application.dump'
    if hashlib.sha256(archive.read_bytes()).hexdigest()!=metadata['archive_sha256']:raise RuntimeError('Archive integrity check failed')
    name='portfolio_rehearsal_'+datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S_%f')
    admin=psycopg2.connect(**LOCAL,dbname='postgres');admin.autocommit=True
    try:
        with admin.cursor() as c:c.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(name)))
    finally:admin.close()
    with psycopg2.connect(**LOCAL,dbname=name) as conn,conn.cursor() as c:
        c.execute("SELECT count(*) FROM information_schema.tables WHERE table_schema='public'")
        if c.fetchone()[0]!=0:raise RuntimeError('New local DB must be empty')
        c.execute('DROP SCHEMA public')
    with (directory/(name+'.restore.log')).open('wb') as log:
        subprocess.run([str(BIN/'pg_restore.exe'),'--no-password','--no-owner','--no-privileges','--exit-on-error','--single-transaction','--dbname='+name,str(archive)],env=pg_environment({**LOCAL,'dbname':name}),stdout=log,stderr=log,check=True,timeout=180)
    with psycopg2.connect(**LOCAL,dbname=name) as conn,conn.cursor() as c:
        for key,value in metadata['serialization'].items():c.execute('SELECT set_config(%s,%s,true)',(key,value))
        for key,expected in metadata['tables'].items():
            if fingerprint(c,*key.split('.'))!=expected:raise RuntimeError('Restored data verification failed')
    info.update(database=name,reset_at_utc=datetime.now(timezone.utc).isoformat())
    pointer.write_text(json.dumps(info,indent=2),encoding='utf-8')
    print('New local rehearsal restored and verified. Previous exercise DB retained.')
    print('No production connection was opened.')

if __name__=='__main__':
    try:main()
    except Exception as error:print('Local reset stopped:',type(error).__name__);raise SystemExit(1)
