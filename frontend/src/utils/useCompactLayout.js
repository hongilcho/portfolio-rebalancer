import {useEffect,useState} from 'react';
export function useCompactLayout(){
  const [compact,setCompact]=useState(()=>globalThis.matchMedia?.('(max-width: 768px)').matches ?? false);
  useEffect(()=>{const query=globalThis.matchMedia?.('(max-width: 768px)');if(!query)return;
    const update=()=>setCompact(query.matches);update();query.addEventListener('change',update);
    return()=>query.removeEventListener('change',update);
  },[]);
  return compact;
}
