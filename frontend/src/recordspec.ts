export type SpecField = {
  key: string;
  label: string;
  type?: string;
  required?: boolean;
  ref?: string;
  options?: string[];
  default?: any;
};
export const f = (
  key: string,
  label: string,
  type = "text",
  extra: Partial<SpecField> = {},
): SpecField => ({ key, label, type, ...extra });
const name = f("name", "名称", "text", { required: true });
const student = f("student_id", "学员", "ref", {
  ref: "student",
  required: true,
});
const course = f("course_id", "课程", "ref", { ref: "course", required: true });
const cls = f("class_id", "班级", "ref", { ref: "class" });
export const specs: Record<
  string,
  {
    title: string;
    fields: SpecField[];
    columns: string[];
    write: string[];
    text: string;
  }
> = {
  lead: {
    title: "招生线索",
    text: "扫描招生表后，跟进、试听与正式报名状态在这里同步。",
    write: ["owner", "operator"],
    columns: [
      "student_name",
      "name",
      "grade",
      "source",
      "stage",
      "contact",
      "loss_reason",
      "followup_at",
    ],
    fields: [
      f("student_name", "学员称呼"),
      f("name", "家长称呼", "text", { required: true }),
      f("relationship", "家长关系", "text", { default: "家长" }),
      f("contact", "家长手机号", "text", { required: true }),
      f("grade", "年级"),
      f("source", "来源渠道", "text", { default: "直接咨询" }),
      f("class_id", "意向班级", "ref", { ref: "class" }),
      f("stage", "跟进阶段", "select", {
        options: ["new", "contacted", "booked", "attended", "won", "lost"],
        default: "new",
      }),
      f("loss_reason", "未成交原因", "textarea"),
      f("owner_id", "招生负责人", "ref", { ref: "member" }),
      f("followup_at", "下次跟进", "datetime"),
      f("trial_at", "试听时间", "datetime"),
      f("contact_time", "方便联系时间"),
      f("need", "需求", "textarea"),
      f("notes", "跟进记录", "textarea"),
    ],
  },
  course: {
    title: "课程包",
    text: "统一课程内容、价格和课时，供招生与教务使用。",
    write: ["owner", "operator"],
    columns: ["name", "price_fen", "lessons", "approved"],
    fields: [
      name,
      f("price_fen", "课程价格（元）", "money", {
        default: 1980,
        required: true,
      }),
      f("lessons", "课时数", "number", { default: 8, required: true }),
      f("description", "课程说明", "textarea"),
      f("approved", "确认可对外介绍", "check"),
    ],
  },
  student: {
    title: "学员档案",
    text: "按班级管理学员及家长联系资料。",
    write: ["owner", "operator"],
    columns: ["name", "grade", "guardian", "contact", "notes"],
    fields: [
      f("name", "学员称呼", "text", { required: true }),
      f("grade", "年级"),
      f("guardians", "家长与手机号", "guardians"),
      f("notes", "备注", "textarea"),
    ],
  },
  class: {
    title: "班级管理",
    text: "维护班级、教学项目、任课老师与人数。",
    write: ["owner", "operator"],
    columns: ["name", "program_name", "teacher_id", "capacity"],
    fields: [
      name,
      f("program_name", "教学项目名称"),
      f("teacher_id", "任课老师", "ref", { ref: "member" }),
      f("capacity", "人数上限", "number", { default: 15, required: true }),
      f("notes", "上课安排", "textarea"),
    ],
  },
  lesson: {
    title: "排课日历",
    text: "安排每一节课，取消课程时自动返还已扣课时。",
    write: ["owner", "operator", "teacher"],
    columns: ["name", "class_id", "starts_at", "duration_minutes", "status"],
    fields: [
      name,
      { ...cls, required: true },
      f("starts_at", "上课时间", "datetime", { required: true }),
      f("duration_minutes", "时长（分钟）", "number", {
        default: 90,
        required: true,
      }),
      f("status", "课程状态", "select", {
        options: ["scheduled", "completed", "cancelled"],
        default: "scheduled",
      }),
    ],
  },
  enrollment: {
    title: "报名与课时",
    text: "缴清学费后确认报名，建立在读关系和课时账户。",
    write: ["owner", "operator"],
    columns: ["student_id", "program_name", "class_id", "remaining", "status"],
    fields: [
      f("order_id", "已收款订单", "ref", { ref: "order", required: true }),
      student,
      cls,
    ],
  },
  order: {
    title: "报名订单",
    text: "直接填写报名金额与课时，不需要课程包。",
    write: ["owner", "operator", "finance"],
    columns: [
      "name",
      "student_id",
      "program_name",
      "purchased_units",
      "due_fen",
      "paid_fen",
    ],
    fields: [
      name,
      student,
      f("program_name", "报名项目名称", "text", { required: true }),
      f("price_fen", "学费金额（元）", "money", {
        default: 1980,
        required: true,
      }),
      f("discount_fen", "优惠金额（元）", "money", { default: 0 }),
      f("purchased_units", "购买课时", "number", {
        default: 8,
        required: true,
      }),
      cls,
      f("lead_id", "关联招生线索", "ref", { ref: "lead" }),
      f("owner_id", "招生负责人", "ref", { ref: "member" }),
      f("channel_id", "合作渠道", "ref", { ref: "channel" }),
      f("notes", "备注", "textarea"),
    ],
  },
  expense: {
    title: "费用台账",
    text: "录入运营费用，票据识别结果需要核对后确认。",
    write: ["owner", "finance"],
    columns: ["name", "category", "amount_fen", "date", "status"],
    fields: [
      name,
      cls,
      f("channel_id", "来源渠道", "ref", { ref: "channel" }),
      f("amount_fen", "金额（元）", "money", { required: true }),
      f("category", "费用分类", "select", {
        options: [
          "运营费用",
          "活动物料",
          "场地费用",
          "模型费用",
          "师资费用",
          "其他",
        ],
        default: "运营费用",
      }),
      f("date", "发生日期", "date"),
      f("status", "入账状态", "select", {
        options: ["draft", "confirmed"],
        default: "draft",
      }),
      f("asset_id", "票据素材编号"),
      f("notes", "说明", "textarea"),
    ],
  },
  channel: {
    title: "渠道与分润",
    text: "确认合作比例后生效，订单保留当时的结算规则。",
    write: ["owner", "finance"],
    columns: ["name", "commission_bps", "confirmed", "notes"],
    fields: [
      name,
      f("commission_bps", "分润比例（%）", "percent", { default: 0 }),
      f("basis", "结算基数", "select", {
        options: ["net_cash", "after_fixed_cost"],
        default: "net_cash",
      }),
      f("deduction_fen", "每单扣除固定成本（元）", "money", { default: 0 }),
      f("effective_from", "生效时间（空为立即）", "datetime"),
      f("confirmed", "已确认合作结算规则", "check"),
      f("notes", "合作约定", "textarea"),
    ],
  },
  knowledge: {
    title: "机构知识库",
    text: "把课程、试听和服务规则整理清楚，让客服与内容共用。",
    write: ["owner", "operator"],
    columns: ["name", "body", "approved"],
    fields: [
      name,
      f("body", "资料内容", "textarea", { required: true }),
      f("source_url", "参考来源链接"),
      f("approved", "审核通过并发布到知识库", "check"),
    ],
  },
  topic: {
    title: "选题池",
    text: "收集真实家长问题，为下一次内容生产做准备。",
    write: ["owner", "operator"],
    columns: ["name", "form", "status", "source"],
    fields: [
      name,
      f("body", "内容切入点", "textarea"),
      f("source", "来源", "text", { default: "manual" }),
      f("form", "内容形式", "select", {
        options: ["image_text", "video"],
        default: "image_text",
      }),
      f("status", "选题状态", "select", {
        options: ["candidate", "selected", "done", "rejected"],
        default: "candidate",
      }),
    ],
  },
  campaign: {
    title: "自动内容计划",
    text: "配置一次主题、平台和频次，系统持续生成、发布与复盘。",
    write: ["owner", "operator"],
    columns: ["name", "platforms", "form", "enabled", "next_run_at"],
    fields: [
      name,
      f("objective", "持续创作主题与目标", "textarea", { required: true }),
      f("platforms", "发布平台", "platforms"),
      f("form", "成品形式", "select", {
        options: ["image_text", "video"],
        default: "video",
      }),
      f("funding", "模型费用来源", "select", {
        options: ["platform", "byok"],
        default: "platform",
      }),
      f("interval_days", "发布间隔（天）", "number", { default: 3 }),
      f("hour", "发布时间（24小时制）", "number", { default: 18 }),
      f("enabled", "启用本计划", "check"),
      f("next_run_at", "首次执行时间", "datetime"),
    ],
  },
  feedback: {
    title: "课堂反馈",
    text: "先记录课堂观察，再生成和审核给家长的反馈。",
    write: ["owner", "operator", "teacher"],
    columns: ["name", "student_id", "status", "teacher_note"],
    fields: [
      name,
      student,
      f("lesson_id", "对应课程", "ref", { ref: "lesson" }),
      f("teacher_note", "课堂观察记录", "textarea", { required: true }),
      f("body", "给家长的反馈", "textarea"),
      f("status", "反馈状态", "select", {
        options: ["draft", "approved", "sent"],
        default: "draft",
      }),
    ],
  },
  community: {
    title: "社群运营",
    text: "维护活动节奏、分组文案和员工发送任务。",
    write: ["owner", "operator"],
    columns: ["name", "audience", "status", "due_at"],
    fields: [
      name,
      f("audience", "目标家长分组"),
      f("body", "群内文案", "textarea"),
      f("due_at", "计划时间", "datetime"),
      f("status", "任务状态", "select", {
        options: ["draft", "approved", "sent"],
        default: "draft",
      }),
      f("channel", "发送渠道", "text", { default: "manual" }),
    ],
  },
};
export const labels: Record<string, string> = {
  name: "名称",
  grade: "年级",
  source: "来源",
  stage: "阶段",
  contact: "家长手机号",
  followup_at: "下次跟进",
  price_fen: "价格",
  lessons: "课时",
  approved: "发布状态",
  guardian: "家长",
  notes: "备注",
  course_id: "课程",
  teacher_id: "任课老师",
  capacity: "容量",
  class_id: "班级",
  starts_at: "上课时间",
  duration_minutes: "时长",
  status: "状态",
  student_id: "学员",
  remaining: "剩余课时",
  due_fen: "应收金额",
  paid_fen: "净收款",
  channel_id: "合作渠道",
  category: "分类",
  amount_fen: "金额",
  date: "日期",
  commission_bps: "分润比例",
  confirmed: "规则确认",
  body: "内容摘要",
  form: "形式",
  platforms: "平台",
  enabled: "计划开关",
  next_run_at: "下次执行",
  teacher_note: "课堂记录",
  audience: "家长分组",
  due_at: "计划时间",
};
export const optionLabels: Record<string, string> = {
  image_text: "图文卡片",
  video: "AI 短视频",
  platform: "平台额度",
  byok: "机构自带 Key",
  manual: "员工发送",
};

specs.leave = {
  title: "请假与补课",
  text: "批准请假后原课不扣课时，补课在对应课程签到后完成。",
  write: ["owner", "operator", "teacher"],
  columns: ["name", "enrollment_id", "lesson_id", "status", "makeup_lesson_id"],
  fields: [
    name,
    f("enrollment_id", "报名记录", "ref", {
      ref: "enrollment",
      required: true,
    }),
    f("lesson_id", "请假课程", "ref", { ref: "lesson", required: true }),
    f("reason", "请假原因", "textarea"),
    f("status", "处理状态", "select", {
      options: ["requested", "approved", "rejected", "made_up"],
      default: "requested",
    }),
    f("makeup_lesson_id", "补课场次", "ref", { ref: "lesson" }),
  ],
};
labels.enrollment_id = "报名记录";
labels.makeup_lesson_id = "补课场次";
optionLabels.requested = "待审批";
optionLabels.made_up = "补课完成";

optionLabels.net_cash = "实际净现金";
optionLabels.after_fixed_cost = "净现金扣除固定成本";

specs.community.fields.push(f("outcome", "效果与转化记录", "textarea"));
specs.community.columns.push("outcome");
labels.outcome = "效果记录";

labels["payment_status"] = "付款状态";

Object.assign(labels, {
  student_name: "学员",
  program_name: "报名项目",
  purchased_units: "购买课时",
  loss_reason: "未成交原因",
  guardians: "家长信息",
});
