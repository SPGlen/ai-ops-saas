# 部署与管理员手册

当前应用更新为 `0.4.0-rc2`，迁移目标 `0006_deepseek`，机构隔离表48张。从 `0.4.0-rc1` 更新前先阅读根目录 `UPGRADE_0.4.0-rc2.txt`。应用/OCR镜像标签随版本更新；独立发布节点代码未变，继续使用 `0.4.0-rc1` 发布镜像。下方旧版本章节保留为历史说明。

## 环境与分离

应用栈：React/TypeScript、FastAPI、PostgreSQL 17 + pgvector、Celery、Valkey、私有 S3 和 SMTP。对象存储使用现有云服务，主 Compose 不把数据库、队列或对象存储公开到互联网。

发布浏览器部署到独立的 Linux 主机及 rootless Docker daemon。应用、财务数据库及模型密钥不进入浏览器容器。不要把浏览器节点的 Docker socket 挂载到业务后端。

建议应用起步配置为 4 vCPU / 8 GB；启用 CPU OCR 时为专用 Worker 预留额外内存，默认单并发、6 GB上限。每机构浏览器容器上限为1.5 GB，按活跃机构数量规划独立主机容量。这些是起步资源参数，未完成云端压测。

## 准备配置

在工程根目录运行：

    python scripts/configure-production.py

编辑生成的 .env.production，填写域名、HTTPS公开地址、SMTP、私有S3桶及访问权限。密钥不要发到聊天、提交到Git或放进前端。生成器不打印密钥，也不覆盖已有文件。

所需字段：

| 配置 | 用途 |
|---|---|
| OPS_DOMAIN、OPS_PUBLIC_URL | DNS域名及https://完整地址 |
| OPS_DB_ROOT_PASSWORD、OPS_MIGRATION_PASSWORD、OPS_DB_PASSWORD | 引导、迁移和运行角色分别使用不同凭证 |
| OPS_SECRET_KEY | 会话/机构凭证加密主密钥，必须稳定保存 |
| OPS_VALKEY_PASSWORD | 私有任务队列 |
| OPS_SMTP_HOST/PORT/USER/PASSWORD/FROM | 邮箱验证与重置；默认587 STARTTLS |
| OPS_S3_BUCKET/ENDPOINT/REGION/ACCESS_KEY/SECRET_KEY | 私有对象存储；桶关闭匿名访问，开启版本控制及静态加密 |
| OPS_ALIYUN_API_KEY | 平台赠送额度使用的模型凭证；可留空，机构选择自带Key |
| OPS_ALIYUN_BASE_URL | 图像/万相/配音API地域，如北京DashScope地址 |
| OPS_ALIYUN_TEXT_BASE_URL | 文字/视觉模型业务空间兼容地址；按实际百炼空间和地域填写 |
| OPS_PUBLISHER_URL/TOKEN | 私有发布网关与共享认证密钥 |
| OPS_ALLOW_LIVE_PUBLISH | 默认为false，真实账号验收前保持关闭 |

Compose中默认模型为 qwen-plus、qwen3-vl-plus、qwen-max、qwen-image-plus、wan2.7-t2v-2026-06-12、qwen3-tts-flash。确认账号对所选模型和地域有权限，不可混用不同地域Key。文字/视觉模型参考[百炼兼容接口](https://help.aliyun.com/zh/model-studio/qwen-api-via-openai-chat-completions)，视频参考[万相接口](https://help.aliyun.com/zh/model-studio/text-to-video-api-reference)。

应用网络默认10.215.88.0/24，网关固定10.215.88.10。若与现有云网段冲突，同时修改 OPS_APPLICATION_SUBNET、OPS_EDGE_IP。Uvicorn只接受该固定网关的代理头；后端8000端口不映射到宿主机。

## 构建与启动

    docker compose --env-file .env.production build backend
    docker compose --env-file .env.production up -d

首次引导创建 vector 扩展与两个数据库角色。迁移服务用 ops_migrator 建表、RLS策略和不可变触发器，完成后应用启动。运行角色 ops_app 不能拥有业务表、不能是超级用户或绕过RLS；生产启动会检查22张机构表的策略是否齐全。

底层镜像的已解析摘要见 deploy/image-lock.json，核心 Python 生产锁文件为 backend/requirements-resolved.lock，包含哈希。实际自有应用和发布镜像应在构建后记录仓库摘要，并用摘要部署。

首次创建平台管理员：

    docker compose --env-file .env.production exec backend python -m app.cli admin

邮箱与密码通过交互输入；已有用户需已验证、处于启用状态，并输入其当前密码才可提升平台权限；不会改写原密码。新平台管理员可登录平台管理页，配置全局免费截止时间、套餐目录、模型单价和机构额度。没有配置开放期时，新机构不会自动获得可用AI任务额度。

检查：

    docker compose --env-file .env.production exec backend python scripts/doctor.py

镜像携带只读运维脚本，诊断不输出凭证。健康接口为 /api/v1/health，接口说明为 /api/docs。正式部署需保存 compose ps、健康结果和迁移版本为验收证据。

## OCR 扩展

默认关闭OCR，避免把未安装的组件当作识别结果。启用步骤：

    docker build -t care-ops:0.3.0-rc1 .
    docker build -f deploy/Dockerfile.ocr -t care-ops-ocr:0.3.0-rc1 .
    docker compose --env-file .env.production --profile ocr up -d

配置 OPS_OCR_ENABLED=true，并重新创建后端及 Worker。普通 Worker 只消费 ops 队列，OCR Worker 单独消费 ocr 队列。OCR依赖固定于 backend/requirements-ocr.lock，模型首次下载与初始化需在部署节点验证；本机没有实际运行 PaddleOCR 模型。

OCR Worker的HOME与XDG缓存已指向持久卷。首次下载需在部署节点验证并记录模型文件哈希，不能把首次下载成功等同于票据识别通过。验收中必须用真实票据验证识别、草稿与人工确认入账。

## 每机构浏览器发布节点

1. 在隔离发布主机安装 rootless Docker。准备与浏览器UID一致的独立daemon用户；确认内核支持非特权user namespace与Chromium沙箱。为网关容器映射到主机的UID显式授予该rootless socket读写ACL，保持网关非特权用户；容器内UID与主机映射UID并不相同，不能只依靠同名账号推断权限。网关会拒绝连接rootful daemon。
2. 构建浏览器镜像：
   
       docker build -f publisher/Dockerfile -t care-ops-publisher:0.3.0-rc1 .
3. 配置 ROOTLESS_DOCKER_SOCKET、OPS_PUBLISHER_TOKEN、PUB_BROWSER_IMAGE；应用端使用相同网关认证主密钥。
4. 启动 publisher/compose.yaml。网关仅监听127.0.0.1:8900。跨主机使用受限私网TLS反向代理，不公开裸端口。发布主机防火墙禁止浏览器网络访问应用数据库、宿主机管理端口、云元数据与其他私网段。
5. 网关只创建固定镜像、固定命令、资源受限、只读根、非特权用户的机构容器。每机构独立加密状态卷，/tmp为内存文件系统；浏览器不挂载daemon socket。
6. 机构在应用中扫码登录三个平台，逐个平台验收。两端部署开关 OPS_ALLOW_LIVE_PUBLISH 与 PUB_ALLOW_LIVE 均为true后才可提交。负责人仍需机构授权与计划授权。
7. 默认最多20个机构容器，可用 PUB_MAX_TENANTS 调整。停用机构的容器和卷由运维按留存要求管理，不自动删除登录状态。

发布适配器采用上游选择器与官方创作者页面。视频号图文仍未实现，本期采用视频成品。DOM变更、安全验证、作者声明或封面控制变化可能进入待处理状态。没有作品ID和链接的页面跳转不能判定成功，不会为凑“成功”再次点击发布。

## 企业微信官方客服

负责人保存独立企业ID、客服Secret、客服账号ID、Token与EncodingAESKey。回调地址为：

    https://域名/api/v1/webhooks/wecom/机构ID

后台完成URL验证后，验收回调验签、解密、账号校验、重复回调、消息同步、资料引用、人工接管、真实发送与接管中停止机器人回复。应用内接管控制本系统机器人；不替代企微后台接待人员的服务状态配置。

请使用官方微信客服开放权限。企业微信客服不等同于任意客户群群控；社群模块在未接通具备授权的发送渠道时保留员工发送任务。

## 发布前检查

必须完成真实供应商调用、实际账户发布、企微接待、原生PG集成、镜像扫描、HTTPS与SMTP、S3权限、备份恢复、升级和代码回滚验证。当前交付包中的状态报告保留“未验证”，需要部署负责人填写真实证据，不能直接改为已通过。


## 0.3.0-rc1 升级与 MCP

角色与互动新增迁移 `0002_staff_social`，机构RLS表增至25张。升级操作使用现有迁移角色运行 Alembic，保留原有加密主密钥。完整离线SQL只供空库审查，不能直接覆盖已有库。

发布镜像现包含固定源码编译的小红书MCP服务，构建会解析 Go 依赖，需要访问 Go 模块代理与校验服务。构建镜像按摘要固定；浏览器采用现有Playwright镜像的标准Chromium，运行时不下载第三方浏览器。

MCP 内部路径 `/mcp/{tenant}/{account}/{platform}` 通过受限私网TLS访问，鉴权令牌沿用网关租户派生规则。实际回复还需应用 `OPS_ALLOW_LIVE_REPLIES=true` 与节点 `PUB_ALLOW_REPLIES=true`。默认均关闭。浏览器节点不获得财务数据库、模型或抖音官方接口凭证。

本地开发可运行 `scripts/build-mcp.ps1 -InstallTools` 并准备 Python Playwright Chromium，再运行 `scripts/dev.ps1 -Publisher`。开发网关仅监听回环地址，禁止生产使用；详细步骤见 STAFF_MCP.md。

## 0.3 升级

当前镜像标签为 `0.3.0-rc1`，迁移至 `0003_operations`，机构隔离表39张。先备份数据库和私有对象，单独保管原加密主密钥，在恢复库演练后升级。不要将完整离线建库 SQL 重复执行到已有库。

本地 OCR 的 Windows 解释器路径不进入生产 `.env`。Linux OCR Worker 使用镜像自身 Python 3.12 和 `requirements-ocr.lock`，启动 Compose 的 `ocr` profile。生产仍需原生 PostgreSQL、镜像扫描、真实通知和账号验收，详情见 [0.3 交付说明](OPERATIONS_03.md)。

## 0.3.1 升级

新部署使用0.3.1-rc1镜像，数据库迁移至`0004_capabilities`，机构RLS表仍为39张。迁移为旧教务人员追加独立排班授权以保留原行为；升级后负责人可在“成员与授权”逐人调整。升级前备份并在恢复库演练，保留加密主密钥。新增业务不要求同步网站账号或导入主站数据库。
