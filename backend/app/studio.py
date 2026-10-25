"""Versioned form definitions and a durable, permission checked DAG workflow runtime."""

import json, hashlib, re
from contextvars import ContextVar
from datetime import datetime
from decimal import Decimal, InvalidOperation
from sqlmodel import select
from sqlalchemy import update
from .models import *
from .domain import query, own, create_record, update_record, plain_data
from .permissions import Scope, has, permit, member_roles, identity_for
from .security import fail, encrypt, decrypt
from .operations import event

EXECUTING = ContextVar("workflow_executing", default="")
ROLES = {"owner", "teacher", "academic_admin", "finance", "admissions", "content_ops"}
BINDINGS = {
    "independent",
    "lead",
    "student",
    "class",
    "leave",
    "transfer",
    "refund",
    "reversal",
    "expense",
    "enrollment",
}
TYPES = {
    "text",
    "textarea",
    "number",
    "money",
    "date",
    "datetime",
    "select",
    "multiselect",
    "boolean",
    "attachment",
    "reference",
    "table",
}
ACTIONS = {
    "lead",
    "student",
    "class",
    "leave",
    "transfer",
    "refund",
    "reversal",
    "expense",
    "enrollment",
    "notify",
}


def canonical(value):
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str
    )


def fingerprint(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def unseal(t, value):
    return json.loads(decrypt(t, value))


def seal(t, value):
    return encrypt(t, canonical(value))


def actor(s, t, uid):
    i = identity_for(s, s.get(Tenant, t), uid)
    if not i:
        fail("ROLE_FORBIDDEN", "发起人的机构权限已经失效", 403)
    return i


def condition(rule, values):
    if not rule:
        return True
    if "all" in rule:
        return all(condition(x, values) for x in rule["all"])
    if "any" in rule:
        return any(condition(x, values) for x in rule["any"])
    a = values.get(rule.get("field"))
    b = rule.get("value")
    op = rule.get("op", "eq")
    if isinstance(a, bool) and isinstance(b, str):
        if b.lower() in ("true", "是", "1"):
            b = True
        elif b.lower() in ("false", "否", "0"):
            b = False
    elif (
        isinstance(a, (int, float, Decimal))
        and not isinstance(a, bool)
        and isinstance(b, str)
    ):
        try:
            b = Decimal(b)
        except InvalidOperation:
            pass
    if op == "eq":
        return a == b
    if op == "ne":
        return a != b
    if op == "in":
        return a in b if isinstance(b, list) else False
    if op == "exists":
        return a not in (None, "", [])
    try:
        aa = Decimal(str(a))
        bb = Decimal(str(b))
        return {"gt": aa > bb, "gte": aa >= bb, "lt": aa < bb, "lte": aa <= bb}.get(
            op, False
        )
    except (InvalidOperation, TypeError, ValueError):
        return False


def validate_rule(rule, depth=0):
    if not isinstance(rule, dict) or depth > 8:
        fail("SCHEMA_INVALID", "条件表达式错误")
    for operator in ("all", "any"):
        if operator in rule:
            if not isinstance(rule[operator], list) or len(rule[operator]) > 30:
                fail("SCHEMA_INVALID", "条件过多")
            for child in rule[operator]:
                validate_rule(child, depth + 1)
            return
    if rule and (
        rule.get("op", "eq")
        not in ("eq", "ne", "in", "exists", "gt", "gte", "lt", "lte")
        or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,79}", rule.get("field", ""))
    ):
        fail("SCHEMA_INVALID", "不支持的条件")


def validate_fields(fields, depth=0):
    if not isinstance(fields, list) or len(fields) > 80 or depth > 2:
        fail("SCHEMA_INVALID", "字段数量或子表层数超限")
    keys = set()
    for f in fields:
        if (
            not isinstance(f, dict)
            or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,79}", f.get("key", ""))
            or f["key"] in keys
        ):
            fail("SCHEMA_INVALID", "字段标识必须唯一且使用字母数字下划线")
        keys.add(f["key"])
        if f.get("type") not in TYPES or not str(f.get("label", "")).strip():
            fail("SCHEMA_INVALID", "字段名称或类型错误")
        for k in ("read_roles", "edit_roles"):
            if k in f and (not isinstance(f[k], list) or not set(f[k]) <= ROLES):
                fail("SCHEMA_INVALID", "字段岗位错误")
        if f.get("visible_when"):
            validate_rule(f["visible_when"])
        if f["type"] == "table":
            validate_fields(f.get("fields", []), depth + 1)
        if f["type"] == "reference" and f.get("ref") not in (
            "student",
            "class",
            "lead",
            "order",
            "enrollment",
            "lesson",
        ):
            fail("SCHEMA_INVALID", "关联来源错误")


def validate_spec(kind, spec):
    if kind == "form":
        validate_fields(spec.get("fields", []))
        return
    nodes = spec.get("nodes", [])
    edges = spec.get("edges", [])
    if not 2 <= len(nodes) <= 100 or len(edges) > 200:
        fail("FLOW_INVALID", "流程需要2至100个节点")
    ids = {n.get("id") for n in nodes}
    if len(ids) != len(nodes) or not all(
        isinstance(x, str) and re.fullmatch(r"[A-Za-z0-9_-]{1,80}", x) for x in ids
    ):
        fail("FLOW_INVALID", "节点编号重复或无效")
    starts = [n for n in nodes if n.get("data", {}).get("kind") == "start"]
    ends = [n for n in nodes if n.get("data", {}).get("kind") == "end"]
    if len(starts) != 1 or not ends:
        fail("FLOW_INVALID", "需要一个开始节点和至少一个结束节点")
    allowed = {
        "start",
        "end",
        "form",
        "approval",
        "condition",
        "parallel",
        "join",
        "notify",
        "action",
    }
    outgoing = {x: [] for x in ids}
    incoming = {x: [] for x in ids}
    for e in edges:
        if e.get("source") not in ids or e.get("target") not in ids:
            fail("FLOW_INVALID", "连线引用了不存在的节点")
        outgoing[e["source"]].append(e)
        incoming[e["target"]].append(e["source"])
    for n in nodes:
        d = n.get("data", {})
        k = d.get("kind")
        if k not in allowed:
            fail("FLOW_INVALID", "未知节点类型")
        if k != "end" and not outgoing[n["id"]]:
            fail("FLOW_INVALID", "非结束节点必须连接后续节点")
        if k in ("form", "approval"):
            if d.get("fields"):
                validate_fields(d["fields"])
            if not d.get("roles") and not d.get("users"):
                fail("FLOW_INVALID", "请选择处理岗位或人员")
            if not set(d.get("roles", [])) <= ROLES:
                fail("FLOW_INVALID", "处理岗位无效")
            if d.get("mode", "all") not in ("all", "any"):
                fail("FLOW_INVALID", "会签规则错误")
        if k == "condition":
            validate_rule(d.get("condition", {}))
            if sorted(e.get("data", {}).get("branch") for e in outgoing[n["id"]]) != [
                "no",
                "yes",
            ]:
                fail("FLOW_INVALID", "条件节点必须有“是”和“否”两条连线")
        if k == "action" and d.get("action") not in ACTIONS:
            fail("FLOW_INVALID", "业务动作未注册")
    visiting = set()
    visited = set()

    def walk(x):
        if x in visiting:
            fail("FLOW_INVALID", "不允许循环，退回修改请使用实例退回操作")
        if x in visited:
            return
        visiting.add(x)
        for e in outgoing[x]:
            walk(e["target"])
        visiting.remove(x)
        visited.add(x)

    walk(starts[0]["id"])
    if visited != ids:
        fail("FLOW_INVALID", "存在无法到达的节点")
    good = {n["id"] for n in ends}
    for _ in nodes:
        good |= {
            n["id"]
            for n in nodes
            if any(e["target"] in good for e in outgoing[n["id"]])
        }
    if good != ids:
        fail("FLOW_INVALID", "存在不能结束的路径")


def field_access(f, i, edit=False):
    if "owner" in i.roles:
        return True
    rs = f.get("edit_roles" if edit else "read_roles", list(ROLES))
    return bool(i.roles & set(rs))


def values_for(i, fields, values, edit=False):
    if not isinstance(values, dict):
        fail("FORM_INVALID", "表单数据格式错误")
    known = {f["key"] for f in fields}
    if edit and set(values) - known:
        fail("FORM_INVALID", "存在未定义的字段")
    out = {}
    for f in fields:
        k = f["key"]
        v = values.get(k)
        if not field_access(f, i, edit):
            if edit and k in values:
                fail("FIELD_FORBIDDEN", "无权填写字段：" + f["label"], 403)
            continue
        if not condition(f.get("visible_when", {}), values):
            continue
        if v in (None, "", []):
            if edit and f.get("required"):
                fail("FORM_REQUIRED", "请填写：" + f["label"])
            continue
        typ = f["type"]
        if typ in ("number", "money"):
            try:
                d = Decimal(str(v))
            except InvalidOperation:
                fail("FORM_INVALID", f["label"] + "需要数字")
            if (
                not d.is_finite()
                or ("min" in f and d < Decimal(str(f["min"])))
                or ("max" in f and d > Decimal(str(f["max"])))
            ):
                fail("FORM_INVALID", f["label"] + "超出范围")
            if typ == "money" and d.as_tuple().exponent < -2:
                fail("FORM_INVALID", "金额最多两位小数")
            v = str(d) if typ == "money" else float(d)
        elif typ in ("date", "datetime"):
            try:
                datetime.fromisoformat(str(v))
            except ValueError:
                fail("FORM_INVALID", f["label"] + "日期错误")
        elif typ in ("select", "multiselect"):
            selected = v if typ == "multiselect" else [v]
            if not isinstance(selected, list) or not set(selected) <= set(
                f.get("options", [])
            ):
                fail("FORM_INVALID", f["label"] + "选项错误")
        elif typ == "boolean":
            if not isinstance(v, bool):
                fail("FORM_INVALID", f["label"] + "需要勾选值")
        elif typ == "reference":
            Scope(i).own(str(v), f["ref"])
        elif typ == "attachment":
            from .permissions import check_asset

            if not isinstance(v, list) or len(v) > 10:
                fail("FORM_INVALID", "附件数量错误")
            for aid in v:
                check_asset(i, own(i.session, Asset, i.tenant.id, aid))
        elif typ == "table":
            if not isinstance(v, list) or len(v) > 100:
                fail("FORM_INVALID", "子表最多100行")
            v = [values_for(i, f.get("fields", []), row, edit) for row in v]
        else:
            if not isinstance(v, str) or len(v) > 5000:
                fail("FORM_INVALID", f["label"] + "文本过长")
        out[k] = v
    return out


def definition_version(s, t, d, version=None):
    v = s.exec(
        query(s, StudioVersion, t).where(
            StudioVersion.definition_id == d.id,
            StudioVersion.version == (version or d.published_version),
        )
    ).first()
    if not v:
        fail("VERSION_REQUIRED", "请先发布表单或流程")
    return v


def eligible(s, t, data):
    candidates = []
    for m in s.exec(select(Membership).where(Membership.tenant_id == t)).all():
        if not member_roles(m):
            continue
        if m.user_id in data.get("users", []) or member_roles(m) & set(
            data.get("roles", [])
        ):
            u = s.get(User, m.user_id)
            if u and u.verified and not u.disabled:
                candidates.append(m.user_id)
    return sorted(set(candidates))


def can_view_instance(i, inst):
    try:
        check_binding(i, inst.binding, inst.record_id)
        source = unseal(i.tenant.id, inst.payload_cipher).get("_form_submission_id")
        if source:
            form = own(i.session, FormSubmission, i.tenant.id, source)
            check_binding(i, form.binding, form.record_id)
    except Exception:
        return False
    if "owner" in i.roles:
        return True
    if inst.actor_id == i.user.id:
        if inst.binding in ("refund", "expense", "reversal") and not has(
            i, "finance.read"
        ):
            return False
        return True
    return bool(
        i.session.exec(
            query(i.session, FlowTask, i.tenant.id).where(
                FlowTask.instance_id == inst.id, FlowTask.assignee_id == i.user.id
            )
        ).first()
    )


def check_binding(i, binding, rid="", write=False):
    cap = {
        "refund": "finance.write",
        "reversal": "finance.write",
        "expense": "expense.write",
        "transfer": "enrollment.write",
        "independent": "",
        "notify": "tenant.manage",
    }.get(binding, binding + (".write" if write else ".read"))
    if cap:
        permit(i, cap)
    if rid and binding == "student" and not write:
        scope = Scope(i)
        student = scope.own(rid, "student")
        full = (
            bool(i.roles & {"owner", "academic_admin"})
            or ("teacher" in i.roles and rid in scope.students)
            or (
                "admissions" in i.roles
                and (rid in scope.sales_students or student.created_by == i.user.id)
            )
        )
        if not full:
            fail("ROLE_FORBIDDEN", "当前岗位仅可读取必要的财务关联学员资料", 403)
    if rid:
        if binding == "reversal":
            own(i.session, LedgerEntry, i.tenant.id, rid)
            return
        kind = {"refund": "order", "transfer": "enrollment"}.get(binding, binding)
        if kind != "independent":
            Scope(i).own(rid, kind, "read")


def lock_instance(i, instance_id):
    i.session.exec(
        update(FlowInstance)
        .where(FlowInstance.tenant_id == i.tenant.id, FlowInstance.id == instance_id)
        .values(revision=FlowInstance.revision)
        .execution_options(synchronize_session=False)
    )
    return i.session.exec(
        query(i.session, FlowInstance, i.tenant.id)
        .where(FlowInstance.id == instance_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    ).first()


def lock_definition(i, definition_id):
    i.session.exec(
        update(StudioDefinition)
        .where(
            StudioDefinition.tenant_id == i.tenant.id,
            StudioDefinition.id == definition_id,
        )
        .values(version=StudioDefinition.version)
        .execution_options(synchronize_session=False)
    )
    return i.session.exec(
        query(i.session, StudioDefinition, i.tenant.id)
        .where(StudioDefinition.id == definition_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    ).one()


def publish(i, d):
    if "owner" not in i.roles:
        fail("ROLE_FORBIDDEN", "只有负责人可发布定义", 403)
    d = lock_definition(i, d.id)
    spec = json.loads(canonical(d.draft))
    if d.kind == "form" and spec.get("workflow_id"):
        linked = own(i.session, StudioDefinition, i.tenant.id, spec["workflow_id"])
        if linked.kind != "workflow" or linked.binding != "independent":
            fail("FLOW_INVALID", "扩展表单请选择独立审批流程")
        linked_version = definition_version(i.session, i.tenant.id, linked)
        if any(n["data"]["kind"] == "action" for n in linked_version.spec["nodes"]):
            fail("FLOW_INVALID", "扩展表单审批不能直接修改核心业务")
        spec["workflow_version"] = linked_version.version
    if d.kind == "workflow":
        for node in spec.get("nodes", []):
            data = node.get("data", {})
            if data.get("kind") == "form" and data.get("form_definition_id"):
                form = own(
                    i.session, StudioDefinition, i.tenant.id, data["form_definition_id"]
                )
                if form.kind != "form":
                    fail("FLOW_INVALID", "填写节点必须选择表单")
                version = definition_version(i.session, i.tenant.id, form)
                data.update(
                    fields=version.spec.get("fields", []), form_version=version.version
                )
    validate_spec(d.kind, spec)
    if d.kind == "workflow":
        for n in d.draft["nodes"]:
            if n["data"]["kind"] == "action" and n["data"].get("action") not in (
                "notify",
                d.binding,
            ):
                fail("FLOW_INVALID", "动作必须与绑定业务一致")
            users = n.get("data", {}).get("users", [])
            for user in users:
                actor(i.session, i.tenant.id, user)
    d.published_version += 1
    d.version += 1
    i.session.add(d)
    v = StudioVersion(
        tenant_id=i.tenant.id,
        definition_id=d.id,
        kind=d.kind,
        version=d.published_version,
        spec=spec,
    )
    i.session.add(v)
    event(
        i.session,
        i.tenant.id,
        i.user.id,
        "definition.published",
        d.id,
        {"version": d.published_version},
    )
    return d


def guard_action(i, binding, rid, payload, workflow_id=""):
    s = i.session
    t = i.tenant.id
    active = s.exec(
        query(s, StudioDefinition, t).where(
            StudioDefinition.kind == "workflow",
            StudioDefinition.binding == binding,
            StudioDefinition.enabled == True,
        )
    ).first()
    if not active:
        return
    wid = EXECUTING.get() or workflow_id
    if not wid:
        fail("WORKFLOW_REQUIRED", "该业务已启用审批，请先完成对应流程", 409)
    inst = own(s, FlowInstance, t, wid)
    approved = unseal(t, inst.payload_cipher)
    if (
        inst.definition_id != active.id
        or inst.binding != binding
        or inst.record_id != rid
        or fingerprint(approved.get("business", approved)) != fingerprint(payload)
    ):
        fail("WORKFLOW_MISMATCH", "审批与本次操作内容不一致", 409)
    if EXECUTING.get() == inst.id:
        return
    if inst.status != "approved":
        fail("WORKFLOW_REQUIRED", "流程未审批通过或已使用", 409)
    if (
        rid
        and binding != "reversal"
        and inst.state.get("record_version") != own(s, Record, t, rid).version
    ):
        fail("WORKFLOW_STALE", "业务记录已变更，请重新提交审批", 409)
    inst.status = "consumed"
    s.add(inst)
    event(s, t, i.user.id, "workflow.consumed", inst.id)


def submit(i, d, payload, rid, request_id, version_number=None):
    check_binding(i, d.binding, rid, True)
    previous = i.session.exec(
        query(i.session, FlowInstance, i.tenant.id).where(
            FlowInstance.request_id == request_id
        )
    ).first()
    if previous:
        if (
            previous.actor_id != i.user.id
            or previous.definition_id != d.id
            or previous.record_id != rid
            or fingerprint(unseal(i.tenant.id, previous.payload_cipher))
            != fingerprint(payload)
        ):
            fail("IDEMPOTENCY_CONFLICT", "请求编号已用于其他内容", 409)
        return previous
    version = definition_version(i.session, i.tenant.id, d, version_number)
    validate_spec("workflow", version.spec)
    inst = FlowInstance(
        tenant_id=i.tenant.id,
        definition_id=d.id,
        definition_version=version.version,
        actor_id=i.user.id,
        binding=d.binding,
        record_id=rid,
        payload_cipher=seal(i.tenant.id, payload),
        request_id=request_id,
        state={
            "done": [],
            "decisions": {},
            "record_version": own(i.session, Record, i.tenant.id, rid).version
            if rid and d.binding != "reversal"
            else 0,
        },
    )
    i.session.add(inst)
    i.session.flush()
    advance(i.session, inst, i)
    event(i.session, i.tenant.id, i.user.id, "workflow.submitted", inst.id)
    return inst


def graph_state(spec, state, payload):
    nodes = {n["id"]: n for n in spec["nodes"]}
    out = {k: [] for k in nodes}
    for e in spec["edges"]:
        out[e["source"]].append(e)
    start = next(k for k, n in nodes.items() if n["data"]["kind"] == "start")
    reachable = set()
    stack = [start]
    decisions = state.get("decisions", {})
    while stack:
        nid = stack.pop()
        if nid in reachable:
            continue
        reachable.add(nid)
        for edge in out[nid]:
            if (
                nid in decisions
                and edge.get("data", {}).get("branch") != decisions[nid]
            ):
                continue
            stack.append(edge["target"])
    return nodes, reachable, out


def apply_action(i, inst, data):
    action = data["action"]
    payload = unseal(i.tenant.id, inst.payload_cipher)
    body = payload.get("business", payload)
    if action != "notify" and action != inst.binding:
        fail("FLOW_INVALID", "流程动作与绑定业务不一致")
    check_binding(i, action, inst.record_id, True)
    if (
        inst.record_id
        and inst.binding != "reversal"
        and inst.state.get("record_version")
        != own(i.session, Record, i.tenant.id, inst.record_id).version
    ):
        fail("WORKFLOW_STALE", "业务已更新，请重新提交审批", 409)
    token = EXECUTING.set(inst.id)
    try:
        if action == "refund":
            if not inst.state.get("actual_confirmed"):
                fail("ACTUAL_CONFIRMATION_REQUIRED", "请由财务确认退款实际发生")
            from .routes_operations import RefundInput
            from .operations import refund

            refund(
                i,
                inst.record_id,
                RefundInput(**body, request_id="flow:" + inst.id, workflow_id=inst.id),
            )
        elif action == "reversal":
            from .domain import reverse_money

            if not inst.state.get("actual_confirmed"):
                fail("ACTUAL_CONFIRMATION_REQUIRED", "请确认冲正依据")
            reverse_money(
                i.session, i.tenant.id, i.user.id, inst.record_id, "flow:" + inst.id
            )
        elif action == "transfer":
            from .operations import transfer

            transfer(
                i,
                inst.record_id,
                body["class_id"],
                body.get("effective_at"),
                body.get("reason", ""),
            )
        elif action == "notify":
            from .reports import enqueue

            enqueue(
                i.session,
                i.tenant,
                "flow:" + inst.id,
                "workflow",
                "流程待办有更新，请登录查看。",
            )
        else:
            if (
                action == "expense"
                and body.get("status") == "confirmed"
                and not inst.state.get("actual_confirmed")
            ):
                fail("ACTUAL_CONFIRMATION_REQUIRED", "请确认费用实际发生")
            initiator = actor(i.session, i.tenant.id, inst.actor_id)
            values = Scope(initiator).validate_write(
                action,
                dict(body),
                Scope(i).own(inst.record_id, action, "write")
                if inst.record_id
                else None,
            )
            if inst.record_id:
                update_record(
                    i.session,
                    i.tenant.id,
                    i.user.id,
                    inst.record_id,
                    values,
                    inst.state.get("record_version", 0),
                )
            else:
                create_record(i.session, i.tenant.id, i.user.id, action, values)
    finally:
        EXECUTING.reset(token)


def advance(s, inst, i):
    d = own(s, StudioDefinition, inst.tenant_id, inst.definition_id)
    spec = definition_version(s, inst.tenant_id, d, inst.definition_version).spec
    state = json.loads(canonical(inst.state))
    done = set(state.get("done", []))
    payload = unseal(inst.tenant_id, inst.payload_cipher)
    fields = {**payload.get("business", payload), **payload.get("values", {})}
    for _ in range(len(spec["nodes"]) + 1):
        nodes, reachable, out = graph_state(spec, state, fields)
        progress = False
        for nid, n in nodes.items():
            if nid not in reachable or nid in done:
                continue
            incoming = [
                e["source"]
                for e in spec["edges"]
                if e["target"] == nid
                and e["source"] in reachable
                and (
                    e["source"] not in state.get("decisions", {})
                    or e.get("data", {}).get("branch")
                    == state["decisions"][e["source"]]
                )
            ]
            data = n["data"]
            kind = data["kind"]
            ready = not incoming or (
                any(x in done for x in incoming)
                if kind == "join" and data.get("mode") == "any"
                else all(x in done for x in incoming)
            )
            if not ready:
                continue
            if kind in ("form", "approval"):
                tasks = s.exec(
                    query(s, FlowTask, inst.tenant_id).where(
                        FlowTask.instance_id == inst.id, FlowTask.node_id == nid
                    )
                ).all()
                if not tasks:
                    users = eligible(s, inst.tenant_id, data)
                    for uid_ in users or [""]:
                        s.add(
                            FlowTask(
                                tenant_id=inst.tenant_id,
                                instance_id=inst.id,
                                node_id=nid,
                                assignee_id=uid_,
                                node_type=kind,
                                status="pending" if uid_ else "unassigned",
                            )
                        )
                    s.flush()
                    continue
                ok = [t for t in tasks if t.status == "approved"]
                satisfied = (
                    bool(ok)
                    if data.get("mode", "all") == "any"
                    else len(ok) == len(tasks)
                )
                if not satisfied:
                    continue
                for t in tasks:
                    if t.status in ("pending", "unassigned"):
                        t.status = "cancelled"
                        s.add(t)
            elif kind == "join" and data.get("mode") == "any":
                # Cancel unfinished, exclusive ancestors of losing branches.
                # Shared prerequisites feeding another path must keep running.
                reverse = {key: [] for key in nodes}
                for edge in spec["edges"]:
                    if edge["source"] in reachable and edge["target"] in reachable:
                        reverse[edge["target"]].append(edge["source"])

                def ancestors(key):
                    found = set()
                    stack = [key]
                    while stack:
                        x = stack.pop()
                        if x in found:
                            continue
                        found.add(x)
                        stack.extend(reverse[x])
                    return found

                winners = set().union(*(ancestors(x) for x in incoming if x in done))
                losing = (
                    set().union(*(ancestors(x) for x in incoming if x not in done))
                    if any(x not in done for x in incoming)
                    else set()
                )
                cancelled = losing - winners - done
                while True:
                    keep = {
                        key
                        for key in cancelled
                        if any(
                            e["target"] in reachable
                            and e["target"] not in cancelled
                            and e["target"] != nid
                            for e in out[key]
                        )
                    }
                    if not keep:
                        break
                    cancelled -= keep
                if cancelled:
                    for task in s.exec(
                        query(s, FlowTask, inst.tenant_id).where(
                            FlowTask.instance_id == inst.id,
                            FlowTask.node_id.in_(cancelled),
                        )
                    ).all():
                        if task.status in ("pending", "unassigned"):
                            task.status = "cancelled"
                            s.add(task)
                    done |= cancelled
                    state["cancelled"] = sorted(
                        set(state.get("cancelled", [])) | cancelled
                    )
            elif kind == "condition":
                state.setdefault("decisions", {})[nid] = (
                    "yes" if condition(data.get("condition", {}), fields) else "no"
                )
            elif kind == "action":
                apply_action(i, inst, data)
            elif kind == "notify":
                from .reports import enqueue

                enqueue(
                    s,
                    i.tenant,
                    "flow:" + inst.id + ":" + nid,
                    "workflow",
                    "机构流程待办有更新，请登录查看。",
                )
            done.add(nid)
            state["done"] = sorted(done)
            progress = True
            if kind == "condition":
                # Rebuild reachability before touching either downstream branch.
                break
        if not progress:
            break
    inst.state = state
    if any(n["data"]["kind"] == "end" and nid in done for nid, n in nodes.items()):
        pending = s.exec(
            query(s, FlowTask, inst.tenant_id).where(
                FlowTask.instance_id == inst.id,
                FlowTask.status.in_(["pending", "unassigned"]),
            )
        ).all()
        if not pending:
            inst.status = (
                "completed"
                if any(n["data"]["kind"] == "action" for n in nodes.values())
                else "approved"
            )
    s.add(inst)
    s.flush()
    source = payload.get("_form_submission_id")
    if source:
        form = own(s, FormSubmission, inst.tenant_id, source)
        form.status = inst.status
        s.add(form)


def decide(i, task_id, decision, note, values=None):
    if decision not in ("approve", "reject", "return"):
        fail("DECISION_INVALID", "审批动作错误")
    task = own(i.session, FlowTask, i.tenant.id, task_id)
    inst = own(i.session, FlowInstance, i.tenant.id, task.instance_id)
    inst = lock_instance(i, inst.id)
    i.session.refresh(task)
    if inst.status != "running" or task.status != "pending":
        fail("STATE_INVALID", "待办已处理", 409)
    spec = definition_version(
        i.session,
        i.tenant.id,
        own(i.session, StudioDefinition, i.tenant.id, inst.definition_id),
        inst.definition_version,
    ).spec
    node = next(n["data"] for n in spec["nodes"] if n["id"] == task.node_id)
    allowed = eligible(i.session, i.tenant.id, node)
    if inst.state.get("assignee_overrides", {}).get(task.id) == i.user.id:
        check_binding(i, inst.binding, inst.record_id, True)
        allowed.append(i.user.id)
    if task.assignee_id != i.user.id or i.user.id not in allowed:
        fail("ROLE_FORBIDDEN", "审批权限已失效", 403)
    check_binding(
        actor(i.session, i.tenant.id, inst.actor_id), inst.binding, inst.record_id, True
    )
    if decision != "approve" and not note.strip():
        fail("REASON_REQUIRED", "驳回或退回需要原因")
    if task.node_type == "form" and decision == "approve":
        if inst.binding in ("refund", "expense", "reversal"):
            permit(i, "finance.write")
            if not values or values.get("actual_confirmed") is not True:
                fail("ACTUAL_CONFIRMATION_REQUIRED", "请勾选确认实际发生")
            inst.state = {**inst.state, "actual_confirmed": True}
        else:
            fields = node.get("fields", [])
            checked = values_for(i, fields, values or {}, True) if fields else {}
            if checked:
                payload = unseal(i.tenant.id, inst.payload_cipher)
                business = payload.get("business", {})
                if any(k in business and business[k] != v for k, v in checked.items()):
                    fail(
                        "WORKFLOW_RESUBMIT",
                        "关键业务数据改变，需退回修改后重新审批",
                        409,
                    )
                payload.setdefault("values", {}).update(checked)
                inst.payload_cipher = seal(i.tenant.id, payload)
    task.status = {"approve": "approved", "reject": "rejected", "return": "returned"}[
        decision
    ]
    task.decision_note = note
    task.decided_at = now()
    i.session.add(task)
    i.session.flush()
    if decision != "approve":
        inst.status = task.status
        for other in i.session.exec(
            query(i.session, FlowTask, i.tenant.id).where(
                FlowTask.instance_id == inst.id,
                FlowTask.status.in_(["pending", "unassigned"]),
            )
        ).all():
            other.status = "cancelled"
            i.session.add(other)
    else:
        advance(i.session, inst, i)
    i.session.add(inst)
    source = unseal(i.tenant.id, inst.payload_cipher).get("_form_submission_id")
    if source:
        form = own(i.session, FormSubmission, i.tenant.id, source)
        form.status = inst.status
        i.session.add(form)
    event(
        i.session,
        i.tenant.id,
        i.user.id,
        "workflow." + decision,
        inst.id,
        {"node": task.node_id, "note": note},
    )
    return inst


def templates():
    result = []
    for binding, name, roles in [
        ("lead", "招生跟进", ["admissions"]),
        ("leave", "请假审批", ["academic_admin"]),
        ("transfer", "调班审批", ["academic_admin"]),
        ("refund", "退读退费审批", ["owner"]),
        ("reversal", "账务冲正审批", ["owner"]),
        ("expense", "费用审批", ["owner"]),
        ("independent", "自定义表单审批", ["owner"]),
    ]:
        nodes = [
            {
                "id": "start",
                "position": {"x": 40, "y": 100},
                "data": {"kind": "start", "label": "开始"},
            },
            {
                "id": "review",
                "position": {"x": 280, "y": 100},
                "data": {
                    "kind": "approval",
                    "label": "审核",
                    "roles": roles,
                    "mode": "all",
                },
            },
            {
                "id": "end",
                "position": {"x": 760, "y": 100},
                "data": {"kind": "end", "label": "完成"},
            },
        ]
        edges = [{"id": "a", "source": "start", "target": "review"}]
        if binding in ("refund", "expense", "reversal"):
            nodes.insert(
                2,
                {
                    "id": "actual",
                    "position": {"x": 510, "y": 100},
                    "data": {
                        "kind": "form",
                        "label": "财务确认实际发生",
                        "roles": ["finance", "owner"],
                        "mode": "any",
                    },
                },
            )
            nodes.insert(
                3,
                {
                    "id": "apply",
                    "position": {"x": 680, "y": 100},
                    "data": {"kind": "action", "label": "登记业务", "action": binding},
                },
            )
            nodes[-1]["position"]["x"] = 900
            edges.extend(
                [
                    {"id": "b", "source": "review", "target": "actual"},
                    {"id": "c", "source": "actual", "target": "apply"},
                    {"id": "d", "source": "apply", "target": "end"},
                ]
            )
        else:
            edges.append({"id": "b", "source": "review", "target": "end"})
        result.append(
            {
                "name": name,
                "kind": "workflow",
                "binding": binding,
                "spec": {"nodes": nodes, "edges": edges},
            }
        )
    return result


def visible_fields(i, fields):
    out = []
    for f in fields:
        if not field_access(f, i):
            continue
        item = {**f, "editable": field_access(f, i, True)}
        if f.get("type") == "table":
            item["fields"] = visible_fields(i, f.get("fields", []))
        out.append(item)
    return out


def instance_public(i, inst, detail=False):
    if not can_view_instance(i, inst):
        fail("NOT_FOUND", "流程不可访问", 404)
    out = {k: v for k, v in inst.model_dump().items() if k != "payload_cipher"}
    if detail:
        d = own(i.session, StudioDefinition, i.tenant.id, inst.definition_id)
        spec = json.loads(
            canonical(
                definition_version(
                    i.session, i.tenant.id, d, inst.definition_version
                ).spec
            )
        )
        for n in spec.get("nodes", []):
            if n["data"].get("fields"):
                n["data"]["fields"] = visible_fields(i, n["data"]["fields"])
        payload = unseal(i.tenant.id, inst.payload_cipher)
        source = payload.get("_form_submission_id")
        form_fields = [
            f for n in spec.get("nodes", []) for f in n["data"].get("fields", [])
        ]
        if form_fields and "values" in payload:
            payload["values"] = values_for(
                i, list({f["key"]: f for f in form_fields}.values()), payload["values"]
            )
        if source:
            f = own(i.session, FormSubmission, i.tenant.id, source)
            fd = own(i.session, StudioDefinition, i.tenant.id, f.definition_id)
            fv = definition_version(i.session, i.tenant.id, fd, f.definition_version)
            payload = {
                "values": values_for(
                    i, fv.spec.get("fields", []), unseal(i.tenant.id, f.values_cipher)
                )
            }
        out.update(payload=payload, definition_spec=spec)
    return out


def custom_record_values(i, rid):
    result = []
    for row in i.session.exec(
        query(i.session, FormSubmission, i.tenant.id).where(
            FormSubmission.record_id == rid
        )
    ).all():
        if row.status not in ("submitted", "approved", "completed"):
            continue
        d = own(i.session, StudioDefinition, i.tenant.id, row.definition_id)
        v = definition_version(i.session, i.tenant.id, d, row.definition_version)
        values = values_for(
            i, v.spec.get("fields", []), unseal(i.tenant.id, row.values_cipher)
        )
        if values:
            result.append(
                {"id": row.id, "name": d.name, "version": v.version, "values": values}
            )
    return result


def form_asset_access(i, asset_id):
    """None means unreferenced; referenced documents follow field and record scopes."""
    referenced = False

    def includes(fields, values, readable=True):
        found, allowed = False, False
        for field in fields:
            value = values.get(field["key"])
            permitted = (
                readable
                and field_access(field, i)
                and condition(field.get("visible_when", {}), values)
            )
            if (
                field["type"] == "attachment"
                and isinstance(value, list)
                and asset_id in value
            ):
                found = True
                allowed |= permitted
            elif field["type"] == "table" and isinstance(value, list):
                for row in value:
                    f, a = includes(field.get("fields", []), row, permitted)
                    found |= f
                    allowed |= a
        return found, allowed

    for submission in i.session.exec(
        query(i.session, FormSubmission, i.tenant.id)
    ).all():
        d = own(i.session, StudioDefinition, i.tenant.id, submission.definition_id)
        v = definition_version(i.session, i.tenant.id, d, submission.definition_version)
        found, readable = includes(
            v.spec.get("fields", []), unseal(i.tenant.id, submission.values_cipher)
        )
        if not found:
            continue
        referenced = True
        if not readable:
            continue
        try:
            check_binding(i, submission.binding, submission.record_id)
        except Exception:
            continue
        if submission.binding != "independent" and submission.record_id:
            return True
        if submission.actor_id == i.user.id:
            return True
        for inst in i.session.exec(query(i.session, FlowInstance, i.tenant.id)).all():
            if unseal(i.tenant.id, inst.payload_cipher).get(
                "_form_submission_id"
            ) == submission.id and can_view_instance(i, inst):
                return True
    return False if referenced else None
