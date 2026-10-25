# 开源复用与许可

检索与固定日期：2026-10-20。GitHub星数不作为安全证明。源码参考版本固定于 upstream-lock.json；许可证原文保存在 licenses/。

| 项目 | 许可 | 本工程的实际使用 |
|---|---|---|
| fastapi/full-stack-fastapi-template | MIT | 参考FastAPI全栈项目、容器和测试组织；本项目机构授权、Cookie会话与RLS为独立实现，未把上游模板包装成现成SaaS |
| pydantic/pydantic-ai | MIT | 实际运行依赖 pydantic-ai-slim 2.58.0，结构化输出与受控模型调用 |
| 本地 cheat-on-content | MIT | 把schema1.4版本、盲预测、T+3实绩、候选规则复核协议产品化；保留源工作区不变 |
| xpzouying/xiaohongshu-mcp | Apache-2.0 | 0.2版实际编译并运行固定源码的账号独立MCP；保留Apache许可及修改通知，通过私有鉴权网关使用 |
| dreammis/social-auto-upload | MIT | 复用其平台页面与选择器思路，隔离重写单次提交及可信结果判定；不运行旧Web后台，不复制反检测逻辑 |
| langbot-app/LangBot | Apache-2.0 | 协议适配研究参考；运行时直接实现官方企微客服接口，没有加载LangBot插件或复制其全局会话/权限体系 |
| PaddlePaddle/PaddleOCR | Apache-2.0 | 可选OCR Worker依赖3.7.0，PaddlePaddle 3.3.1、PaddleX 3.7.2，需部署时初始化模型 |
| Microsoft Playwright | Apache-2.0 | 浏览器自动化与端到端测试；Chromium seccomp配置来自官方仓库 |
| Swagger UI | Apache-2.0 | 随包提供固定npm版本的静态接口文档，原LICENSE/NOTICE同目录保留 |
| PGlite / pgvector | Apache-2.0 / PostgreSQL License | 只在开发测试中验证真实Postgres SQL语义与向量/RLS，不作为生产数据库 |

其余Python与前端依赖按各自许可分发，精确版本和完整性哈希分别见Python锁文件与package-lock.json。Docker底层镜像摘要见 deploy/image-lock.json。浏览器基础镜像的注册表摘要也已固定，仍需在发布主机拉取、扫描和运行验证。

安全核查：[Pydantic AI公告](https://github.com/pydantic/pydantic-ai/security/advisories/GHSA-6fqq-452j-qhrp)的修复下限为2.53.0，本项目锁定2.58.0。依赖扫描报告与实际安装版本见本目录，扫描只说明当次数据库中没有命中已知漏洞，不代表不存在缺陷。

[SAU公开问题214](https://github.com/dreammis/social-auto-upload/issues/214)涉及旧后台鉴权、路径与依赖问题，因此该后台不进入本工程。官方页面也会发生选择器变化：[抖音标题输入问题275](https://github.com/dreammis/social-auto-upload/issues/275)说明了兼容选择器的必要性。真实三平台发布仍需独立验收。

导入器只读取 .cheat-state.json 验证schema，然后允许 audience.md、script_patterns.md、rubric_notes.md、benchmark.md、candidates.md 五份文本，输出未审核知识库资料。不会递归复制 .cheat-cache、登录目录、浏览器缓存、凭证、调试文件、样本视频或历史预测文件。源资料与协议引用文件的SHA-256记录于 skill-provenance.json。


## 0.2.0-rc1 实际 MCP 复用

xiaohongshu-mcp 现为固定源码编译的真实独立 MCP 服务，原始68份源码输入与提交 `7797fd375aba02dcd33afe143f6bee13e5870859` 一致，验证见 xhs-source-verification.json。保留 Apache-2.0 LICENSE。LOCAL_PATCHES.json 列出依赖升级、标准 Chromium 管理、绝对账号路径、强制鉴权和结构化身份输出等本地改动；原下载目录不变。

上游自定义浏览器下载和指纹改动不用于本产品。使用已安装的标准 Playwright Chromium，保留沙箱。Go SDK 升至1.8.0，x/net升至0.61.0等，精确版本和校验为 vendored go.mod/go.sum。Go1.27.3归档和Docker构建镜像均固定校验信息。

抖音/视频号发布继续复用现有 social-auto-upload 选择器适配器并通过私有MCP暴露，不运行其旧Web后台。低星MCP及私有托管视频号数据服务未作为运行依赖引入。抖音官方评论使用固定官方域名；私信未验证部分保留人工方式。

本地开发工具 uv 的 [GHSA-hq85-5cpj-mr62](https://github.com/astral-sh/uv/security/advisories/GHSA-hq85-5cpj-mr62) 已通过升级到0.13.4处理；它不属于运行时依赖。新增Go CI使用 [actions/setup-go v7.0.0固定提交](https://github.com/actions/setup-go/commit/b7ad1dad31e06c5925ef5d2fc7ad053ef454303e)。

## 0.3 补充许可与实现

- [React Flow](https://reactflow.dev/) / `@xyflow/react` **12.12.0**，MIT；用于可视化流程画布，保留归属标记。许可原文见 `licenses/react-flow/LICENSE`。没有复制 Pro 示例。
- ReportLab **5.0.1**，BSD 许可；生成招生打印模板，许可原文见 `licenses/reportlab/LICENSE`。
- pypdf **6.21.2**，BSD 许可；PDF 页数与加密检查，许可原文见 `licenses/pypdf/LICENSE`。
- PaddleOCR CPU 关闭 MKL-DNN 的参数参照[官方使用说明](https://www.paddleocr.ai/latest/en/version3.x/pipeline_usage/OCR.html)。PNG/PDF 打印体合成样本真实测试报告单独记录，不能外推为手写材料验收。

0.3 默认暂停咨询与自媒体互动自动回复；0.2 文档中的互动能力描述作为历史接入资料保留。本版自媒体生产和发布继续使用原固定源码及安全边界。


## 0.4 矩阵运营

继续使用固定上游源码和现有锁文件，没有新增第三方运行依赖。`cheat-on-content`（MIT）的选题、独立盲评、不可覆盖预测、T+3复盘及规则全量重算方法转换为服务端业务任务；没有复制个人账号目录、品牌状态、内容、历史预测或凭证。发布网关继续保留小红书Apache-2.0及SAU MIT归属。新账号路由、费用预占和调度逻辑为本产品实现。


## 可选临时演示连接工具

cloudflared，Cloudflare，Apache-2.0；上游：https://github.com/cloudflare/cloudflared 。固定版本与官方校验值见 `demo-tools-lock.json`。演示脚本仅按需下载至本机 `.local/tools/`，源码交付包不分发可执行文件或隧道凭证。免费Quick Tunnel仅用于开发展示，不代替生产部署。
