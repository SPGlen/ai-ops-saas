"""Versioned educational rubrics. Predictions remain immutable when a rubric changes."""

import json, hashlib, math
from pydantic import BaseModel, Field
from sqlmodel import select
from .models import *
from .domain import query, own, audit
from .security import fail

DIMENSIONS = [
    "clarity",
    "relevance",
    "usefulness",
    "credibility",
    "narrative",
    "actionability",
    "accessibility",
]
BASE = {
    "image_text": {
        "clarity": "封面和标题清楚；卡片每页一个重点",
        "relevance": "解决目标年级家长的真实问题",
        "usefulness": "有可执行的亲子练习或课程信息",
        "credibility": "课程事实有依据，不编造背书或学习效果",
        "narrative": "图文顺序自然，有具体例子",
        "actionability": "下一步明确且不过度推销",
        "accessibility": "文字可读，图文信息一致，儿童信息脱敏",
    },
    "video": {
        "clarity": "前三秒明确主题，字幕与配音清楚",
        "relevance": "对目标家长有明确观看价值",
        "usefulness": "示范可复现，不只是工具展示",
        "credibility": "素材与事实可追溯，不承诺获奖提分",
        "narrative": "开头、示范、结尾衔接，时长与节奏合理",
        "actionability": "结尾给出具体可执行的行动",
        "accessibility": "字幕对比度、声音、封面、儿童隐私合适",
    },
}


def rubric(session, tenant_id, form, profile_id=None):
    tenant = session.get(Tenant, tenant_id)
    profile = own(session, MediaProfile, tenant_id, profile_id) if profile_id else None
    candidate_id = (profile.rubrics if profile else tenant.settings.get("rubrics", {})).get(form)
    if candidate_id:
        candidate = own(session, RubricCandidate, tenant_id, candidate_id)
        return {
            "version": candidate.id,
            "calibrated": False,
            "dimensions": BASE[form],
            "weights": candidate.weights,
            "notes": candidate.notes,
        }
    return {
        "version": (profile.id + ":" if profile else "") + "edu-" + form + "-v0",
        "calibrated": False,
        "dimensions": BASE[form],
        "weights": {k: 1 for k in DIMENSIONS},
        "notes": "初始规则未经实绩校准。",
    }


def score(payload, weights):
    return round(
        sum(payload[k] * weights[k] for k in DIMENSIONS) / sum(weights.values()) * 2, 2
    )


def corpus(session, tenant_id, form, profile_id=None):
    content_ids = [
        x.id
        for x in session.exec(
            query(session, Content, tenant_id).where(Content.form == form)
        ).all()
    ]
    scoped_tasks = session.exec(query(session, AutomationAccountTask, tenant_id)).all()
    matrix_content = {t.content_id for t in scoped_tasks if t.content_id}
    if profile_id:
        own(session, MediaProfile, tenant_id, profile_id)
        run_ids = {r.id for r in session.exec(query(session, AutomationRun, tenant_id)).all() if r.snapshot.get("profile", {}).get("id") == profile_id}
        allowed_content = {t.content_id for t in scoped_tasks if t.run_id in run_ids}
        content_ids = [c for c in content_ids if c in allowed_content]
    else:
        content_ids = [c for c in content_ids if c not in matrix_content]
    versions = session.exec(
        query(session, ContentVersion, tenant_id).where(
            ContentVersion.content_id.in_(content_ids)
        )
    ).all()
    jobs = session.exec(
        query(session, PublishJob, tenant_id).where(
            PublishJob.version_id.in_([v.id for v in versions])
        )
    ).all()
    job_versions = {
        j.id: j.version_id
        for j in jobs
        if j.status == "succeeded"
        and j.submitted_at
        and j.submitted_at <= now() - __import__("datetime").timedelta(days=3)
    }
    rows = session.exec(
        query(session, MetricSnapshot, tenant_id)
        .where(MetricSnapshot.eligible == True)
        .order_by(MetricSnapshot.created_at.desc())
    ).all()
    latest = {}
    for metric in rows:
        v = job_versions.get(metric.publish_job_id)
        if (
            v
            and v not in latest
            and any(x is not None for x in metric.metrics.values())
        ):
            latest[v] = metric
    metrics = list(latest.values())
    payload = {
        "versions": sorted((x.id, x.content_hash) for x in versions),
        "metrics": sorted((m.id, m.metrics) for m in metrics),
    }
    checksum = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
    return versions, metrics, checksum


class IndependentReview(BaseModel):
    acceptable: bool
    no_regression: bool
    reasons: list[str] = Field(min_length=1, max_length=15)


def process(session, tenant_id, run, tenant):
    from .integrations import aliyun
    from .config import settings
    from .agents import RubricScore, BLIND_INSTRUCTIONS

    candidate = own(session, RubricCandidate, tenant_id, run.input["candidate_id"])
    versions, metrics, checksum = corpus(session, tenant_id, candidate.form, candidate.profile_id)
    if checksum != candidate.corpus_hash:
        fail("CORPUS_CHANGED", "样本集已变化，请重新提交候选规则", 409)
    from .model_router import reservation
    route = reservation(session, tenant_id, run.request_id, run.funding, "review")
    score_model_name = route.get("score_model", settings().score_model)
    review_model_name = route.get("review_model", settings().review_model)
    if review_model_name == score_model_name:
        fail("INDEPENDENT_MODEL_REQUIRED", "复核模型必须与评分模型不同")
    results = list(candidate.report.get("results", []))
    used = int(candidate.report.get("used_tokens", 0))
    completed = {r["version_id"] for r in results}
    from .agents import blind_input

    current = rubric(session, tenant_id, candidate.form, candidate.profile_id)
    for version in versions:
        if version.id in completed:
            continue
        data = blind_input(session, tenant_id, version.id)
        data["rubric"] = {
            **current,
            "weights": candidate.weights,
            "notes": candidate.notes,
            "version": candidate.id,
        }
        from .blind_media import attachments
        from .worker import agent_call, authorize_actor

        authorize_actor(session, tenant_id, run.actor_id, {"owner"})
        out, tokens = agent_call(
            session,
            tenant_id,
            run,
            BLIND_INSTRUCTIONS,
            json.dumps(data, ensure_ascii=False),
            RubricScore,
            model_name=score_model_name,
            media=attachments(session, tenant_id, version.id),
        )
        payload = out.model_dump()
        used += tokens
        results.append(
            {
                "version_id": version.id,
                "scores": payload,
                "proposed": score(payload, candidate.weights),
                "baseline": score(payload, current["weights"]),
            }
        )
        candidate.report = {"results": results, "used_tokens": used}
        session.add(candidate)
        session.commit()
    pairs = [
        (a, b)
        for i, a in enumerate(results)
        for b in results[i + 1 :]
        if a["baseline"] != b["baseline"]
    ]
    agreement = (
        sum(
            (a["proposed"] - b["proposed"]) * (a["baseline"] - b["baseline"]) > 0
            for a, b in pairs
        )
        / len(pairs)
        if pairs
        else 0
    )
    from .worker import agent_call

    review, tokens = agent_call(
        session,
        tenant_id,
        run,
        "独立复核教育内容评分规则。只依据样本、重算结果和实绩，评估权重是否合理且无明显回归。不能修改原预测。缺少证据时acceptable=false。",
        json.dumps(
            {
                "candidate": {"weights": candidate.weights, "notes": candidate.notes},
                "results": [
                    {k: v for k, v in r.items() if k != "scores"} for r in results
                ],
                "metrics": [{"id": m.publish_job_id, **m.metrics} for m in metrics],
            },
            ensure_ascii=False,
        ),
        IndependentReview,
        model_name=review_model_name,
    )
    used += tokens
    candidate.report = {
        "results": results,
        "ranking_agreement": agreement,
        "independent_review": review.model_dump(),
        "review_model": review_model_name,
        "scoring_model": score_model_name,
        "eligible_metrics": len(metrics),
        "full_rescore": len(results) == len(versions),
    }
    candidate.status = (
        "reviewed"
        if agreement >= 0.8 and review.acceptable and review.no_regression
        else "rejected"
    )
    candidate.reviewed_at = now()
    session.add(candidate)
    return {
        "candidate_id": candidate.id,
        "status": candidate.status,
        "report": candidate.report,
    }, used
