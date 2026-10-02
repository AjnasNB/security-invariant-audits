/** Persistent upfront reservations; auth headers never enter stored evidence. */
import assert from 'node:assert/strict';
import {promises as fs} from 'node:fs';
import path from 'node:path';
import {createHash} from 'node:crypto';

type Rates={input:number;cached:number;write:number;output:number};
type Model={id:string;deployment:string;model:string;version:string;protocol:string;endpoint:string;rates:Rates};
export class MultiModelBudget {
  private original=globalThis.fetch;
  private selected?:Model;
  private directory:string;
  private limit:number;
  private trajectoryInputEstimate=0;
  attempts=0;
  reference=0;
  pending:any[]=[];
  records:any[]=[];
  perModel:Record<string,any>={};
  constructor(readonly root:string,readonly protocol:any,cap?:number){
    this.directory=root;this.limit=cap??protocol.limits.total_reference_cap_usd;
  }
  select(model:Model,directory:string){
    assert.equal(this.pending.length,0,'Previous inference request is still pending');
    this.selected=model;this.directory=directory;
    this.trajectoryInputEstimate=0;
    this.perModel[model.id]??={requests:0,attempts:0,input_tokens:0,output_tokens:0,cached_tokens:0,
      cache_write_tokens:0,reference_estimate_usd:0,unknown_usage_attempts:0};
  }
  async save(){
    await fs.writeFile(path.join(this.root,'usage.json'),JSON.stringify({
      http_attempts:this.attempts,reference_estimate_usd:this.reference,per_model:this.perModel,
      pending_requests:this.pending,total_reference_cap_usd:this.limit,
      pricing:'Verified public Standard reference rates; not account-specific Azure invoice',
      cache_writes:'Replace uncached input at 1.25x; Anthropic cache tokens reported separately.',
    },null,2)+'\n');
  }
  install(){
    globalThis.fetch=async(input:any,init?:RequestInit)=>{
      const url=String(input);
      if(!url.endsWith('/responses')&&!url.endsWith('/messages'))return this.original(input,init);
      const model=this.selected;assert.ok(model,'No selected research model');
      const body=JSON.parse(String(init?.body));assert.equal(body.model,model.deployment);
      assert.ok(url.startsWith(model.endpoint+'/'),'Provider endpoint mismatch');
      if(model.protocol==='responses')body.reasoning={...(body.reasoning??{}),effort:'low'};
      else body.output_config={...(body.output_config??{}),effort:'low'};
      const output=body.max_output_tokens??body.max_tokens;
      assert.ok(output>0&&output<=this.protocol.limits.max_output_tokens_per_request);
      const encoded=JSON.stringify(body),inputEstimate=Math.ceil(Buffer.byteLength(encoded)/2);
      assert.ok(inputEstimate<=this.protocol.limits.max_request_input_estimate,'Request context cap exceeded');
      // Explicit v2 opt-in: v1 declared this ceiling but did not enforce it.
      // Historical v1 is retained; do not silently change its replay semantics.
      if(this.protocol.limits.enforce_trajectory_input_estimate){
        assert.ok(this.trajectoryInputEstimate+inputEstimate<=this.protocol.limits.max_input_tokens_per_trajectory,
          'Frozen trajectory input-estimate budget reached');
      }
      const rates=model.rates;
      // Long input is reserved at the conservative long-context input rate.
      const multiplier=inputEstimate>272000?2:1;
      const reserved=(inputEstimate*Math.max(rates.input,rates.write)*multiplier+output*rates.output*(multiplier>1?1.5:1))/1e6;
      const usage=this.perModel[model.id];
      if(this.attempts>=this.protocol.limits.max_model_requests||this.reference+reserved>this.limit
        ||usage.reference_estimate_usd+reserved>this.protocol.limits.reference_cap_per_model_usd){
        throw new Error('Frozen multi-model reference/request budget reached');
      }
      const number=++this.attempts,directory=this.directory;
      this.trajectoryInputEstimate+=inputEstimate;
      usage.attempts++;this.reference+=reserved;usage.reference_estimate_usd+=reserved;
      this.pending.push({request_number:number,model:model.id,reserved_usd:reserved});
      await fs.writeFile(path.join(directory,`provider-${number}-request.json`),JSON.stringify(body,null,2)+'\n');
      await this.save();
      const started=new Date().toISOString();let response:Response,raw:string;
      try{
        response=await this.original(input,{...init,body:encoded});
        raw=await response.text();
      }catch(error){
        usage.unknown_usage_attempts++;this.pending=[];
        await fs.writeFile(path.join(directory,`provider-${number}-metadata.json`),JSON.stringify({
          number,model_id:model.id,started_at:started,usage_unknown:true,reference_reservation_usd:reserved,
          request_status:'transport_failed',error:'Transport failed; reservation retained',
        },null,2)+'\n');await this.save();throw error;
      }
      await fs.writeFile(path.join(directory,`provider-${number}-response.sse`),raw);
      const events=raw.replaceAll('\r\n','\n').split('\n\n').flatMap(block=>{
        const value=block.split('\n').filter(line=>line.startsWith('data:')).map(line=>line.slice(5).trimStart()).join('\n');
        if(!value||value==='[DONE]')return [];try{return [JSON.parse(value)];}catch{return [];}
      });
      let served:any,reported:any,status:any,complete=false;
      if(model.protocol==='responses'){
        const done=events.find(event=>['response.completed','response.incomplete','response.failed'].includes(event.type))?.response;
        served=done?.model;reported=done?.usage;status=done?.status;complete=status==='completed';
      }else{
        const beginning=events.find(event=>event.type==='message_start')?.message;
        const ending=events.find(event=>event.type==='message_delta');
        served=beginning?.model;reported=beginning?.usage&&ending?.usage?{...beginning.usage,...ending.usage}:undefined;
        status=ending?.delta?.stop_reason;complete=events.some(event=>event.type==='message_stop')&&status!=='max_tokens';
      }
      let cost=reserved;
      if(reported){
        const cached= model.protocol==='messages'?(reported.cache_read_input_tokens??0):(reported.input_tokens_details?.cached_tokens??0);
        const written=model.protocol==='messages'?(reported.cache_creation_input_tokens??0):(reported.input_tokens_details?.cache_write_tokens??0);
        const inputs=model.protocol==='messages'?(reported.input_tokens??0)+cached+written:(reported.input_tokens??0);
        const outputs=reported.output_tokens??0;
        const inputFactor=inputs>272000&&model.protocol==='responses'?2:1;
        cost=((inputs-cached-written)*rates.input*inputFactor+cached*rates.cached*inputFactor+
          written*rates.write*inputFactor+outputs*rates.output*(inputFactor>1?1.5:1))/1e6;
        Object.assign(usage,{requests:usage.requests+1,input_tokens:usage.input_tokens+inputs,
          output_tokens:usage.output_tokens+outputs,cached_tokens:usage.cached_tokens+cached,
          cache_write_tokens:usage.cache_write_tokens+written});
      }else if(response.status===429||response.status===400||response.status===403||response.status===404){
        cost=0;
      }else{usage.unknown_usage_attempts++;}
      this.reference+=cost-reserved;usage.reference_estimate_usd+=cost-reserved;this.pending=[];
      const metadata={number,model_id:model.id,deployment:model.deployment,served_model:served,
        started_at:started,completed_at:new Date().toISOString(),http_status:response.status,status,
        response_completed:complete,usage:reported,usage_unknown:!reported,
        reference_cost_usd:cost,reference_reservation_usd:reserved,
        request_sha256:createHash('sha256').update(encoded).digest('hex'),
        response_sha256:createHash('sha256').update(raw).digest('hex')};
      this.records.push(metadata);
      await fs.writeFile(path.join(directory,`provider-${number}-metadata.json`),JSON.stringify(metadata,null,2)+'\n');
      await this.save();
      if(served)assert.ok([model.deployment,model.model,model.model+'-'+model.version].includes(served),
        'Unexpected served model identity');
      return new Response(raw,{status:response.status,statusText:response.statusText,headers:response.headers});
    };
  }
  restore(){globalThis.fetch=this.original;}
}
