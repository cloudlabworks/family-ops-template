import fs from 'node:fs';
import YAML from 'yaml';
import Ajv2020 from 'ajv/dist/2020.js';
import addFormats from 'ajv-formats';
const spec=YAML.parse(fs.readFileSync('openapi/runtime.yaml','utf8'));
const ajv=new Ajv2020({strict:false,allErrors:true});addFormats(ajv);
ajv.addSchema({$id:'runtime',components:spec.components});
const refs=o=>Array.isArray(o)?o.map(refs):o&&typeof o==='object'?Object.fromEntries(Object.entries(o).map(([k,v])=>[k,k==='$ref'&&v.startsWith('#/')?'runtime'+v:refs(v)])):o;
let checked=0;
for(const row of JSON.parse(fs.readFileSync(process.argv[2],'utf8'))){
 const path=(spec.paths[row.path]?row.path:null)||Object.keys(spec.paths).find(p=>new RegExp('^'+p.replace(/\{[^}]+\}/g,'[^/]+')+'$').test(row.path));
 if(!path){if(row.status===404)continue;throw new Error('Undocumented route '+row.path);}
 let response=spec.paths[path][row.method]?.responses[String(row.status)];
 if(!response)throw new Error('Undocumented status '+JSON.stringify(row));
 if(response.$ref)response=spec.components.responses[response.$ref.split('/').at(-1)];
 const content=response.content&&Object.values(response.content)[0];
 if(content){const validate=ajv.compile(refs(content.schema));if(!validate(row.body))throw new Error(JSON.stringify({path:row.path,status:row.status,errors:validate.errors}));checked++;}
}
console.log(`Runtime response contract: ${checked} actual HTTP-handler responses validated`);
