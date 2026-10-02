/** Vague requests, fixed large context, actual Delta loop, independent executable judge. */
import assert from 'node:assert/strict';
import {promises as fs} from 'node:fs';
import path from 'node:path';
import {spawn} from 'node:child_process';
import {createHash} from 'node:crypto';
import {fileURLToPath,pathToFileURL} from 'node:url';
import {MultiModelBudget} from './multi-model-budget';

const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
const option=(name:string,fallback:string)=>process.argv.find(arg=>arg.startsWith(`--${name}=`))?.slice(name.length+3)??fallback;
const delta=option('delta-root',process.env.DELTA_ROOT??'');
const python=option('python',process.env.STUDY_PYTHON??'python');
const profileDirectory=option('profile',process.env.DELTA_LOCAL_PROFILE??(process.env.APPDATA?path.join(process.env.APPDATA,'Delta Harness'):''));
const output=option('output',path.join(root,'artifacts/private/hard-vague-context-v1'));
const mode=option('mode','study');
const registeredProtocol=option('protocol','');
const azurePython=option('azure-python','');
assert.ok(delta&&profileDirectory,'Set Delta source and local profile paths.');
assert.ok(['connection','study'].includes(mode));
await fs.mkdir(path.dirname(output),{recursive:true});await fs.mkdir(output,{recursive:false});
const hash=(value:string|Buffer)=>createHash('sha256').update(value).digest('hex');
const writeJson=async(file:string,value:any)=>{await fs.mkdir(path.dirname(file),{recursive:true});await fs.writeFile(file,JSON.stringify(value,null,2)+'\n');};
async function execute(command:string,args:string[],timeout=120000){
  return new Promise<{code:number;stdout:string;stderr:string}>((resolve,reject)=>{
    const child=spawn(command,args,{cwd:root,shell:false,windowsHide:true,stdio:['ignore','pipe','pipe'],
      env:{...process.env,PYTHONUTF8:'1',PYTHONDONTWRITEBYTECODE:'1'}});
    let stdout='',stderr='';const timer=setTimeout(()=>{child.kill();reject(new Error('Controller helper timed out'));},timeout);
    child.stdout.on('data',chunk=>{stdout+=chunk;});child.stderr.on('data',chunk=>{stderr+=chunk;});
    child.on('error',error=>{clearTimeout(timer);reject(error);});
    child.on('exit',code=>{clearTimeout(timer);resolve({code:code??-1,stdout,stderr});});
  });
}
async function py(args:string[],timeout=120000){
  const result=await execute(python,['-B',...args],timeout);
  if(result.code)throw new Error('Controller helper failed: '+result.stderr.slice(-1400));
  return JSON.parse(result.stdout);
}
const specification=registeredProtocol?JSON.parse(await fs.readFile(path.resolve(registeredProtocol),'utf8')):
  await py(['-c','import json;from hardstudy.protocol import protocol;print(json.dumps(protocol()))']);
await writeJson(path.join(output,'protocol.json'),specification);
const savedProfile=JSON.parse(await fs.readFile(path.join(profileDirectory,'workspace/state.json'),'utf8'));
const deploymentMap:any={};
for(const model of specification.models){
  const command=azurePython||'az',prefix=azurePython?['-IBm','azure.cli']:[];
  const checked=await execute(command,[...prefix,'cognitiveservices','account','deployment','show',
    '-g',model.group,'-n',model.account,'--deployment-name',model.deployment,
    '--query','{deployment:name,state:properties.provisioningState,model:properties.model}','-o','json'],45000);
  if(checked.code)throw new Error('Cannot verify Azure deployment '+model.id);
  const metadata=JSON.parse(checked.stdout);
  assert.equal(metadata.state,'Succeeded');assert.equal(metadata.model.name,model.model);
  assert.equal(metadata.model.version,model.version);
  deploymentMap[model.id]=metadata;
}
await writeJson(path.join(output,'deployment-map.json'),deploymentMap);
function settingsFor(model:any){
  const provider={id:'hard-'+model.id,name:model.name,kind:model.protocol==='messages'?'azure-anthropic':'azure-openai',
    endpoint:model.endpoint,auth:'azure-cli',models:[{id:'primary',name:model.name,model:model.deployment,
      contextWindow:model.context_window,maxInputTokens:model.max_input_tokens,maxOutputTokens:128000,supportsTools:true,
      inputPricePerMillion:model.rates.input,cachedInputPricePerMillion:model.rates.cached,
      outputPricePerMillion:model.rates.output}]};
  return {...savedProfile.settings,providers:[provider],maxSteps:specification.limits.max_steps_per_trajectory,
    maxOutputTokens:mode==='connection'?128:specification.limits.max_output_tokens_per_request,
    contextBudget:specification.limits.context_budget_estimated_tokens,modelTimeoutMs:100000,
    multiAgentEnabled:false};
}
const native=await import(pathToFileURL(path.join(delta,'src/core/native.ts')).href);
const providers=await import(pathToFileURL(path.join(delta,'src/core/providers.ts')).href);
const budget=new MultiModelBudget(output,specification,mode==='connection'?specification.limits.connection_stage_reference_cap_usd:undefined);
const records:any[]=[];
const schema=(properties:Record<string,any>,required=Object.keys(properties))=>({type:'object',properties,required,additionalProperties:false});
const string={type:'string'},integer={type:'integer',minimum:0};
const tools=[
  {name:'inspect_file',description:'Read a project text file and its current hash, with optional paging.',
    strict:false,parameters:schema({path:string,offset:integer,max_chars:{type:'integer',minimum:1,maximum:80000}},['path'])},
  {name:'edit_block',description:'Replace one exact source block using the latest file hash.',
    parameters:schema({path:string,old_text:string,new_text:string,expected_sha256:string})},
  {name:'update_file',description:'Replace a source module with complete text using its latest hash.',
    parameters:schema({path:string,content:string,expected_sha256:string})},
  {name:'run_tests',description:'Run the project tests and return the results.',parameters:schema({})},
  {name:'project_files',description:'List project source paths matching a text fragment.',
    parameters:schema({query:string})},
];
try{
  budget.install();
  await writeJson(path.join(output,'configuration.json'),{
    date:'2026-10-02',mode,agent:'Actual Delta Native',protocol_sha256:hash(JSON.stringify(specification)),
    delta_source_hashes:Object.fromEntries(await Promise.all(['src/core/native.ts','src/core/providers.ts','src/core/turn-input.ts']
      .map(async file=>[file,hash(await fs.readFile(path.join(delta,file)))]))),
    native_system_instructions_retained:true,exact_security_policy_in_user_prompt:false,
    no_credentials_in_project:true,
  });
  if(mode==='connection'){
    for(const model of specification.models){
      const directory=path.join(output,model.id);await fs.mkdir(directory);budget.select(model,directory);
      let answer:string|null=null,error:string|null=null;
      try{
        const reply=await providers.requestModel({model:'hard-'+model.id+':primary',settings:settingsFor(model),
          instructions:'You are a coding assistant.',input:[{role:'user',content:'Reply with the word connected.'}],
          tools:[],signal:AbortSignal.timeout(100000),onDelta:()=>{}});
        answer=reply.text;
      }catch(failure){error=(failure as Error).message;}
      const row={model_id:model.id,answer,error,connected:!error&&answer?.trim().toLowerCase()==='connected'};
      records.push(row);await writeJson(path.join(directory,'result.json'),row);
      await writeJson(path.join(output,'results.json'),{mode,results:records});
      console.log(`${model.id}: ${row.connected?'connected':error??answer}`);
    }
  }else{
    const control=JSON.parse(await fs.readFile(path.join(root,'reports/hard-reference-controls-v1.json'),'utf8'));
    assert.equal(control.passed,true,'Hard-task judge controls must pass before paid coding runs.');
    const preparedSourceFiles=await py(['-c',
      'import json;from pathlib import Path;from hardstudy.context import SOURCES;print(json.dumps({name:[p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file() and ".git" not in p.parts] for name,root in SOURCES.items()}))']);
    const budgetStoppedModels=new Set<string>();
    for(const [index,item] of specification.schedule.entries()){
      if(budgetStoppedModels.has(item.model_id)){
        records.push({...item,scheduled_index:index+1,termination:'not_run_budget',task_completed:false});
        await writeJson(path.join(output,'results.json'),{mode,results:records});continue;
      }
      const model=specification.models.find((model:any)=>model.id===item.model_id);
      const directory=path.join(output,`${String(index+1).padStart(3,'0')}-${item.model_id}-${item.task}-${item.context}-${item.condition}-${item.arm}-${item.repetition}`);
      await fs.mkdir(directory);const workspace=path.join(directory,'workspace');
      const prepared=await py(['-m','hardstudy.context','--workspace',workspace,'--task',item.task,
        '--condition',item.condition,'--context',item.context],120000);
      await fs.writeFile(path.join(directory,'context.txt'),prepared.context,'utf8');
      const {context,...inputReceipt}=prepared;await writeJson(path.join(directory,'input.json'),inputReceipt);
      const before=Object.fromEntries(await Promise.all(prepared.editable.map(async(file:string)=>[file,await fs.readFile(path.join(workspace,file),'utf8')])));
      await writeJson(path.join(directory,'initial-source.json'),before);
      budget.select(model,directory);
      const usageBefore=structuredClone(budget.perModel[model.id]),costBefore=budget.reference;
      const at=new Date().toISOString(),events:any[]=[];let answer='',error:string|null=null,testsRun=false;
      const task={id:'hard-'+(index+1),title:item.task,workspace,mode:'code',engine:'native',
        model:'hard-'+model.id+':primary',status:'running',createdAt:at,updatedAt:at,
        messages:[{id:'request',role:'user',text:prepared.prompt,createdAt:at}],events:[],
        notes:'',summary:'',usage:{inputTokens:0,outputTokens:0,cachedTokens:0,modelCalls:0}};
      console.log(`HARD ${index+1}/${specification.schedule.length} ${model.id}/${item.task}/${item.context}/${item.condition}/${item.arm}`);
      try{
        answer=await native.runNative({task,settings:settingsFor(model),context,
          signal:AbortSignal.timeout(specification.limits.wall_seconds_per_trajectory*1000),
          allowedTools:tools.map(tool=>tool.name),extensionTools:tools,onDelta:()=>{},onUsage:async()=>{},
          approve:async()=>false,
          onEvent:async(text:string,details:any)=>{events.push({text,details});await writeJson(path.join(directory,'events.json'),events);},
          saveCheckpoint:async(checkpoint:any)=>writeJson(path.join(directory,'checkpoint.json'),checkpoint),
          executeExtension:async(name:string,args:any)=>{
            if(name==='run_tests'){
              const result=await py(['-m','hardstudy.bridge','--workspace',workspace,'--task',item.task,'--public'],140000);
              testsRun=result.status==='assessed'&&result.failed===0;
              await writeJson(path.join(directory,'public-tests.json'),result);return JSON.stringify(result);
            }
            if(name==='project_files'){
              const query=args.query.toLowerCase();
              return JSON.stringify({paths:[...Object.keys(prepared.files),
                ...Object.entries(preparedSourceFiles).flatMap(([source,files]:any)=>files.map((file:string)=>'project/'+source+'/'+file))]
                .filter(file=>file.toLowerCase().includes(query)).slice(0,80)});
            }
            let file:string;
            if(Object.hasOwn(prepared.files,args.path))file=path.join(workspace,args.path);
            else{
              const match=/^project\/(frappe|erpnext)\/(.+)$/.exec(args.path??'');
              assert.ok(match&&preparedSourceFiles[match[1]].includes(match[2]),'Project path not found');
              assert.equal(name,'inspect_file','Project reference file is not editable');
              file=path.join(root,'_sources',match[1]==='frappe'?'large-frappe':'large-erpnext',match[2]);
            }
            const current=await fs.readFile(file,'utf8');
            if(name==='inspect_file'){
              const offset=args.offset??0,length=args.max_chars??24000;
              assert.ok(Number.isInteger(offset)&&offset>=0&&offset<=current.length);
              const end=Math.min(offset+length,current.length);
              return JSON.stringify({path:args.path,sha256:hash(current),content:current.slice(offset,end),
                total_chars:current.length,next_offset:end<current.length?end:null});
            }
            assert.ok(prepared.editable.includes(args.path),'This project file is not editable');
            assert.equal(hash(current),args.expected_sha256,'File changed; inspect it before editing');
            let next:string;
            if(name==='edit_block'){
              assert.ok(typeof args.old_text==='string'&&args.old_text.length>0);
              assert.equal(current.split(args.old_text).length,2,'Exact block missing or ambiguous');
              assert.equal(typeof args.new_text,'string');next=current.replace(args.old_text,()=>args.new_text);
            }else{assert.equal(name,'update_file');next=args.content;assert.equal(typeof next,'string');}
            assert.ok(Buffer.byteLength(next)<=160000);await fs.writeFile(file,next,'utf8');
            return JSON.stringify({path:args.path,saved:true,sha256:hash(next)});
          }});
      }catch(failure){error=(failure as Error).message;if(error.includes('Frozen multi-model'))budgetStoppedModels.add(model.id);}
      const candidate=Object.fromEntries(await Promise.all(prepared.editable.map(async(file:string)=>[file,await fs.readFile(path.join(workspace,file),'utf8')])));
      await writeJson(path.join(directory,'candidate-source.json'),candidate);
      const changed=Object.keys(candidate).some(file=>candidate[file]!==before[file]);
      const structure=await py(['-m','hardstudy.bridge','--workspace',workspace,'--task',item.task,
        '--structure-before',path.join(directory,'initial-source.json'),
        '--structure-after',path.join(directory,'candidate-source.json')]);
      const assessment=await py(['-m','hardstudy.bridge','--workspace',workspace,'--task',item.task],150000);
      const unchangedContext=(await Promise.all(Object.keys(prepared.files).filter(file=>!prepared.editable.includes(file))
        .map(async file=>hash(await fs.readFile(path.join(workspace,file)))===prepared.files[file]))).every(Boolean);
      const runUsage=Object.fromEntries(Object.keys(usageBefore).map(key=>[key,budget.perModel[model.id][key]-usageBefore[key]]));
      const row={...item,run_id:path.basename(directory),scheduled_index:index+1,
        termination:error?error.includes('Frozen multi-model')?'budget_stopped':'failed':'completed',
        error,changed,tests_run:testsRun,context_unchanged:unchangedContext,
        task_completed:!error&&structure.executable_changed&&structure.public_api_preserved&&testsRun&&unchangedContext,
        structure,
        assessment,usage:runUsage,reference_estimate_usd:budget.reference-costBefore,answer,
        context_sha256:prepared.context_manifest.sha256,context_characters:prepared.context_manifest.total_characters,
        candidate_hashes:Object.fromEntries(Object.entries(candidate).map(([file,code]:any)=>[file,hash(code)]))};
      records.push(row);await writeJson(path.join(directory,'run.json'),row);
      await writeJson(path.join(output,'results.json'),{mode,results:records,reference_estimate_usd:budget.reference});
      console.log(`  completed=${row.task_completed} checks=${assessment.passed}/${assessment.total} leaks=${assessment.security_failures} status=${assessment.interpretation?.status??assessment.status} error=${error}`);
    }
  }
}finally{budget.restore();await budget.save();}
await writeJson(path.join(output,'results.json'),{mode,completed_at:new Date().toISOString(),results:records,
  reference_estimate_usd:budget.reference,per_model:budget.perModel});
console.log(`Finished ${records.length} scheduled records; reference estimate $${budget.reference.toFixed(4)}.`);
