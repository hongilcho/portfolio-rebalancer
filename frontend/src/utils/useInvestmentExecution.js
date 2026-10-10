import {useCallback,useEffect,useRef,useState} from 'react';
import {api} from './api';
export function useInvestmentExecution(portfolioId,active,authenticated,refreshKey) {
  const [state,setState]=useState({scope:null,cycle:null,history:[],plans:[],loading:false,error:'',available:null});
  const scope=useRef(portfolioId);scope.current=portfolioId;
  const sequence=useRef(0),seen=useRef(false);
  const refresh=useCallback(async()=>{
    if (!authenticated || !seen.current || ['all','crypto'].includes(portfolioId)) return;
    const request=++sequence.current;
    setState(old=>({...old,loading:true,error:''}));
    try {
      if ((await api.getInvestmentCapabilities()).investment_protocol!==1) throw Object.assign(new Error('투자 실행 지원 버전이 필요합니다.'),{status:404});
      const [data,plans]=await Promise.all([api.getInvestments(portfolioId),api.getInvestmentPlans(portfolioId)]);
      if(request!==sequence.current || scope.current!==portfolioId)return;
      setState({scope:portfolioId,...data,plans:plans.plans,loading:false,error:'',available:true});
    } catch(error) {
      if(request!==sequence.current || scope.current!==portfolioId)return;
      setState(old=>({...((old.scope===portfolioId)?old:{cycle:null,history:[],plans:[],available:null}),scope:portfolioId,loading:false,error:error.status===404?'Render 배포가 완료되면 투자 실행을 사용할 수 있습니다. 기존 5번 기록 입력은 계속 사용할 수 있습니다.':error.message,available:error.status===404?false:(old.scope===portfolioId?old.available:null)}));
      throw error;
    }
  },[portfolioId,authenticated]);
  useEffect(()=>{
    if(!active || !authenticated)return;
    seen.current=true;
    refresh().catch(()=>{});
    const counter=sequence;
    return()=>{counter.current++;};
  },[active,authenticated,portfolioId,refreshKey,refresh]);
  return {...(state.scope===portfolioId?state:{cycle:null,history:[],plans:[],loading:active,error:'',available:null}),refresh};
}
