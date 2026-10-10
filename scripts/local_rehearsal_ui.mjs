// Local private data copy only. No env file or production API is loaded.
import {createServer} from '../frontend/node_modules/vite/dist/node/index.js';
import {fileURLToPath} from 'node:url';
const root=fileURLToPath(new URL('../frontend/',import.meta.url));
const base='http://127.0.0.1:5198';
const server=await createServer({root,configFile:fileURLToPath(new URL('../frontend/vite.config.js',import.meta.url)),envDir:false,
  define:{'import.meta.env.VITE_API_BASE_URL':JSON.stringify(base)},
  plugins:[{name:'local-rehearsal-label',transformIndexHtml(html){return html.replace('<title>','<title>[로컬 연습] ').replace('<body>',`<body><aside role="note" style="position:sticky;top:0;z-index:10000;background:#713f12;color:#fff;padding:12px 16px;font:14px system-ui;line-height:1.6;text-align:center">로컬 연습 · 운영 DB 복사본<br>입력·수정은 이 PC의 복사본에만 반영됩니다. 시세·환율은 복사된 값으로 고정됩니다.</aside>`);}}],
  server:{host:'127.0.0.1',port:5198,strictPort:true,proxy:{'/api':{target:'http://127.0.0.1:8568'},'/local-rehearsal':{target:'http://127.0.0.1:8568'}}}});
await server.listen();server.printUrls();
process.on('SIGINT',async()=>{await server.close();process.exit(0);});
process.on('SIGTERM',async()=>{await server.close();process.exit(0);});
