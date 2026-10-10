// Dedicated synthetic UI runner. No production configuration or env files.
import {createServer} from '../frontend/node_modules/vite/dist/node/index.js';
import {fileURLToPath} from 'node:url';
const frontend=fileURLToPath(new URL('../frontend/',import.meta.url));
const server=await createServer({
  root:frontend, configFile:fileURLToPath(new URL('../frontend/vite.config.js',import.meta.url)),
  envDir:false,
  define:{'import.meta.env.VITE_API_BASE_URL':JSON.stringify('http://127.0.0.1:5197')},
  server:{host:'127.0.0.1',port:5197,strictPort:true,
    proxy:{'/api':{target:'http://127.0.0.1:8571'},
           '/qa':{target:'http://127.0.0.1:8571'}}},
});
await server.listen();
server.printUrls();
process.on('SIGINT',async()=>{await server.close();process.exit(0);});
process.on('SIGTERM',async()=>{await server.close();process.exit(0);});
