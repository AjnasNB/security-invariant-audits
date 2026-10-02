/** Exact archived-example questions, current Azure models, no answer in input. */
import assert from 'node:assert/strict';
import {promises as fs} from 'node:fs';
import path from 'node:path';
import {fileURLToPath,pathToFileURL} from 'node:url';
import {MultiModelBudget} from './multi-model-budget';

const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
const option=(name:string,fallback:string)=>process.argv.find(arg=>arg.startsWith(`--${name}=`))?.slice(name.length+3)??fallback;
const delta=option('delta-root',process.env.DELTA_ROOT??'');
const profileDirectory=option('profile',process.env.DELTA_LOCAL_PROFILE??(process.env.APPDATA?path.join(process.env.APPDATA,'Delta Harness'):''));
const output=option('output',path.join(root,'artifacts/private/hard-paper-models-v1'));
assert.ok(delta&&profileDirectory);
const protocol=JSON.parse(await fs.readFile(path.join(root,'protocols/hard-paper-models-v1.json'),'utf8'));
const settings=JSON.parse(await fs.readFile(path.join(profileDirectory,'workspace/state.json'),'utf8')).settings;
const providers=await import(pathToFileURL(path.join(delta,'src/core/providers.ts')).href);
await fs.mkdir(output,{recursive:false});
const writeJson=(file:string,data:any)=>fs.writeFile(file,JSON.stringify(data,null,2)+'\n');
await writeJson(path.join(output,'protocol.json'),protocol);
const budget=new MultiModelBudget(output,protocol);
const records:any[]=[];
try{
  budget.install();
  for(const [index,item] of protocol.schedule.entries()){
    const model=protocol.models.find((model:any)=>model.id===item.model_id);
    const question=protocol.questions.find((row:any)=>row.id===item.question_id);
    const directory=path.join(output,`${String(index+1).padStart(3,'0')}-${model.id}-${question.id.replace(':','-')}`);
    await fs.mkdir(directory);budget.select(model,directory);
    const provider={id:'paper-'+model.id,name:model.name,kind:model.protocol==='messages'?'azure-anthropic':'azure-openai',
      endpoint:model.endpoint,auth:'azure-cli',models:[{id:'primary',name:model.name,model:model.deployment,
        contextWindow:model.context_window,maxInputTokens:model.max_input_tokens,maxOutputTokens:128000,supportsTools:true}]};
    let text:string|null=null,error:string|null=null;
    const costBefore=budget.reference,usageBefore=structuredClone(budget.perModel[model.id]);
    try{
      const response=await providers.requestModel({model:provider.id+':primary',
        settings:{...settings,providers:[provider],maxOutputTokens:protocol.limits.max_output_tokens_per_request,
          modelTimeoutMs:70000},instructions:'You are a coding assistant.',
        input:[{role:'user',content:question.prompt}],tools:[],
        signal:AbortSignal.timeout(protocol.limits.wall_seconds_per_question*1000),onDelta:()=>{}});
      text=response.text;
    }catch(failure){error=(failure as Error).message;}
    const row={...item,scheduled_index:index+1,run_id:path.basename(directory),text,error,
      termination:error?'failed':'completed',reference_estimate_usd:budget.reference-costBefore,
      usage:Object.fromEntries(Object.keys(usageBefore).map(key=>[key,budget.perModel[model.id][key]-usageBefore[key]]))};
    records.push(row);await writeJson(path.join(directory,'answer.json'),row);
    await writeJson(path.join(output,'results.json'),{results:records});
    console.log(`${index+1}/${protocol.schedule.length} ${model.id}/${question.id}: ${error??text}`);
  }
}finally{budget.restore();await budget.save();}
await writeJson(path.join(output,'results.json'),{completed_at:new Date().toISOString(),results:records});
console.log(`Paper stage finished; reference estimate $${budget.reference.toFixed(6)}.`);
