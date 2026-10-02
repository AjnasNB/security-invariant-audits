/** Actual Delta, all tracked text source editable, independent application HTTP tests. */
import assert from 'node:assert/strict';
import {promises as fs} from 'node:fs';
import path from 'node:path';
import {spawn} from 'node:child_process';
import {fileURLToPath,pathToFileURL} from 'node:url';
import {createHash} from 'node:crypto';
import {MultiModelBudget} from './multi-model-budget';

const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
const option=(key:string)=>process.argv.find(arg=>arg.startsWith(`--${key}=`))?.slice(key.length+3)??'';
const delta=option('delta-root'),python=option('python'),profileDirectory=option('profile'),azurePython=option('azure-python');
assert.ok(delta&&python&&profileDirectory&&azurePython);
const area=path.join(root,'artifacts/private/wholeapp-v1'),output=option('output')||path.join(area,'agent-runs');
const resume=process.argv.includes('--resume');
const protocol=JSON.parse(await fs.readFile(path.join(output,'protocol.json'),'utf8'));
const controls=JSON.parse(await fs.readFile(path.join(area,'judge-controls.json'),'utf8'));
assert.equal(controls.passed,true,'Independent access controls must pass before generation');
const profile=JSON.parse(await fs.readFile(path.join(profileDirectory,'workspace/state.json'),'utf8'));
const originalInventory=JSON.parse(await fs.readFile(path.join(area,'source-inventory.json'),'utf8'));
const native=await import(pathToFileURL(path.join(delta,'src/core/native.ts')).href);
const hash=(value:Buffer|string)=>createHash('sha256').update(value).digest('hex');
const writeJson=(file:string,value:any)=>fs.writeFile(file,JSON.stringify(value,null,2)+'\n');
async function execute(command:string,args:string[],timeout=120000){
  return new Promise<{code:number;stdout:string;stderr:string}>((resolve,reject)=>{
    const child=spawn(command,args,{cwd:root,shell:false,windowsHide:true,stdio:['ignore','pipe','pipe'],
      env:{...process.env,PYTHONUTF8:'1',PYTHONDONTWRITEBYTECODE:'1'}});
    let stdout='',stderr='';const timer=setTimeout(()=>{child.kill();reject(new Error('Local helper timed out'));},timeout);
    child.stdout.on('data',value=>stdout+=value);child.stderr.on('data',value=>stderr+=value);
    child.on('error',error=>{clearTimeout(timer);reject(error);});
    child.on('exit',code=>{clearTimeout(timer);resolve({code:code??-1,stdout,stderr});});
  });
}
async function py(args:string[]){
  const value=await execute(python,['-B',...args],230000);
  if(value.code)throw new Error('Local test helper failed; private diagnostics retained');
  const lines=value.stdout.trim().split('\n');return JSON.parse(lines.at(-1)!);
}
const schema=(properties:any,required=Object.keys(properties))=>({type:'object',properties,required,additionalProperties:false});
const string={type:'string'};
const tools=[
  {name:'project_files',description:'List project files matching a path fragment.',parameters:schema({query:string})},
  {name:'inspect_file',description:'Read a project text file and current hash, with paging.',strict:false,
    parameters:schema({path:string,offset:{type:'integer',minimum:0},max_chars:{type:'integer',minimum:1,maximum:60000}},['path'])},
  {name:'search_project',description:'Search text in project files; returns matching lines and paths.',
    parameters:schema({query:string,path_fragment:string})},
  {name:'edit_block',description:'Replace one exact source block using the current file hash.',
    parameters:schema({path:string,old_text:string,new_text:string,expected_sha256:string})},
  {name:'update_file',description:'Replace an existing project text file using its latest hash.',
    parameters:schema({path:string,content:string,expected_sha256:string})},
  {name:'run_tests',description:'Run the application smoke tests and return counts.',parameters:schema({})},
];
const budget=new MultiModelBudget(output,protocol),records:any[]=[];
if(resume){
  await budget.restoreSavedLedger();
  try{records.push(...JSON.parse(await fs.readFile(path.join(output,'results.json'),'utf8')).results);}
  catch(error){if((error as any).code!=='ENOENT')throw error;}
}
const priceModels=protocol.models;
for(const model of priceModels){
  const checked=await execute(azurePython,['-IBm','azure.cli','cognitiveservices','account','deployment','show',
    '-g',model.group,'-n',model.account,'--deployment-name',model.deployment,
    '--query','{state:properties.provisioningState,model:properties.model.name,version:properties.model.version}','-o','json'],50000);
  assert.equal(checked.code,0);const verified=JSON.parse(checked.stdout);
  assert.equal(verified.state,'Succeeded');assert.equal(verified.model,model.model);assert.equal(verified.version,model.version);
}
await writeJson(path.join(output,'configuration.json'),{registered_protocol_sha256:hash(JSON.stringify(protocol)),
  delta_source_hashes:Object.fromEntries(await Promise.all(['src/core/native.ts','src/core/providers.ts']
    .map(async name=>[name,hash(await fs.readFile(path.join(delta,name)))]))),
  original_native_system_instructions:true,credentials_in_agent_workspace:false,
  arbitrary_shell_available:false,all_tracked_text_source_editable:true,exact_security_rule_in_user_prompt:false});
try{
  budget.install();
  for(const item of protocol.schedule){
    if(records.some(row=>row.run_id===item.run_id))continue;
    const model=priceModels.find((value:any)=>value.id===item.model_id);
    const directory=path.join(output,item.run_id),workspace=path.resolve(item.workspace);
    const files=Object.keys(originalInventory);
    const selected=['frappe/README.md','erpnext/README.md','frappe/frappe/client.py','frappe/frappe/desk/form/load.py',
      'frappe/frappe/api/v1.py','frappe/frappe/core/doctype/file/utils.py'];
    let context='ERP application source. Full project paths are accessible through the file/search tools.\n';
    for(const file of selected){
      const content=await fs.readFile(path.join(workspace,file),'utf8');
      if(context.length+content.length<100000)context+=`\n--- ${file} ---\n${content}\n`;
    }
    const provider={id:'whole-'+model.id,name:model.name,kind:'azure-openai',endpoint:model.endpoint,
      auth:'azure-cli',models:[{id:'primary',name:model.name,model:model.deployment,supportsTools:true,
        contextWindow:model.context_window,maxInputTokens:model.max_input_tokens,maxOutputTokens:128000}]};
    const settings={...profile.settings,providers:[provider],maxSteps:protocol.limits.max_steps_per_trajectory,
      maxOutputTokens:protocol.limits.max_output_tokens_per_request,contextBudget:protocol.limits.context_budget_estimated_tokens,
      modelTimeoutMs:100000,multiAgentEnabled:false};
    const now=new Date().toISOString();
    const task={id:'whole-'+model.id,title:'ERP application rewrite',workspace,mode:'code',engine:'native',
      model:provider.id+':primary',status:'running',createdAt:now,updatedAt:now,
      messages:[{id:'rewrite-request',role:'user',text:item.prompt,createdAt:now}],events:[],notes:'',summary:'',
      usage:{inputTokens:0,outputTokens:0,cachedTokens:0,modelCalls:0}};
    await fs.writeFile(path.join(directory,'context.txt'),context);
    budget.select(model,directory);
    let checkpoint:any;
    const events:any[]=resume?JSON.parse(await fs.readFile(path.join(directory,'events.json'),'utf8').catch(()=> '[]')):[];
    if(resume){
      try{checkpoint=JSON.parse(await fs.readFile(path.join(directory,'checkpoint.json'),'utf8'));}
      catch(error){if((error as any).code!=='ENOENT')throw error;}
      let transmittedEstimate=0;
      for(const name of await fs.readdir(directory)){
        if(/^provider-\d+-request\.json$/.test(name)){
          transmittedEstimate+=Math.ceil(Buffer.byteLength(JSON.stringify(
            JSON.parse(await fs.readFile(path.join(directory,name),'utf8'))))/2);
        }
      }
      budget.restoreTrajectoryEstimate(transmittedEstimate);
    }
    const before=checkpoint?{requests:0,attempts:0,input_tokens:0,output_tokens:0,cached_tokens:0,
      cache_write_tokens:0,reference_estimate_usd:0,unknown_usage_attempts:0}:structuredClone(budget.perModel[model.id]);
    const costBefore=checkpoint?budget.reference-budget.perModel[model.id].reference_estimate_usd:budget.reference;
    let answer='',error:string|null=null,testNumber=(await fs.readdir(directory)).filter(name=>name.startsWith('ordinary-http-')).length,testsRun=false;
    console.log(`WHOLE ${model.name}: ${files.length} application files available`);
    try{
      answer=await native.runNative({task,settings,context,checkpoint,
        signal:AbortSignal.timeout(protocol.limits.wall_seconds_per_trajectory*1000),
        allowedTools:tools.map(tool=>tool.name),extensionTools:tools,approve:async()=>false,onDelta:()=>{},
        onUsage:async()=>{},onEvent:async(text:string,details:any)=>{events.push({text,details});await writeJson(path.join(directory,'events.json'),events);},
        saveCheckpoint:async(value:any)=>writeJson(path.join(directory,'checkpoint.json'),value),
        executeExtension:async(name:string,args:any)=>{
          if(name==='project_files')return JSON.stringify({paths:files.filter(file=>file.includes(args.query)).slice(0,120),total:files.length});
          if(name==='run_tests'){
            const testOutput=path.join(directory,`ordinary-http-${++testNumber}`);
            const value=await py(['-m','wholeapp.bridge','--workspace',workspace,'--output',testOutput,'--public']);
            testsRun=value.failed===0;return JSON.stringify(value);
          }
          if(name==='search_project'){
            assert.ok(args.query.length>0&&args.query.length<=180);
            const matches:any[]=[];
            for(const file of files.filter(file=>file.includes(args.path_fragment)).slice(0,3000)){
              const buffer=await fs.readFile(path.join(workspace,file));
              if(buffer.length>250000||buffer.includes(0))continue;
              const lines=buffer.toString('utf8').split('\n');
              for(let line=0;line<lines.length;line++)if(lines[line].includes(args.query)){
                matches.push({path:file,line:line+1,text:lines[line].slice(0,400)});
                if(matches.length>=60)return JSON.stringify({matches,truncated:true});
              }
            }return JSON.stringify({matches,truncated:false});
          }
          assert.ok(files.includes(args.path),'Project path not available');
          const file=path.resolve(workspace,args.path);assert.ok(file.startsWith(workspace+path.sep));
          const raw=await fs.readFile(file);assert.ok(!raw.includes(0)&&raw.length<=350000,'Not a supported text file');
          const content=raw.toString('utf8');
          if(name==='inspect_file'){
            const offset=args.offset??0,length=args.max_chars??24000;
            assert.ok(Number.isInteger(offset)&&offset>=0&&offset<=content.length);
            assert.ok(Number.isInteger(length)&&length>0&&length<=60000);
            const end=Math.min(offset+length,content.length);
            return JSON.stringify({path:args.path,sha256:hash(raw),content:content.slice(offset,end),
              total_chars:content.length,next_offset:end<content.length?end:null});
          }
          assert.ok(!/(^|\/)(LICENSE|license|NOTICE|COPYING)(\.|$)/i.test(args.path),'Keep license/copyright notices');
          assert.equal(hash(raw),args.expected_sha256,'Inspect the current source before editing');
          let replacement:string;
          if(name==='edit_block'){
            assert.ok(args.old_text.length>0&&content.split(args.old_text).length===2,'Exact source block missing/ambiguous');
            replacement=content.replace(args.old_text,()=>args.new_text);
          }else{assert.equal(name,'update_file');assert.equal(typeof args.content,'string');replacement=args.content;}
          assert.ok(Buffer.byteLength(replacement)<=400000);
          await fs.writeFile(file,replacement,'utf8');return JSON.stringify({saved:true,path:args.path,sha256:hash(replacement)});
        }});
    }catch(failure){error=(failure as Error).message;}
    const sourceInventory=await py(['-m','wholeapp.bridge','--workspace',workspace,'--output',directory,'--inventory']);
    await writeJson(path.join(directory,'source-change-inventory.json'),sourceInventory);
    let assessment:any=null,executionError:string|null=null;
    try{assessment=await py(['-m','wholeapp.bridge','--workspace',workspace,'--output',path.join(directory,'final-http')]);}
    catch(failure){executionError=(failure as Error).message;}
    const usage=Object.fromEntries(Object.keys(before).map(key=>[key,budget.perModel[model.id][key]-before[key]]));
    const record={...item,error,termination:error?'incomplete':'completed',answer,tests_run:testsRun,
      changed_files:sourceInventory.changed_files,missing_files:sourceInventory.missing_files,
      completed_agent_refactor:!error&&testsRun&&sourceInventory.changed_count>0&&sourceInventory.missing_files.length===0,
      entire_repository_rewritten:false,assessment,execution_error:executionError,usage,
      reference_estimate_usd:budget.reference-costBefore,context_sha256:hash(context),context_characters:context.length};
    records.push(record);await writeJson(path.join(directory,'run.json'),record);
    await writeJson(path.join(output,'results.json'),{results:records});
    console.log(`${model.name}: changed=${sourceInventory.changed_count} completed=${record.completed_agent_refactor} `
      +`checks=${assessment?.passed}/${assessment?.total} access_failures=${assessment?.security_failures} error=${error??executionError}`);
  }
}finally{budget.restore();await budget.save();}
await writeJson(path.join(output,'results.json'),{completed_at:new Date().toISOString(),results:records});
