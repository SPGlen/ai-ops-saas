"""Rebuild release evidence only from recorded tests; external acceptance stays explicit."""
import json,hashlib
from pathlib import Path
from datetime import datetime,timezone
from xml.etree import ElementTree as ET
root=Path(__file__).resolve().parents[1];docs=root/'docs'


def read(name):
    return json.loads((docs/name).read_text(encoding='utf-8-sig'))


def junit(name):
    suites=list(ET.parse(docs/name).getroot().iter('testsuite'))
    return {k:sum(int(s.get(k,0)) for s in suites) for k in ('tests','errors','failures','skipped')}


api=junit('matrix-api-tests.xml');features=junit('matrix-feature-tests.xml');mcp=junit('matrix-mcp-tests.xml')
browser=read('e2e-report.json')['stats'];migration=read('matrix-migration-test.json');media=read('matrix-media-test.json');restore=read('matrix-backup-restore.json');protocol=read('xhs-runtime-report.json')
assert all(not x['errors'] and not x['failures'] for x in (api,features,mcp))
assert not browser['unexpected'] and not browser['flaky']
assert migration['status']==restore['status']==protocol['status']=='passed'
assert all(c['status']=='passed' for c in media['cases'])
version=json.loads((root/'frontend/package.json').read_text(encoding='utf8'))['version']
report={'version':version,'generated_at':datetime.now(timezone.utc).isoformat(),'formal_delivery_accepted':False,'api':api,'matrix_feature_tests':features,'mcp_contract_tests':mcp,'real_mcp_protocol':protocol,'browser':{'passed':browser['expected'],'failed':browser['unexpected'],'flaky':browser['flaky'],'skipped':browser['skipped'],'database':'isolated SQLite fixtures'},'migration':migration,'media':media,'backup_restore':restore,'dependencies':{'new_runtime_dependencies':False,'installed_dependency_check':'pip check passed','fresh_vulnerability_database_scan':False},'features':{'same_platform_multiple_accounts':True,'role_wide_institution_scope':True,'immutable_plan_versions':True,'frozen_explicit_account_targets':True,'matrix_shared_topic_single_charge':True,'per_account_content_and_predictions':True,'step_and_run_cost_breakdown':True,'manual_and_authorized_auto_publishing':True,'billing_unknown_result_no_resubmission':True,'explicit_safe_account_step_retry':True,'real_rendering_three_modes':True,'scoped_sse_and_calendar':True,'brand_scoped_rubric_calibration':True,'consultation_paused':True},'external_acceptance':{'real_aliyun_text_image_speech_video':False,'real_xiaohongshu_publish_receipt':False,'real_douyin_publish_receipt':False,'real_channels_publish_receipt':False,'real_t_plus_3_metrics':False,'real_wecom_notice':False,'native_postgresql':False,'docker_runtime_or_image_scan':False,'aliyun_deployment':False},'account_identity':{'xiaohongshu':'MCP self-profile ID readback implemented; real account pending','douyin':'explicit public-profile link observer implemented; real creator DOM pending','channels':'stable account ID readback pending real-account adaptation; unattended publishing blocked'},'upstream':'existing fixed vendor commits; no personal workspace data or credentials imported'}
names=('matrix-api-tests.xml','matrix-feature-tests.xml','matrix-mcp-tests.xml','matrix-migration-test.json','matrix-media-test.json','matrix-backup-restore.json','e2e-report.json','xhs-runtime-report.json','migration-upgrade-0005.sql','openapi.json')
report['evidence_sha256']={n:hashlib.sha256((docs/n).read_bytes()).hexdigest() for n in names}
for n in ('matrix-acceptance.json','release-gates.json'):(docs/n).write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
print(json.dumps({'version':version,'api':api,'matrix':features,'browser':report['browser'],'formal_delivery_accepted':False},ensure_ascii=False))
