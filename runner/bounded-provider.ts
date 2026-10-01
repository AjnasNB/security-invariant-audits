/** Shared paid-call cap. No headers or provider credentials are persisted. */
import assert from 'node:assert/strict';
import {promises as fs} from 'node:fs';
import path from 'node:path';
import {createHash} from 'node:crypto';

export class BoundedProvider {
  private original=globalThis.fetch;
  private directory:string;
  attempts=0;
  referenceDebit=0;
  conservativeDebit=0;
  unknownUsage=0;
  usage={requests:0,input_tokens:0,output_tokens:0,cached_tokens:0,cache_write_tokens:0};
  records:any[]=[];
  constructor(readonly root:string,readonly deployment:string,readonly limits:{
    max_http_attempts:number;reference_estimate_cap_usd:number;conservative_debit_cap_usd:number;
  }) { this.directory=root; }
  select(directory:string){this.directory=directory;}
  async save(){
    await fs.writeFile(path.join(this.root,'usage.json'),JSON.stringify({
      ...this.usage,http_attempts:this.attempts,reference_estimate_usd:this.referenceDebit,
      conservative_debit_usd:this.conservativeDebit,unknown_usage_attempts:this.unknownUsage,
      limits:this.limits,pricing:'Public GPT-6.1 Sol Standard estimate, not Azure invoice',
      rates_per_million:{input:2,cached:.1,output:10,cache_write:2.5},
      assumption:'Reported cache-write tokens replace ordinary uncached input at 1.25x; no double charge.',
    },null,2)+'\n');
  }
  install(){
    globalThis.fetch=async(input:any,init?:RequestInit)=>{
      if(!String(input).endsWith('/responses'))return this.original(input,init);
      const body=JSON.parse(String(init?.body));
      assert.equal(body.model,this.deployment,'Do not substitute the requested model.');
      assert.equal(body.reasoning?.effort,'low');
      const inputEstimate=Math.ceil(Buffer.byteLength(JSON.stringify(body))/2);
      const output=body.max_output_tokens;
      assert.ok(output>0&&output<=1536);assert.ok(inputEstimate<=16000);
      const refReservation=(inputEstimate*2.5+output*10)/1e6;
      const planningReservation=(inputEstimate*4+output*20)/1e6;
      if(this.attempts>=this.limits.max_http_attempts
         ||this.referenceDebit+refReservation>this.limits.reference_estimate_cap_usd
         ||this.conservativeDebit+planningReservation>this.limits.conservative_debit_cap_usd){
        throw new Error('Frozen experiment budget cannot cover the next model request.');
      }
      const number=++this.attempts,directory=this.directory;
      await fs.writeFile(path.join(directory,`provider-${number}-request.json`),JSON.stringify(body,null,2)+'\n');
      let response:Response;
      try{response=await this.original(input,init);}
      catch(error){
        this.referenceDebit+=refReservation;this.conservativeDebit+=planningReservation;this.unknownUsage++;
        await this.save();throw error;
      }
      const raw=await response.text();
      await fs.writeFile(path.join(directory,`provider-${number}-response.sse`),raw);
      const events=raw.replaceAll('\r\n','\n').split('\n\n').flatMap(block=>{
        const data=block.split('\n').filter(line=>line.startsWith('data:')).map(line=>line.slice(5).trimStart()).join('\n');
        if(!data||data==='[DONE]')return [];try{return [JSON.parse(data)];}catch{return [];}
      });
      const completed=events.find(event=>['response.completed','response.incomplete'].includes(event.type))?.response;
      const usage=completed?.usage;
      let referenceCost=0;
      if(usage){
        const inputs=usage.input_tokens??0,outputs=usage.output_tokens??0;
        const cached=Math.min(inputs,usage.input_tokens_details?.cached_tokens??0);
        const written=Math.min(inputs-cached,usage.input_tokens_details?.cache_write_tokens??0);
        referenceCost=((inputs-cached-written)*2+cached*.1+written*2.5+outputs*10)/1e6;
        this.referenceDebit+=referenceCost;this.conservativeDebit+=(inputs*4+outputs*20)/1e6;
        this.usage.requests++;this.usage.input_tokens+=inputs;this.usage.output_tokens+=outputs;
        this.usage.cached_tokens+=cached;this.usage.cache_write_tokens+=written;
      }else if(response.status!==429){
        this.referenceDebit+=refReservation;this.conservativeDebit+=planningReservation;this.unknownUsage++;
      }
      const metadata={request_number:number,http_status:response.status,model:completed?.model,
        response_id:completed?.id,status:completed?.status,usage,
        incomplete_details:completed?.incomplete_details,reference_cost_usd:referenceCost,
        response_sha256:createHash('sha256').update(raw).digest('hex'),
        usage_unknown:!usage,case_directory:path.relative(this.root,directory)};
      this.records.push(metadata);
      await fs.writeFile(path.join(directory,`provider-${number}-metadata.json`),JSON.stringify(metadata,null,2)+'\n');
      await this.save();
      if(completed?.model)assert.ok(completed.model===this.deployment||completed.model==='gpt-6.1-sol',
        'Unexpected served model identity; check the recorded deployment mapping.');
      return new Response(raw,{status:response.status,statusText:response.statusText,headers:response.headers});
    };
  }
  restore(){globalThis.fetch=this.original;}
}
