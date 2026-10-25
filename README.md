> 同事 GPT / Codex 接手：先读 [项目上下文](docs/GPT_HANDOFF.txt) 和 [AGENTS.md](AGENTS.md)。上传与仓库访问说明见 [GitHub 协作](GITHUB_UPLOAD.txt)。

> 完整使用说明（2026-10-23）：[网页版手册](docs/USER_MANUAL.html) · [PDF手册](output/pdf/知营使用说明书与自媒体账号接入指南.pdf)。自媒体账号如何扫码接入、当前演示限制和三平台能力见手册第8至13页。

> 当前更新包 **0.4.0-rc2**：包含 DeepSeek 后台文字智能体、负责人配置、用量与预算记录及报表 AI 解读。旧版 `0.4.0-rc1` 用户先读 [升级说明](UPGRADE_0.4.0-rc2.txt)，本包验收状态见 `docs/release-0.4.0-rc2.json`。真实模型与平台账号联调单独验收。

# 知营 · AI辅助教育机构经营工作台

当前版本：**0.4.0-rc2，DeepSeek 智能体、自媒体矩阵、多岗授权与经营报表**。本地预览：[http://127.0.0.1:8188/](http://127.0.0.1:8188/)。

业务链：招生表录入 → 跟进试听 → 报名收款 → 分班签到 → 课返完成 KPI → 周报月报 → 异常提醒 → 财务核对。

本版取消新业务对课程包的依赖，课返只记录完成情况。咨询接待、网页/微信 AI 客服和互动自动回复默认暂停；历史数据保留。自媒体内容生产和周期发布独立保留。数字人直播入口当前隐藏，真实开播待供应商接入。

“一人公司”表示一人可兼任多个岗位，并支持多人协作。机构负责人在“成员与授权”统一授予招生、授课、排班、教务、营收查看、财务及内容运营；每项业务继续按机构和负责范围校验。

新增入口：成员与授权、营收总览、教务中的学员家长反馈、周报/月报的自动生成与历史版本。仅有营收查看权限时，不开放订单、费用、票据和学员资料。说明见 [0.3.1 使用与验收](docs/MANAGEMENT_031.md)。

## 本地使用

PowerShell 在本目录执行：

```powershell
.\scripts\dev.ps1
```

在登录页展开“开发演示”选择岗位。员工演示密码为 `Demo-Staff-2026!`，仅开发环境可用：

| 账号 | 用途 |
|---|---|
| owner.qinghe@zhiying.example | 负责人：机构设置、经营报表、表单流程和成员管理 |
| teacher1.qinghe@zhiying.example | 教师：本人任教班级、学员和课返 KPI |
| admissions1.qinghe@zhiying.example | 招生：本人线索、扫描表和订单 |
| scheduler.qinghe@zhiying.example | 排班：查看班级与维护排课，不读取学员档案和财务 |
| revenue.qinghe@zhiying.example | 营收查看：仅机构实收、退款、净收汇总及趋势 |
| finance.qinghe@zhiying.example | 财务：收退费、图表、票据和结算 |
| combined.qinghe@zhiying.example | 教师兼财务：分别校验各项操作的范围 |

`demo@zhiying.example / Demo-Zhiying-2026!` 是两个机构的负责人兼平台管理员，适合验收跨机构切换，不代表普通员工入口。

初次安装：Python 3.12+、Node.js 24；创建 `.venv`，安装 `backend/requirements.lock`，再执行 `pip install --no-deps -e ./backend`、`npm ci --prefix frontend`、`npm run build --prefix frontend`、`python scripts/configure.py`。配置工具不会覆盖已有密钥。

OCR 使用独立的 Python 3.12 运行环境或 Docker OCR Worker。本机已配置专用 CPU 环境；源码包不包含 Python 环境、模型缓存、账号或凭证。重新部署请参考 [0.3 使用与交付说明](docs/OPERATIONS_03.md)。

## 主要页面

- 招生：Excel / PDF 模板，Excel、PNG/JPG、多页 PDF 导入，原件核对、逐行处理、稳定编号匹配和实时刷新；扫描信息不直接记账。
- 学员与教务：按班级浏览，多家长联系方式，直接报名金额与总课时，签到、请假补课、调班历史及每课次课返 KPI。
- 财务：实收、退款、净收、费用和收支差额图表；点击查看流水、票据原件、OCR 草稿、退款课时快照与操作记录。
- 经营：周报、月报、同批线索转化率、月度流失与出勤、不可覆盖报表版本、默认 30% 流失报警和负责人管理群通知。
- 定制：拖拽表单字段、条件和岗位权限；React Flow 流程画布、分支、并行审批、退回修改、财务实际发生确认及版本固定。
- 自媒体：AI 图文与视频生产、内容计划、发布网关和成品复盘；真实发送默认关闭。

默认允许财务直接登记。只有负责人发布并启用对应业务流程后，业务接口才要求完成审批。独立表单可关联已发布的独立审批流程。

## 验证与交付边界

自动化结果见 [本轮验收报告](docs/management-acceptance.json) 及 [0.3.1 使用说明](docs/MANAGEMENT_031.md)。真实 CPU OCR 已验证合成打印体中文 PNG 和 PDF，手写资料仍待验收。Docker 镜像、原生 PostgreSQL、真实企微群推送、真实模型和三平台账号联调须在部署环境分别验证；本地通过不等于正式生产交付。

```powershell
.venv\Scripts\python.exe -m pytest backend\tests -q --junitxml=docs/management-full-api-tests.xml
.\scripts\test-browser.ps1
node frontend\test-management-migration.mjs
node frontend\test-rls.mjs
.venv\Scripts\python.exe -m app.cli openapi
npm run generate-client --prefix frontend
.venv\Scripts\python.exe scripts\release-management.py
.venv\Scripts\python.exe scripts\package.py
```

## 文档

[机构手册](docs/USER_GUIDE.md) · [0.3 规则与接口](docs/OPERATIONS_03.md) · [部署](docs/DEPLOYMENT.md) · [备份恢复与升级](docs/OPERATIONS.md) · [岗位与 MCP](docs/STAFF_MCP.md) · [开源许可](docs/THIRD_PARTY_NOTICES.md) · [OpenAPI](docs/openapi.json)。运行后访问 `/api/docs` 查看离线接口文档。


## 下周企业演示

在项目根目录双击 `启动企业演示.cmd`，打开独立的虚构机构环境；`重置企业演示.cmd` 可恢复基线。
外部体验用 `开启临时外网演示.cmd`，默认8小时到期且需要访问码。原开发数据库不进入演示。
现场讲解、岗位切换、离线录像和交付边界见 [企业演示使用说明](docs/ENTERPRISE_DEMO.md)。


## DeepSeek 后台文字智能体（2026-10-24）

当前工作区已增加 DeepSeek 官方 API 适配，沿用现有机构权限、任务与额度管理。它负责选题、文案、分镜规划、复盘、OCR 后的字段整理和经营报表解读；图片、视频、配音、向量检索、视觉盲评和独立复核仍使用百炼的独立模型。网页/微信客服及互动自动回复继续保持原暂停策略。

### 机构自带 Key 的接入步骤

1. 在 DeepSeek 开放平台申请 API Key，并确保账户可调用模型。
2. 用机构负责人账号进入“机构与连接 → 服务连接 → DeepSeek 官方 API”，在密码框保存 Key。密钥按机构加密，不会回显。
3. 在同页“AI 模型配置”选择“DeepSeek 官方 API”，选择 `deepseek-flash` 或 `deepseek-v4-pro`，费用来源选“机构自带 Key”。默认关闭思考模式，输出上限 3000 Token；可由负责人调整。
4. 核对输入、输出和缓存输入的预算估算单价，点击“保存 AI 配置”，再点击“测试连接”。测试会真实调用少量 Token；结果在页面和用量记录中显示。
5. 在内容工作室或矩阵计划中创建任务。矩阵计划继续使用其明确选择的费用来源；BYOK 计划的视觉评分、图片、视频和配音还需要本机构的百炼 Key。不会自动改用平台凭证。

单价单位为分/百万 Token，BYOK 初值是估算参数，不会自动查询供应商峰谷时价；以供应商账单为准。模型调用前按保守上限预占预算，返回后按输入、缓存和输出 Token 及锁定单价结算。配置变更只影响新预占的任务，历史及排队任务不会静默换供应商。旧版本的空路由记录继续视为百炼记录。

### 平台提供 DeepSeek 额度

服务器部署配置中设置 `OPS_DEEPSEEK_API_KEY`；`OPS_DEEPSEEK_MODEL` 默认 `deepseek-flash`，`OPS_TEXT_PROVIDER` 默认 `aliyun`，可改为 `deepseek` 作为没有机构覆盖配置时的默认值。Compose 已把这三项传给 API 和 Worker。不要把 Key 写进前端、代码或共享源码包。

平台管理员还需在“平台管理”配置对应模型的输入、输出、缓存单价，并为机构分配 `text_tokens`、`cost_fen` 额度。负责人在“AI 模型配置”主动选择平台额度；额度不足不会动用机构 Key。平台与机构计价、费用来源分别记录。

### 报表与执行边界

负责人在“经营规则与提醒 → 报表版本”打开周报/月报，点击“生成 AI 解读”。只发送该快照的汇总数字，原始反馈、家长电话、学员姓名、订单和票据明细不进入模型请求。解读保存在独立任务，原快照及账务不变。本次新增的是按需解读；周期报表与提醒保持原有确定性统计和调度，并未默认增加周期性的模型扣费。

DeepSeek 接入现有固定工作流；模型返回结构化结果，后端执行权限、事实和预算检查。发布仍由原发布网关执行。视觉盲评和独立模型复核不随文字供应商一起切换。

官方地址固定为 `https://api.deepseek.com`。不接收机构自定义代理地址；本次使用 Chat Completions JSON 输出并做 Pydantic 校验，不依赖 Beta 工具严格模式。思考模式显式开关。401/403、余额不足、参数拒绝和429有明确状态；SDK 关闭自动重试，超时和服务结果未知时保留预占并停止重发。无效输出也会保留实际用量。

API：`GET/PUT /api/v1/ai-settings`、`POST /api/v1/ai-settings/test`、`PUT/DELETE /api/v1/integrations/deepseek`、`GET /api/v1/runs/{id}`；已有 `/runs` 增加 `report_summary` 类型。配置与连接测试仅负责人可用。

升级前备份。SQLite 开发环境启动时补充 `usage_records.model_usage` 列；生产 PostgreSQL 使用 Alembic `upgrade head` 升至 `0006_deepseek`。迁移只增加用量元数据列，旧金额不重算；回退使用已验证备份及对应源码。数据库迁移、OpenAPI 和前端类型已随源码更新。

验证证据见 `docs/deepseek-acceptance.json`。模拟 API 测试不等于真实账号联调；真实 DeepSeek、百炼媒体生成及生产原生 PostgreSQL 仍须独立验收。

官方参考：[DeepSeek API](https://api-docs.deepseek.com/zh-cn/)、[JSON 输出](https://api-docs.deepseek.com/zh-cn/guides/json_mode/)、[思考模式](https://api-docs.deepseek.com/zh-cn/guides/thinking_mode/)。
