# 0.3 交付与运行说明

## 功能边界

本版实现招生扫描与核对、直接报名、班级档案、多家长资料、课返完成 KPI、退款课时快照、经营周月报、异常管理、通知发件箱、可视化表单/流程和数字人申请。

课程包、课返正文和咨询记录保留为历史资料。新业务不用课程包；不再生成或发送课返正文。咨询、微信/网页 AI 客服、互动自动回复默认暂停。管理群经营通知继续独立运行，自媒体内容计划与发布不受暂停影响。

数字人申请允许“待处理、已报价、已批准待接入、暂不受理”四种平台处理状态。真实开播、收费及供应商调用没有启用。

## 指标与版本

- 使用中国时区 Asia/Shanghai，周一为统计周起点。
- 新增线索转化与首次试听到场转化分别使用同一批线索，报名后回补原批次累计转化。
- 正式在读为应收缴清后确认报名；定金不计转化。重复签到不重复扣课，同一个学员同一课次即使多笔报名也只计一个应到/实到人次。
- 月流失率：本月结束最后一条在读关系的去重学员 ÷ 月初在读与本月新增在读的去重学员。继续就读的部分退款不计流失。
- 月出勤率：有效已结束课次的实到 ÷ 应到，请假仍算未出勤，取消课程剔除。名册和原任课老师在课次发生时固定。
- 课返只记录每班每课次完成情况，默认结束后24小时内完成；期限修改影响以后生成的考核。历史未知考核不补造。
- 零分母显示无数据；历史期初未核对时在读基数、流失率等显示待校准。负责人核对名单和实际生效日期后确认。
- 当前报表实时计算。已保存报表内容、表单发布版、流程发布版和原业务事件不可覆盖；补录、冲正或规则变化形成新的报表版本。

## 表单、审批与附件

自定义值不平铺进业务记录：采用机构密钥加密，并绑定定义版本、业务记录和发起人。列表、详情、搜索、导出、流程详情与附件下载均重新执行机构、岗位、归属和字段权限。

表单字段支持分组、排序、预览、必填、范围、选项、条件、读写岗位、附件、业务关联和明细子表。招生 Excel 可包含自定义列；打印 PDF 最多22列。复杂字段或无法匹配的关联值需要网页核对，不自动猜测。

流程采用 React Flow 画布；后端执行有向无环图，支持填写、审批、条件、并行、汇合、通知及注册业务动作。回环不允许，退回通过新提交修订办理。发布时检查节点和分支，填写节点固定所关联表单的发布版本。审批人停用后转负责人待分配，不自动通过。

直接财务登记默认保留。只有启用对应业务审批后，原接口才检查批准实例、同一份业务数据和记录版本；财务还须确认实际发生。并发操作锁定流程实例和业务记录，重试使用稳定请求编号，不重复登记。

## 招生导入

接口只接受 XLSX、PNG/JPG、PDF，限制25MB、20页、500行。XLSX 不执行公式，压缩展开大小有限制。扫描在受限环境的专用 OCR 进程执行，不向模型下载进程传入数据库、模型 Key 或企微密钥。

纸表带版本和稳定行号。优先匹配行号；电话相同只给候选，不自动合并不同孩子。确认时检查原记录版本，已确认行不会重复导入。识别失败和中断可重新执行，导入确认与事件一起提交。收款/报名/退费标记只进入核对信息，不自动生成台账。

实时接口只发送刷新提示，不发送其他员工的业务内容或联系方式；客户端重新读取授权范围的数据。正常连接下5秒内刷新，断线重连会补取；权限撤销时缓存清空并重新获取会话权限。

## 经营通知

默认每周一09:00发送上周周报，每月1日09:00发送上月月报。默认流失率达到或超过30%报警，负责人可配置指标、阈值和班级。

Webhook 仅允许官方 `https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=...`，机构密钥加密保存，仅替换和撤销，不回显。消息不含家长电话或儿童明细。发件箱先持久化发送意图；平台限流退避，超时/服务中断标记未知，须核实未发送后再重试。配置更换或撤销后取消旧配置版本的待发送通知。

本机只有模拟通知协议测试，**没有发送过真实企微群通知**。上线须负责人在机构页面填写真实 Webhook，测试消息并保存发送记录。

## 本地 OCR

主服务可以使用当前 `.venv`。Paddle 独立使用 Python 3.12，避免主环境 Python 3.14 的原生库兼容问题：

```powershell
# 使用已安装的 Python 3.12 创建专用环境
py -3.12 -m venv .local/ocr-venv
.venv/Scripts/uv.exe pip install --python .local/ocr-venv/Scripts/python.exe --constraint backend/requirements-ocr.lock paddlepaddle==3.3.1 paddleocr==3.7.0 pypdfium2==5.14.0
```

在本地 `.env` 配置 `OPS_OCR_PYTHON` 为该解释器绝对路径，`OPS_OCR_ENABLED=true`。不要把 Windows 路径带入 Linux 生产配置。CPU 识别关闭 MKL-DNN，模型缓存写入数据目录；首次启动下载官方模型需要网络，部署时可预热缓存。

```powershell
.venv/Scripts/python.exe scripts/test-operations-ocr.py --ocr-python .local/ocr-venv/Scripts/python.exe
```

真实验证覆盖合成打印体中文 PNG 和 PDF，结果见 `operations-real-ocr.json`；手写、复杂票据、实拍歪斜多页资料仍需单独验收。财务 OCR 后的 AI 字段提取另需可用文字模型与额度。

## 迁移、备份与生产

新增迁移 `0003_operations`，14张机构表，机构 RLS 表共39张。原订单复制课程名称、金额和课时快照；账务/课时流水不改写。缺少可靠日期的历史在读保留待校准标记。

1. 停止自动任务和写入，保存数据库、私有对象及原加密主密钥。
2. 在独立恢复库演练恢复，再使用迁移角色执行 `alembic -c backend/alembic.ini upgrade head`。
3. 原生 PostgreSQL 运行角色必须非库表所有者、NOSUPERUSER、NOBYPASSRLS；验证全部39张机构表启用 FORCE RLS。
4. 构建 `care-ops:0.3.0-rc1`；需要 OCR 时构建 `deploy/Dockerfile.ocr`，以 `docker compose --profile ocr up -d` 启动对应队列。
5. 检查 `/api/v1/health`、`scripts/doctor.py`、SSE、备份和定时任务，完成机构岗位验收后恢复写入。
6. 回滚使用与旧镜像匹配的备份，在维护窗口恢复；不对已有财务/审批历史执行破坏式 downgrade。

本机 SQLite 迁移和恢复用于开发验收，PostgreSQL WASM 用于 SQL/RLS 检查。它们不能替代原生 PostgreSQL、Docker、阿里云网络/OSS/邮件、真实模型、发布账号和企微群联调。

## 新接口

| 组 | 主要接口（均 `/api/v1` 前缀） |
|---|---|
| 学员与教务 | `/classes/students`、`/students/{id}/profile`、`/education/feedback-kpis`、`/enrollments/{id}/transfer` |
| 招生导入 | `/admissions/template/{xlsx,pdf}`、`/admissions/imports`、`/admissions/imports/{id}/confirm`、`/operations/events` |
| 财务 | `/finance/overview`、`/finance/details/{kind}/{id}`、`/finance/receipt-links`、`/orders/{id}/refund-context` |
| 报表与通知 | `/reports/{weekly,monthly}`、`/report-snapshots`、`/operations/settings`、`/operations/alerts`、`/notifications` |
| 定制 | `/studio/definitions`、`/studio/forms/{id}/submissions`、`/studio/workflows/{id}/instances`、`/studio/tasks` |
| 增值 | `/addons/digital-human`、`/addons/digital-human/requests`、`/platform/addon-requests` |

完整字段和错误码以生成的 `openapi.json` 与 `/api/docs` 为准。
