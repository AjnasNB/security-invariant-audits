/** Actual Delta Responses adapter; independent, preselected author mutation inputs. */
import {promises as fs} from 'node:fs';
import path from 'node:path';
import {pathToFileURL} from 'node:url';
import assert from 'node:assert/strict';
import {BoundedProvider} from './bounded-provider';
const option=(name:string,fallback:string)=>process.argv.find(arg=>arg.startsWith(`--${name}=`))?.slice(name.length+3)??fallback;
const output=option('output',''),deltaRoot=option('delta-root',process.env.DELTA_ROOT??'');
const profileRoot=option('profile',process.env.DELTA_LOCAL_PROFILE??(process.env.APPDATA?path.join(process.env.APPDATA,'Delta Harness'):''));
if(!output||!deltaRoot||!profileRoot)throw new Error('Supply prepared output, Delta source and configured local profile.');
const profile=JSON.parse(await fs.readFile(path.join(profileRoot,'workspace/state.json'),'utf8'));
assert.equal(profile.settings.solDeployment,'maqam-orchestrator-sol-6-1');
const settings={...profile.settings,maxOutputTokens:256,modelTimeoutMs:60000};
const providers=await import(pathToFileURL(path.join(deltaRoot,'src/core/providers.ts')).href);
const queries=JSON.parse(await fs.readFile(path.join(output,'queries.json'),'utf8')).variants;
const budget=new BoundedProvider(output,settings.solDeployment,{
  max_http_attempts:20,reference_estimate_cap_usd:.05,conservative_debit_cap_usd:.20});
const responses:any[]=[];
try{
  budget.install();
  for(const [index,query] of queries.entries()){
    const directory=path.join(output,`${index+1}-${query.id.replaceAll('/','-').replaceAll(':','-')}`);
    await fs.mkdir(directory);budget.select(directory);
    let text:string|null=null,error:string|null=null;
    try{
      const reply=await providers.requestModel({model:'sol',settings,instructions:'You are a coding assistant.',
        input:[{role:'user',content:query.prompt}],tools:[],signal:AbortSignal.timeout(60000),onDelta:()=>{}});
      text=reply.text;
    }catch(failure){error=(failure as Error).message;}
    responses.push({id:query.id,text,error,termination:error?error.includes('budget')?'budget_stopped':'failed':'completed'});
    await fs.writeFile(path.join(output,'responses.json'),JSON.stringify({responses},null,2)+'\n');
    console.log(`MUCOCO ${index+1}/${queries.length} ${query.id}: ${error??text}`);
    if(error?.includes('Frozen experiment budget'))break;
  }
}finally{budget.restore();await budget.save();}
