"""Build and verify a diagnostic-only overlay; never deploy or read secrets."""
import ast
import difflib
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import re
import uuid
import zipfile

ROOT=Path(__file__).resolve().parents[1]
BASE='7efe40fef908744872966864c17dd0a8bc595c01'
NEW_FILES=('logic/cma_diagnostics.py','backend/routers/cma_diagnostics.py','data/cma_nh.py')
FILES=(*NEW_FILES,'data/nh_api.py','backend/main.py')


def blob(name):return subprocess.check_output(['git','show',BASE+':'+name],cwd=ROOT).decode('utf-8')
def sha(raw):return hashlib.sha256(raw).hexdigest()


def build():
    assert subprocess.check_output(['git','branch','--show-current'],cwd=ROOT,text=True).strip()=='codex/cma-interest'
    out=ROOT/'backups/cma-final-local-20261015'/('readonly-bundle-'+uuid.uuid4().hex)
    out.mkdir(parents=True)
    texts={name:(ROOT/name).read_text(encoding='utf-8') for name in NEW_FILES}
    old_nh=blob('data/nh_api.py')
    anchor='''return {
                "deposit_krw": deposit,
                "holdings": holdings
            }, None'''
    tree=ast.parse(old_nh)
    method=next(n for n in ast.walk(tree) if isinstance(n,ast.FunctionDef) and n.name=='fetch_account_balance')
    lines=old_nh.splitlines(True)
    domestic=''.join(lines[method.lineno-1:method.end_lineno])
    assert domestic.count(anchor)==1,'Domestic balance anchor changed; review new deployed base'
    replacement=anchor.replace('"holdings": holdings','"holdings": holdings,\n                "cma_diagnostics": self._cma_diagnostics(data)')
    nh=''.join(lines[:method.lineno-1])+domestic.replace(anchor,replacement)+''.join(lines[method.end_lineno:])
    marker='    def fetch_overseas_account_balance(self, account_no: str):'
    assert nh.count(marker)==1
    nh=nh.replace(marker,'''    @staticmethod
    def _cma_diagnostics(data):
        from logic.cma_diagnostics import balance_diagnostics
        return balance_diagnostics(data)

'''+marker)
    texts['data/nh_api.py']=nh
    old_main=blob('backend/main.py')
    marker='app.include_router(sync.router)'
    assert old_main.count(marker)==1
    texts['backend/main.py']='from backend.routers import cma_diagnostics\n'+old_main.replace(marker,marker+'\napp.include_router(cma_diagnostics.router)')
    patch=[];manifest=dict(base_commit=BASE,profile_verified=False,
        flags={'CMA_DIAGNOSTICS_ENABLED':'1','CMA_INTEREST_ENABLED':'0','CMA_INTEREST_WRITES_ENABLED':'0'},
        approved_for_execution=False,files={},tests={})
    check=out/'check';check.mkdir()
    for name,text in texts.items():
        ast.parse(text)
        old=blob(name) if name not in NEW_FILES else ''
        target=out/'payload'/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_text(text,encoding='utf-8',newline='\n')
        manifest['files'][name]={'before_sha256':sha(old.encode()) if old else None,'after_sha256':sha(text.encode())}
        if old:manifest['files'][name]['before_crlf_sha256']=sha(old.replace('\n','\r\n').encode())
        if old:
            target=check/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_text(old,encoding='utf-8',newline='\n')
        patch.append('diff --git a/'+name+' b/'+name+'\n')
        if not old:patch.append('new file mode 100644\n')
        patch.extend(difflib.unified_diff(old.splitlines(True),text.splitlines(True),fromfile='a/'+name if old else '/dev/null',tofile='b/'+name))
    diff=out/'readonly.patch';diff.write_text(''.join(patch),encoding='utf-8',newline='\n')
    relative=check.relative_to(ROOT).as_posix()
    subprocess.run(['git','-c','core.autocrlf=false','apply','--check','--directory='+relative,str(diff)],cwd=ROOT,check=True,capture_output=True)
    subprocess.run(['git','-c','core.autocrlf=false','apply','--directory='+relative,str(diff)],cwd=ROOT,check=True,capture_output=True)
    for name,text in texts.items():assert sha((check/name).read_bytes())==sha(text.encode())
    # These modules must be absent even if the full CMA worktree contains them.
    forbidden=('cma_interest','cma_policy','portfolio_cma','CMA_INTEREST_ENABLED','cma_evidence')
    assert all(word not in texts['backend/main.py']+texts['data/nh_api.py'] for word in forbidden)
    program='''import os,sys
sys.path.insert(0,sys.argv[1])
os.environ['PORTFOLIO_LOAD_CONFIG_FILES']='0'
os.environ['CMA_DIAGNOSTICS_ENABLED']='0'
import requests
requests.sessions.Session.request=lambda *a,**k: (_ for _ in ()).throw(AssertionError('No external IO'))
from fastapi import FastAPI
from fastapi.testclient import TestClient
from backend.routers import cma_diagnostics as r
from logic.cma_diagnostics import balance_diagnostics
app=FastAPI();app.include_router(r.router);client=TestClient(app)
assert client.post('/api/cma-diagnostics/p/a').status_code==409
os.environ['CMA_DIAGNOSTICS_ENABLED']='1'
r.probe=lambda *a,**k: {'diagnostics':balance_diagnostics({'Output_0':{'dca':0,'drn_pbl_amt':123},'Output_1':[]}), 'ledger_write_performed':False}
value=client.post('/api/cma-diagnostics/p/a').json()
assert value['diagnostics']['cash_fields']['drn_pbl_amt']['value']=='123'
assert value['ledger_write_performed'] is False
print('diagnostic-only imports, feature-off guard and synthetic HTTP: passed')
'''
    result=subprocess.run([sys.executable,'-I','-B','-c',program,str(check)],cwd=check,capture_output=True,text=True,check=True)
    manifest['tests']=dict(patch_check=True,patch_applied_to_synthetic_base=True,payload_hashes_match=True,
        no_interest_or_schema_code=True,isolated_diagnostic_http=True,external_calls=0)
    operator=texts['logic/cma_diagnostics.py']+'\n'+(ROOT/'scripts/cma_diagnostic_reader.py').read_text(encoding='utf-8')
    ast.parse(operator)
    operator_path=out/'operator-readonly.py';operator_path.write_text(operator,encoding='utf-8',newline='\n')
    manifest['operator_sha256']=sha(operator.encode())
    (out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
    archive=out/('cma-readonly-'+BASE[:7]+'.zip')
    with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as zipped:
        for file in [out/'manifest.json',diff,operator_path,*((out/'payload'/name) for name in FILES)]:
            zipped.write(file,file.relative_to(out))
    with zipfile.ZipFile(archive) as zipped:assert zipped.testzip() is None
    evidence=dict(bundle=str(archive.relative_to(ROOT)),sha256=sha(archive.read_bytes()),manifest=manifest)
    (ROOT/'docs/cma-readonly-bundle-evidence.json').write_text(json.dumps(evidence,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'bundle':str(archive),'sha256':evidence['sha256'],'files':list(FILES),'tests':manifest['tests']}))


if __name__=='__main__':
    if len(sys.argv)==3 and sys.argv[1]=='--base':
        if not re.fullmatch('[a-f0-9]{40}',sys.argv[2]):raise SystemExit('Exact reviewed base commit required')
        BASE=sys.argv[2]
    elif len(sys.argv)!=1:raise SystemExit('Usage: prepare_cma_readonly_bundle.py [--base <commit>]')
    build()
