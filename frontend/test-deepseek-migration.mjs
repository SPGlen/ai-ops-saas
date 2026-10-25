import fs from 'node:fs/promises';
import assert from 'node:assert/strict';
import { PGlite } from '@electric-sql/pglite';
import { vector } from '@electric-sql/pglite-pgvector';
const pg = await PGlite.create({ extensions: { vector } });
await pg.exec('CREATE EXTENSION vector; CREATE ROLE ops_app NOSUPERUSER NOBYPASSRLS;');
const sql = await fs.readFile(new URL('../docs/migration-upgrade-0006.sql',import.meta.url),'utf8');
const idx = sql.indexOf('-- Running upgrade 0005_media_matrix -> 0006_deepseek');
assert(idx>0);
await pg.exec(sql.slice(0,idx));
await pg.exec(`INSERT INTO tenants(id,slug,name,status,settings,created_at) VALUES ('ds-a','ds-a','A','active','{}',now()),('ds-b','ds-b','B','active','{}',now());
INSERT INTO usage_records(id,tenant_id,created_at,request_id,resource,funding,reserved,actual,cost_fen,unit_rate_fen,unit_scale,estimated,state,period,updated_at) VALUES
('usage-a','ds-a',now(),'legacy-request-a','text_tokens','byok',20000,1234,17,1000,1000000,false,'settled','2026-10',now()),
('usage-b','ds-b',now(),'legacy-request-b','text_tokens','byok',20000,2345,19,1000,1000000,false,'settled','2026-10',now());`);
await pg.exec(sql.slice(idx));
assert.equal((await pg.query('SELECT version_num FROM alembic_version')).rows[0].version_num,'0006_deepseek');
const old = (await pg.query("SELECT actual,cost_fen,model_usage FROM usage_records WHERE id='usage-a'")).rows[0];
assert.equal(old.actual,1234);assert.equal(old.cost_fen,17);assert.deepEqual(old.model_usage,{});
const count = (await pg.query('SELECT count(*)::int AS n FROM pg_class WHERE relrowsecurity AND relforcerowsecurity')).rows[0].n;
assert.equal(count,48);
await pg.exec("SET ROLE ops_app; SELECT set_config('ops.tenant_id','ds-a',false);");
assert.equal((await pg.query('SELECT id FROM usage_records')).rows.length,1);
await pg.exec(`UPDATE usage_records SET model_usage='{"route":{"provider":"deepseek"}}' WHERE id='usage-a';`);
await pg.exec(`UPDATE usage_records SET model_usage='{"route":{"provider":"tampered"}}' WHERE id='usage-b';`);
await pg.exec('RESET ROLE');
assert.deepEqual((await pg.query("SELECT model_usage FROM usage_records WHERE id='usage-b'")).rows[0].model_usage,{});
const report={status:'passed',revision:'0006_deepseek',engine:'PGlite PostgreSQL WASM',native_postgresql:false,rls_tables:count,legacy_usage_preserved:true,tenant_isolation:true};
await fs.writeFile(new URL('../docs/deepseek-migration-test.json',import.meta.url),JSON.stringify(report,null,2));
console.log(JSON.stringify(report));await pg.close();
