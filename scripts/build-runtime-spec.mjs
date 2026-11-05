import fs from 'node:fs';
import YAML from 'yaml';
const blueprint = YAML.parse(fs.readFileSync('openapi/openapi.yaml', 'utf8'));
const names = ['/requests', '/requests/{requestId}', '/requests/{requestId}/decisions', '/requests/{requestId}/complete', '/requests/routing-rules', '/audit'];
const s = {openapi:'3.1.0',info:{title:'Family Ops Requests API',version:'0.2.0',description:'Runnable single-household subset. Person sessions only; no service delegation, kiosk or channel decisions. All other blueprint domains are not implemented.',license:{name:'MIT',identifier:'MIT'}},servers:[{url:'http://localhost:8080/v1'}],security:[{personSession:[]}],tags:blueprint.tags.filter(t=>['requests','audit'].includes(t.name)),paths:{},components:structuredClone(blueprint.components)};
s.components.securitySchemes={personSession:{type:'http',scheme:'bearer',description:'Opaque one-hour token returned by POST /auth/login; maps to one enabled person. Never trust caller-supplied role headers.'}};
for(const n of names){
 s.paths[n]=structuredClone(blueprint.paths[n]);
 for(const [method, op] of Object.entries(s.paths[n])){
  if(method==='parameters')continue;
  delete op.security;
  op['x-allowed-roles']=op['x-allowed-roles'].filter(r=>['parent','teen','child'].includes(r));
  op.responses['400']={$ref:'#/components/responses/BadRequest'};
 }
}
s.paths['/requests'].post.description='Server derives requester from the authenticated person. Routing is frozen at creation. Only parents may hide surprise requests. No onBehalfOf support.';
s.paths['/requests'].get.description='Requester and frozen parent deciders only; hidden requests omitted. Offset cursor applies after visibility filtering.';
s.paths['/requests/{requestId}'].get.description='Same visibility as listing. Decider opening a new request changes it to seen and increments revision.';
s.components.schemas.RequestInput.additionalProperties=false;
delete s.components.schemas.RequestInput.properties.onBehalfOf;
s.components.schemas.RequestInput.properties.title.minLength=1;
s.components.schemas.DecisionInput.additionalProperties=false;
s.components.schemas.Mutation={type:'object',additionalProperties:false,required:['revision'],properties:{revision:{type:'integer',minimum:1}}};
s.components.schemas.Answer={...structuredClone(s.components.schemas.Mutation),properties:{revision:{type:'integer',minimum:1},details:{type:'string',maxLength:2000}}};
for(const action of ['complete','cancel','answer']){
 const path='/requests/{requestId}/'+action;
 s.paths[path]={parameters:[{$ref:'#/components/parameters/requestId'}],post:{tags:['requests'],operationId:action+'Request',summary:action+' a request',description:'Requires the current revision. Answer/cancel: requester only. Complete: requester or frozen parent decider, approved state only.',requestBody:{required:true,content:{'application/json':{schema:{$ref:'#/components/schemas/'+(action==='answer'?'Answer':'Mutation')}}}},responses:{'200':{description:'Updated request',content:{'application/json':{schema:{$ref:'#/components/schemas/Request'}}}},'400':{$ref:'#/components/responses/BadRequest'},'401':{$ref:'#/components/responses/Unauthorized'},'403':{$ref:'#/components/responses/Forbidden'},'404':{$ref:'#/components/responses/NotFound'},'409':{$ref:'#/components/responses/Conflict'}}}};
}
s.paths['/audit'].get.parameters=[{name:'cursor',in:'query',schema:{type:'integer',minimum:0}}];
s.paths['/audit'].get.responses['200'].content['application/json'].schema.properties.entries.items={oneOf:[{$ref:'#/components/schemas/AuditEntry'},{type:'object',required:['id','redacted'],properties:{id:{type:'integer'},redacted:{const:true}}}]};
s.components.schemas.AuditEntry.properties.id={type:'integer'};
s.paths['/requests'].get.parameters.push({name:'cursor',in:'query',schema:{type:'integer',minimum:0}},{name:'limit',in:'query',schema:{type:'integer',minimum:1,maximum:200,default:100}});
s.paths['/requests'].get.responses['200'].content['application/json'].schema.properties.nextCursor={type:['string','null']};
const generic={type:'object'};
s.paths['/auth/login']={post:{operationId:'login',summary:'Start an individual session',security:[],requestBody:{required:true,content:{'application/json':{schema:{type:'object',additionalProperties:false,required:['username','password'],properties:{username:{type:'string',maxLength:64},password:{type:'string',format:'password',maxLength:256}}}}}},responses:{'200':{description:'Opaque session; never persist or log the raw token',content:{'application/json':{schema:{type:'object',required:['accessToken','tokenType','expiresIn'],properties:{accessToken:{type:'string'},tokenType:{const:'Bearer'},expiresIn:{const:3600}}}}}},'400':{$ref:'#/components/responses/BadRequest'},'401':{$ref:'#/components/responses/Unauthorized'},'429':{description:'Ten login attempts per remote address per minute'}}}};
s.paths['/auth/logout']={post:{operationId:'logout',summary:'Revoke this session',responses:{'204':{description:'Revoked'},'401':{$ref:'#/components/responses/Unauthorized'}}}};
s.paths['/me']={get:{operationId:'getMe',summary:'Authenticated member ID and role',responses:{'200':{description:'Identity',content:{'application/json':{schema:generic}}},'401':{$ref:'#/components/responses/Unauthorized'}}}};
s.components.schemas.Role.enum=['parent','teen','child'];
s.components.schemas.RoutingRules.required=['rules','default','revision'];
s.components.schemas.RoutingRules.properties.default.properties.deciders.minItems=0;
s.components.schemas.RoutingRules.properties.default.properties.deciders.description='Empty only before operator configuration; PUT requires at least one enabled parent.';
// Include only referenced component objects, avoiding dangling design-only security schemes.
const needed=new Set();function walk(v){if(!v||typeof v!=='object')return;for(const [k,x]of Object.entries(v)){if(k==='$ref'&&x.startsWith('#/components/')){if(!needed.has(x)){needed.add(x);const [, ,section,name]=x.split('/');walk(s.components[section]?.[name]);}}else walk(x);}}
walk(s.paths);
for(const [section,objects] of Object.entries(s.components)){if(section==='securitySchemes')continue;for(const name of Object.keys(objects))if(!needed.has(`#/components/${section}/${name}`))delete objects[name];}
const content=YAML.stringify(s);
if(process.argv.includes('--check')){if(fs.readFileSync('openapi/runtime.yaml','utf8')!==content)throw new Error('Regenerate runtime.yaml');}else fs.writeFileSync('openapi/runtime.yaml',content);
