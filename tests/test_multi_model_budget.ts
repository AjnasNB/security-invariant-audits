/** Offline fake transports only. Real auth/network are never used. */
import assert from 'node:assert/strict';
import {test} from 'node:test';
import {promises as fs} from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {MultiModelBudget} from '../runner/multi-model-budget';

const model={id:'test',deployment:'test-deployment',model:'test-model',version:'1',protocol:'responses',
  endpoint:'https://test.invalid',rates:{input:2,cached:.1,write:2.5,output:10}};
const specification={limits:{max_model_requests:4,max_output_tokens_per_request:32,
  max_request_input_estimate:10000,total_reference_cap_usd:1,reference_cap_per_model_usd:1}};
const body={model:model.deployment,input:[{role:'user',content:'Tidy it up.'}],max_output_tokens:16};
const fetchRequest=()=>fetch(model.endpoint+'/responses',{method:'POST',headers:{Authorization:'fake-unit-test-only'},
  body:JSON.stringify(body)});
const sse=(value:any)=>'data: '+JSON.stringify(value)+'\n\n';

async function setup(transport:typeof fetch,protocol:any=specification){
  const original=globalThis.fetch;
  const root=await fs.mkdtemp(path.join(os.tmpdir(),'ajnas-budget-unit-'));
  globalThis.fetch=transport;
  const budget=new MultiModelBudget(root,protocol);budget.select(model,root);budget.install();
  return {budget,root,restore:()=>{budget.restore();globalThis.fetch=original;}};
}

test('upfront reservation survives a transport failure without saving auth',async()=>{
  let root:string;
  const unit=await setup(async()=>{
    const saved=JSON.parse(await fs.readFile(path.join(root,'usage.json'),'utf8'));
    assert.equal(saved.pending_requests.length,1);assert.ok(saved.reference_estimate_usd>0);
    throw new Error('offline transport failure');
  });root=unit.root;
  try{
    await assert.rejects(fetchRequest(),/offline transport/);
    assert.equal(unit.budget.pending.length,0);assert.equal(unit.budget.perModel.test.unknown_usage_attempts,1);
    const request=await fs.readFile(path.join(root,'provider-1-request.json'),'utf8');
    assert.ok(!request.includes('fake-unit-test-only'));
    assert.ok(unit.budget.reference>0);
  }finally{unit.restore();}
});

test('reported cache input and writes replace, not double-charge, input',async()=>{
  const unit=await setup(async(_input,init)=>{
    const request=JSON.parse(String(init?.body));assert.equal(request.reasoning.effort,'low');
    return new Response(sse({type:'response.completed',response:{model:'test-model',status:'completed',
      usage:{input_tokens:100,output_tokens:2,input_tokens_details:{cached_tokens:60,cache_write_tokens:20}}}}));
  });
  try{
    await fetchRequest();
    assert.ok(Math.abs(unit.budget.reference-0.000116)<1e-12);
    assert.equal(unit.budget.perModel.test.input_tokens,100);
    assert.equal(unit.budget.pending.length,0);
  }finally{unit.restore();}
});

test('HTTP 429 records an attempt but no reported inference cost',async()=>{
  const unit=await setup(async()=>new Response('{"error":"rate limit"}',{status:429}));
  try{
    await fetchRequest();assert.equal(unit.budget.attempts,1);
    assert.equal(unit.budget.reference,0);assert.equal(unit.budget.perModel.test.requests,0);
  }finally{unit.restore();}
});

test('unexpected served model is retained and rejected',async()=>{
  const unit=await setup(async()=>new Response(sse({type:'response.completed',response:{
    model:'wrong-model',status:'completed',usage:{input_tokens:20,output_tokens:1}}})));
  try{
    await assert.rejects(fetchRequest(),/Unexpected served model/);
    assert.equal(unit.budget.records.length,1);assert.ok(unit.budget.reference>0);
  }finally{unit.restore();}
});

test('future strict trajectory guard stops before a second network call',async()=>{
  let calls=0;
  const estimate=Math.ceil(Buffer.byteLength(JSON.stringify({...body,reasoning:{effort:'low'}}))/2);
  const protocol={limits:{...specification.limits,enforce_trajectory_input_estimate:true,
    max_input_tokens_per_trajectory:estimate}};
  const unit=await setup(async()=>{
    calls++;return new Response(sse({type:'response.completed',response:{
      model:'test-model',status:'completed',usage:{input_tokens:10,output_tokens:1}}}));
  },protocol);
  try{
    await fetchRequest();await assert.rejects(fetchRequest(),/trajectory input-estimate/);
    assert.equal(calls,1);assert.equal(unit.budget.attempts,1);
  }finally{unit.restore();}
});
