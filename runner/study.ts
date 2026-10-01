/**
 * Actual Delta Native agent loop; only the research extension broker can act.
 * Provider credentials never enter task files or candidate execution containers.
 */
import assert from "node:assert/strict";
import {promises as fs} from "node:fs";
import path from "node:path";
import crypto from "node:crypto";
import {spawn} from "node:child_process";
import {pathToFileURL,fileURLToPath} from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const args = process.argv.slice(2);
const option = (name:string, fallback:string) => args.find(arg => arg.startsWith(`--${name}=`))?.slice(name.length+3) ?? fallback;
const mode = option("mode", "smoke");
const deltaRoot = option("delta-root", "D:/delta voice/my harness");
const python = option("python", "python");
const batchName = option("batch", `${mode}-${new Date().toISOString().replace(/[:.]/g, "-")}`);
assert.match(batchName, /^[a-zA-Z0-9_-]+$/);
const batchDir = path.join(root, "artifacts", "agent_runs", batchName);
const protocol = JSON.parse(await fs.readFile(path.join(root, "protocol.json"), "utf8"));
const limits = protocol.limits;
const hash = (text:string|Buffer) => crypto.createHash("sha256").update(text).digest("hex");
const now = () => new Date().toISOString();
const total = {requests:0,input_tokens:0,output_tokens:0,cached_tokens:0,estimated_cost_usd:0,planning_debit_usd:0};
const publicReferenceRates = {input:2,cached:0.1,output:10,source:"OpenAI public Standard API reference; Azure invoice may differ",checked:"2026-10-01"};
const planningRates = {
  input:protocol.billing.unverified_conservative_planning_rates[0],
  output:protocol.billing.unverified_conservative_planning_rates[2],
};
let activeRunDir:string|undefined;
let capturedCounter=0;
let metadataError:string|undefined;
let activeQueryId:string|undefined;
let lastResponseMetadata:any;
await fs.mkdir(path.dirname(batchDir), {recursive:true});
await fs.mkdir(batchDir, {recursive:false});

async function exec(command:string, arguments_:string[], timeout=60000, input?:string) {
  return new Promise<{code:number,stdout:string,stderr:string}>((resolve,reject)=>{
    const process_ = spawn(command, arguments_, {cwd:root,shell:false,windowsHide:true,
      env:{...process.env,PYTHONDONTWRITEBYTECODE:"1"},stdio:["pipe","pipe","pipe"]});
    let stdout="",stderr="";
    const timer=setTimeout(()=>{process_.kill();reject(new Error("Controller subprocess timed out"));},timeout);
    process_.stdout.on("data",chunk=>{stdout+=chunk;});
    process_.stderr.on("data",chunk=>{stderr+=chunk;});
    process_.on("error",error=>{clearTimeout(timer);reject(error);});
    process_.on("exit",code=>{clearTimeout(timer);resolve({code:code??1,stdout,stderr});});
    process_.stdin.end(input);
  });
}
async function writeJson(file:string,value:unknown) {
  await fs.writeFile(file,JSON.stringify(value,null,2)+"\n","utf8");
}
async function pythonJson(arguments_:string[],timeout=60000) {
  const result=await exec(python,["-m","research.cli",...arguments_],timeout);
  if(result.code)throw new Error(`Controller check failed: ${result.stderr.slice(-1800)}`);
  return JSON.parse(result.stdout);
}
const nativeModule = await import(pathToFileURL(path.join(deltaRoot,"src/core/native.ts")).href);
const providerModule = await import(pathToFileURL(path.join(deltaRoot,"src/core/providers.ts")).href);
const azurePython=option("azure-python","C:/Program Files/Microsoft SDKs/Azure/CLI2/python.exe");
const deploymentCheck=await exec(azurePython,["-IBm","azure.cli",
  "cognitiveservices","account","deployment","show","-g","rg-erpseeker-demo",
  "-n","erpseeker-ai-9340a6","--deployment-name",protocol.deployment,
  "--query","{deployment:name,state:properties.provisioningState,model:properties.model,sku:sku}","-o","json",
]);
if(deploymentCheck.code)throw new Error("Azure deployment metadata could not be verified");
const deploymentMetadata=JSON.parse(deploymentCheck.stdout);
assert.equal(deploymentMetadata.model.name,protocol.expected_model);
assert.equal(deploymentMetadata.model.version,protocol.expected_version);
assert.equal(deploymentMetadata.state,"Succeeded");
await writeJson(path.join(batchDir,"deployment.json"),deploymentMetadata);
const settings:any={
  azureEndpoint:"https://erpseeker-ai-9340a6.openai.azure.com/openai/v1",
  astraDeployment:"unused",solDeployment:protocol.deployment,lunaDeployment:"unused",
  claudeEndpoint:"",claudeDeployment:"",claudeAuth:"api-key",
  maxSteps:limits.max_steps,maxOutputTokens:limits.max_output_tokens_per_request,contextBudget:20000,
  commandTimeoutMs:45000,modelTimeoutMs:120000,maxTaskTokens:100000,maxTaskUsd:1,multiAgentEnabled:false,
  providers:[{id:"research",name:"Research Azure GPT-6.1 Sol",kind:"azure-openai",auth:"azure-cli",
    endpoint:"https://erpseeker-ai-9340a6.openai.azure.com/openai/v1",
    models:[{id:"sol61",name:"GPT-6.1 Sol",model:protocol.deployment,supportsTools:true,contextWindow:20000}]}],
  theme:"system",speechProvider:"local",speechLocalExecutable:"",speechLocalModel:"",selfSourcePath:"",
  speechEndpoint:"",speechDeployment:"",speechLanguage:"",speechAuth:"azure-cli",codexPath:"",
};
const modelKey="research:sol61";
const upstreamFetch=globalThis.fetch;
// Inspect the final served response and preserve every provider event. No headers are persisted.
globalThis.fetch=async function(input:any, init:any) {
  const url=String(input);
  if(!url.endsWith("/responses"))return upstreamFetch(input,init);
  const body=JSON.parse(init.body);
  assert.equal(body.model,protocol.deployment,"Never substitute the requested model");
  body.reasoning={effort:"low"}; // Explicit research adapter setting, fixed in every condition.
  assert.ok(body.max_output_tokens<=limits.max_output_tokens_per_request);
  const inputEstimate=Math.ceil(Buffer.byteLength(JSON.stringify(body))/2);
  const reserve=inputEstimate*planningRates.input/1e6+body.max_output_tokens*planningRates.output/1e6;
  if(inputEstimate>limits.max_input_tokens_per_request)throw new Error("Input planning cap reached");
  if(total.requests>=limits.batch_max_requests||total.planning_debit_usd+reserve>limits.batch_planning_cap_usd)
    throw new Error("Research request/spending planning cap reached");
  if(total.input_tokens+total.output_tokens+inputEstimate+body.max_output_tokens>limits.batch_max_total_tokens)
    throw new Error("Research total token cap reached");
  total.requests++;
  capturedCounter++;
  const requestIndex=capturedCounter;
  const requestDir=activeRunDir??batchDir;
  await writeJson(path.join(requestDir,`provider-${requestIndex}-request.json`),body);
  const response=await upstreamFetch(input,{...init,body:JSON.stringify(body)});
  const requestId=response.headers.get("x-request-id")??response.headers.get("apim-request-id")??response.headers.get("x-ms-request-id");
  const raw=await response.text();
  await fs.writeFile(path.join(requestDir,`provider-${requestIndex}-response.sse`),raw,"utf8");
  const events:any[]=[];
  for(const block of raw.replaceAll("\r\n","\n").split("\n\n")){
    const data=block.split("\n").filter(line=>line.startsWith("data:")).map(line=>line.slice(5).trimStart()).join("\n");
    if(data&&data!=="[DONE]"){try{events.push(JSON.parse(data));}catch{}}
  }
  const completed=events.find(event=>event.type==="response.completed"||event.type==="response.incomplete")?.response;
  const metadata:any={request_id:requestId,http_status:response.status,started_at:now(),model:completed?.model,
    response_id:completed?.id,status:completed?.status,usage:completed?.usage,response_sha256:hash(raw),
    query_id:activeQueryId,incomplete_details:completed?.incomplete_details};
  if(completed?.usage){
    const usage=completed.usage;
    const inputTokens=usage.input_tokens??0,outputTokens=usage.output_tokens??0,cached=usage.input_tokens_details?.cached_tokens??0;
    total.input_tokens+=inputTokens;total.output_tokens+=outputTokens;total.cached_tokens+=cached;
    total.estimated_cost_usd+=(inputTokens-cached)*publicReferenceRates.input/1e6+cached*publicReferenceRates.cached/1e6+outputTokens*publicReferenceRates.output/1e6;
    total.planning_debit_usd+=inputTokens*planningRates.input/1e6+outputTokens*planningRates.output/1e6;
  }else if(response.status!==429){total.planning_debit_usd+=reserve;metadata.usage_unknown=true;metadataError="Missing provider usage"; }
  // Azure may report the deployment alias in response.model; keep it verbatim and
  // link it to the independently verified deployment mapping rather than inventing a snapshot.
  metadata.identity_evidence=completed?.model===protocol.deployment
    ? "response deployment alias + Azure control-plane model/version mapping"
    : "response model field + Azure control-plane model/version mapping";
  if(completed?.model&&completed.model!==protocol.deployment&&!completed.model.startsWith(protocol.expected_model)){
    metadataError=`Served model mismatch: ${completed.model}`;metadata.model_mismatch=true;
  }
  await writeJson(path.join(requestDir,`provider-${requestIndex}-metadata.json`),metadata);
  lastResponseMetadata=metadata;
  await writeJson(path.join(batchDir,"usage.json"),{...total,rates:publicReferenceRates,cost_is_estimate_not_invoice:true});
  // Recreate the observed stream so Delta's original response parser still handles it.
  return new Response(raw,{status:response.status,statusText:response.statusText,headers:response.headers});
} as typeof fetch;

await writeJson(path.join(batchDir,"configuration.json"),{
  engine:"Delta Native actual runNative + restricted extension broker",deployment:protocol.deployment,
  expected_model:protocol.expected_model,protocol_sha256:hash(JSON.stringify(protocol)),settings,
  reasoning_effort:"low",pricing:publicReferenceRates,
  delta_git_commit:(await exec("git",["-C",deltaRoot,"rev-parse","HEAD"])).stdout.trim(),
  delta_source_hashes:Object.fromEntries(await Promise.all(["src/core/native.ts","src/core/providers.ts","src/core/provider-registry.ts","src/core/tools.ts","src/core/runtime-clock.ts"].map(async file=>[file,hash(await fs.readFile(path.join(deltaRoot,file)))]))),
});
const results:any[]=[];
try {
  if(mode==="connection"){
    for(const [index,code] of [
      "def f(x):\n    count = x + 1\n    return count * 2",
      "def f(x):\n    count = x + 1\n    return count * 2",
      "def f(x):\n    result = x + 1\n    return result * 2",
      "def f(x):\n    result = x + 1\n    return result * 2",
    ].entries()){
      const response=await providerModule.requestModel({model:modelKey,settings:{...settings,maxOutputTokens:256},
        instructions:"Return only the integer requested, no commentary.",
        input:[{role:"user",content:`${code}\nWhat is f(3)?`}],tools:[],signal:AbortSignal.timeout(60000),onDelta:()=>{}});
      const passed=response.text.trim()==="8"&&!metadataError;
      results.push({kind:"connection",index,condition:index<2?"original":"rename",passed,text:response.text,usage:response.usage});
      if(!passed)throw new Error("Connection check failed");
    }
  }else if(mode==="text"){
    const queries=JSON.parse(await fs.readFile(option("queries",""),"utf8"));
    settings.maxOutputTokens=512;
    for(const query of queries){
      activeQueryId=query.id;lastResponseMetadata=undefined;
      try{
        const response=await providerModule.requestModel({
          model:modelKey,settings,instructions:query.instructions??"You are a helpful assistant.",
          input:query.messages??[{role:"user",content:query.prompt}],tools:[],
          signal:AbortSignal.timeout(60000),onDelta:()=>{},
        });
        results.push({id:query.id,text:response.text,usage:response.usage,termination:"completed"});
      }catch(failure){
        const filtered=lastResponseMetadata?.incomplete_details?.reason==="content_filter";
        const incomplete=lastResponseMetadata?.status==="incomplete";
        results.push({id:query.id,text:null,termination:filtered?"content_filtered":incomplete?"incomplete":"errored",
          error:(failure as Error).message,provider_metadata:lastResponseMetadata});
        // Keep blocked/incomplete attempts. Never retry them into a usable response.
        if(!filtered&&!incomplete)throw failure;
      }
      await writeJson(path.join(batchDir,"results.json"),{mode,results,total,rates:publicReferenceRates});
      if(metadataError)throw new Error(metadataError);
    }
  }else{
    const validation=JSON.parse(await fs.readFile(path.join(root,"artifacts/validation.json"),"utf8"));
    assert.equal(validation.passed,true,"Evaluator must pass before live agent runs");
    let schedule:any[];
    if(mode==="single")schedule=[{task:option("task","access_helper"),condition:option("condition","original"),repetition:0,arm:"smoke"}];
    else if(mode==="smoke")schedule=["access_helper","invoice_lookup","invoice_list","fastapi_items"].flatMap(task=>protocol.conditions.map((condition:string)=>({task,condition,repetition:0,arm:"smoke"})));
    else if(mode==="application"){
      schedule=protocol.conditions.map((condition:string)=>({task:"fastapi_items",condition,repetition:0,arm:"application-smoke"}));
    }else if(mode==="pilot"){
      schedule=protocol.fixture_tasks.flatMap((task:string)=>[
        ...protocol.conditions.flatMap((condition:string)=>Array.from({length:2},(_,repetition)=>({task,condition,repetition,arm:"variation"}))),
        ...Array.from({length:6},(_,repetition)=>({task,condition:"original",repetition,arm:"unchanged-control"})),
      ]);
    }else throw new Error("Unknown run mode");
    // Recorded deterministic shuffle; hosted model responses themselves need not be deterministic.
    let seed=protocol.schedule_seed;
    const random=()=>{seed=(Math.imul(1664525,seed)+1013904223)>>>0;return seed/2**32;};
    for(let index=schedule.length-1;index>0;index--){const j=Math.floor(random()*(index+1));[schedule[index],schedule[j]]=[schedule[j],schedule[index]];}
    await writeJson(path.join(batchDir,"schedule.json"),schedule);
    for(const [index,item] of schedule.entries()){
      if(metadataError)throw new Error(metadataError);
      const runId=`${String(index+1).padStart(3,"0")}-${item.task}-${item.condition}-${item.arm}-${item.repetition}`;
      activeRunDir=path.join(batchDir,runId);await fs.mkdir(activeRunDir);
      const workspace=path.join(activeRunDir,"workspace");
      const prepared=await pythonJson(["prepare","--workspace",workspace,"--task",item.task,"--condition",item.condition]);
      const before=await fs.readFile(path.join(workspace,"target.py"),"utf8");
      await writeJson(path.join(activeRunDir,"input.json"),prepared);
      const started=now();
      const usageBefore={...total};
      const events:any[]=[];
      const event=async(text:string,details?:unknown)=>{
        const value={timestamp:now(),text,details};events.push(value);
        await fs.appendFile(path.join(activeRunDir!,"tool_events.jsonl"),JSON.stringify(value)+"\n");
      };
      const definitions=[
        {name:"study_read_file",description:"Read one listed task file. Only target.py, models.py, PROJECT_NOTE.md and public_cases.json are allowed.",
          parameters:{type:"object",properties:{path:{type:"string"}},required:["path"],additionalProperties:false}},
        {name:"study_write_file",description:"Replace target.py with complete updated Python source. Other files cannot be edited.",
          parameters:{type:"object",properties:{path:{type:"string"},content:{type:"string"},expected_sha256:{type:"string"}},required:["path","content","expected_sha256"],additionalProperties:false}},
        {name:"study_run_public_tests",description:"Execute the fixed public tests inside the no-network, non-root research container.",
          parameters:{type:"object",properties:{},required:[],additionalProperties:false}},
      ];
      const broker=async(name:string,parameters:any)=>{
        if(name==="study_read_file"){
          if(parameters.path==="PROJECT_NOTE.md"&&!prepared.available_files.includes(parameters.path)){
            return JSON.stringify({path:"PROJECT_NOTE.md",exists:false,
              message:"No project note is present in this condition. Do not reread this absent file.",
              available_files:prepared.available_files});
          }
          assert.ok(prepared.available_files.includes(parameters.path),"Path not in task allowlist");
          assert.ok(["target.py","models.py","PROJECT_NOTE.md","public_cases.json"].includes(parameters.path),"Path not allowed");
          const file=path.join(workspace,parameters.path);
          const stat=await fs.lstat(file);assert.ok(stat.isFile()&&!stat.isSymbolicLink(),"Linked paths prohibited");
          const text=await fs.readFile(file,"utf8");
          return JSON.stringify({path:parameters.path,sha256:hash(text),content:text});
        }
        if(name==="study_write_file"){
          assert.equal(parameters.path,"target.py");
          assert.ok(typeof parameters.content==="string"&&parameters.content.length<64000);
          assert.equal(hash(await fs.readFile(path.join(workspace,"target.py"),"utf8")),parameters.expected_sha256,"Stale source hash");
          await fs.writeFile(path.join(workspace,"target.py"),parameters.content,"utf8");
          return JSON.stringify({saved:"target.py",sha256:hash(parameters.content)});
        }
        if(name==="study_run_public_tests"){
          const check=await pythonJson(["public","--workspace",workspace,"--task",item.task]);
          await writeJson(path.join(activeRunDir!,"public_tests.json"),check);
          return JSON.stringify({
            status:check.status,total:check.total,passed:check.passed,
            functional_failures:check.functional_failures,security_failures:check.security_failures,
            checks:check.checks?.map((row:any)=>({id:row.id,passed:row.passed})),
            failures:check.checks?.filter((row:any)=>!row.passed),
            error:check.error,
          });
        }
        throw new Error("Unknown tool");
      };
      let final="",termination="completed",error:string|undefined;
      console.log(`${runId}: starting GPT-6.1 Sol / Delta restricted`);
      try{
        const task:any={id:runId,title:runId,workspace,mode:"code",engine:"native",model:modelKey,status:"running",
          createdAt:started,updatedAt:started,messages:[{id:"request",role:"user",text:prepared.instruction+
            `\nAvailable task files: ${prepared.available_files.join(", ")}.`,createdAt:started}],
          events:[],notes:"",summary:"",usage:{inputTokens:0,outputTokens:0,cachedTokens:0,modelCalls:0},
          accessMode:"ask",skillIds:[],pluginIds:[],qarinahEnabled:false};
        final=await nativeModule.runNative({
          task,settings,context:"",signal:AbortSignal.timeout(limits.wall_seconds_per_run*1000),
          onDelta:()=>{},onEvent:event,approve:async()=>false,onUsage:async()=>{},
          allowedTools:definitions.map(definition=>definition.name),extensionTools:definitions,executeExtension:broker,
          beforeModelCall:async()=>{if(metadataError)throw new Error(metadataError);},
        });
      }catch(failure){termination="errored";error=(failure as Error).message;}
      const candidate=await fs.readFile(path.join(workspace,"target.py"),"utf8");
      await fs.writeFile(path.join(activeRunDir,"candidate.py"),candidate);
      await fs.writeFile(path.join(activeRunDir,"final_response.txt"),final);
      const sealedAt=now();const candidateHash=hash(candidate);
      const assessment=await pythonJson(["assess","--workspace",workspace,"--task",item.task],60000);
      await writeJson(path.join(activeRunDir,"assessment.json"),assessment);
      const changed=before!==candidate;
      const receipt={
        run_id:runId,...item,started_at:started,sealed_at:sealedAt,completed_at:now(),engine:"delta-native-restricted",
        requested_deployment:protocol.deployment,candidate_sha256:candidateHash,changed,
        task_completed:termination==="completed"&&changed&&assessment.status==="assessed"&&assessment.functional_failures===0,
        termination,error,assessment: {status:assessment.status,total:assessment.total,passed:assessment.passed,
          functional_failures:assessment.functional_failures,security_failures:assessment.security_failures},
        usage:Object.fromEntries(Object.keys(total).map(key=>[key,(total as any)[key]-(usageBefore as any)[key]])),
        preparation:prepared.metadata,tool_calls:events.filter(event=>event.text.startsWith("Tool:")).length,
        note_read:prepared.available_files.includes("PROJECT_NOTE.md")&&events.some(event=>
          event.text==="study_read_file result"&&(event.details as any)?.phase==="completed"&&
          (event.details as any)?.output?.includes('"path":"PROJECT_NOTE.md"')),
      };
      await writeJson(path.join(activeRunDir,"run.json"),receipt);results.push(receipt);
      await writeJson(path.join(batchDir,"results.json"),{mode,results,total,rates:publicReferenceRates});
      console.log(`${runId}: ${termination}; changed=${changed}; ${assessment.passed}/${assessment.total}; security failures=${assessment.security_failures}`);
    }
  }
  await writeJson(path.join(batchDir,"results.json"),{mode,completed_at:now(),results,total,rates:publicReferenceRates});
}catch(failure){
  await writeJson(path.join(batchDir,"results.json"),{mode,stopped_at:now(),error:(failure as Error).message,results,total,rates:publicReferenceRates});
  console.error((failure as Error).message);process.exitCode=1;
}finally{
  globalThis.fetch=upstreamFetch;
  console.log(JSON.stringify({batch:batchDir,completed:results.length,...total}));
}
