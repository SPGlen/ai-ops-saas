"""Typed model and speech bridges used by the existing execution/recovery path."""
import json
from .matrix_agents import TopicSelection, MatrixDraft, TOPIC_INSTRUCTIONS, DIRECTOR_INSTRUCTIONS
from .security import fail
from .models import now
from .matrix import guard


def may_start(s, tid, task_id):
    try:
        guard(s, tid, task_id)
        return True
    except Exception:
        return False


def agent(s, tid, run):
    from .worker import agent_call
    public_input={k:v for k,v in run.input.items() if not k.startswith('_')}
    if len(json.dumps(public_input,ensure_ascii=False).encode("utf8")) > 10000:
        fail("BRAND_INPUT_TOO_LARGE", "品牌事实或来源资料过长，请缩小本次引用范围")
    output,used=agent_call(s,tid,run,TOPIC_INSTRUCTIONS if run.kind=='matrix_topic' else DIRECTOR_INSTRUCTIONS,json.dumps(public_input,ensure_ascii=False),TopicSelection if run.kind=='matrix_topic' else MatrixDraft)
    if run.kind=='matrix_topic':
        allowed={x.get('url') for x in run.input['sources']['items'] if x.get('url')}
        if not set(output.source_urls)<=allowed:
            fail('SOURCE_INVALID','选题引用了未提供的来源')
    else:
        allowed={f['id'] for f in run.input['facts']}
        if not set(output.source_ids)<=allowed:
            fail('SOURCE_INVALID','内容引用了品牌以外的事实')
        spec=run.input['spec']
        if output.render_mode not in spec['allowed_render_modes']:
            fail('RENDER_MODE_FORBIDDEN','导演选择了未授权的制作方式')
        if run.input['account']['form']=='video':
            seconds=sum(x.seconds for x in output.scenes)+2
            if len(output.scenes)<3 or not spec['min_video_seconds']<=seconds<=spec['max_video_seconds']:
                fail('STORYBOARD_INVALID','分镜数量或总时长不符合计划')
            kinds={x.kind for x in output.scenes if x.kind!='asset'}
            actual='mixed' if kinds=={'program','aigc'} else 'aigc' if kinds=={'aigc'} else 'program'
            if actual!=output.render_mode:
                fail('STORYBOARD_INVALID','分镜与声明的制作方式不一致')
            for scene in output.scenes:
                if scene.kind=='asset' and scene.asset_id not in run.input['profile']['asset_ids']:
                    fail('ASSET_CONSENT_REQUIRED','分镜引用了未授权的品牌素材')
                if scene.kind=='aigc' and not scene.prompt:
                    fail('STORYBOARD_INVALID','AIGC分镜缺少提示')
    result = output.model_dump()
    if run.kind == 'matrix_content':
        from .worker import price
        items = {'blind_prediction': price(s,'text_tokens',20000,tid,run.funding,'vision'), 'retrospective': price(s,'text_tokens',20000,tid,run.funding)}
        if run.input['account']['form'] == 'video':
            items['aigc_clips'] = sum(price(s,'video_seconds',10) for scene in output.scenes if scene.kind == 'aigc')
            items['speech'] = price(s,'speech_characters',sum(len(scene.narration) for scene in output.scenes))
        else:
            items['image'] = price(s,'images',1)
        result['estimated_remaining_cost_fen'] = sum(items.values())
        result['estimated_cost_items'] = items
    return result,used


def speech(s, tid, job):
    from .worker import finish_usage
    from .integrations import aliyun
    from .integrations.storage import save_asset, download_result
    url=job.parameters.get('result_url')
    if not url:
        if job.parameters.get('submitted'):
            fail('SPEECH_RESULT_UNKNOWN','配音结果未知，请勿重复提交',409)
        job.status='submitting'
        job.parameters={**job.parameters,'submitted':True}
        s.add(job);s.commit()
        url,chars=aliyun.speech(s,tid,job.funding,job.prompt)
        job.parameters={**job.parameters,'result_url':url}
        finish_usage(s,tid,job.request_id,'speech_characters',chars,job.funding)
        job.status='finishing'
        s.add(job);s.commit()
    raw=download_result(url)
    job.asset_ids=[save_asset(s,tid,'矩阵配音.wav',raw,'audio/wav',True).id]
    job.status='succeeded';job.updated_at=now()
    s.add(job);s.commit()
