import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {createHash} from 'node:crypto';
import {fileURLToPath} from 'node:url';
import React from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
import {createServer} from 'vite';
import {tradeFormCases} from './fixtures/tradeFormCases.js';
const baseline=JSON.parse(await readFile(new URL('./fixtures/tradeFormBeforeMaintenance.json',import.meta.url),'utf8'));
const server=await createServer({root:fileURLToPath(new URL('../',import.meta.url)),envDir:false,configFile:false,logLevel:'error',cacheDir:'node_modules/.vite-test-trade-form-maintenance',server:{middlewareMode:true,watch:null,hmr:false,ws:false}});
try{
 const Form=(await server.ssrLoadModule('/src/components/Tab4History/TradeBatchForm.jsx')).default;
 for(const [name,props] of tradeFormCases)test(`trade form retains exact desktop/mobile markup: ${name}`,()=>{
  const html=renderToStaticMarkup(React.createElement(Form,props));
  assert.equal(createHash('sha256').update(html).digest('hex'),baseline.sha256[name]);
 });
}finally{await server.close();}
