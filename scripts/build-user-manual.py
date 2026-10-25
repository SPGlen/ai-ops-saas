"""Build the dated product manual from reviewed UI and source facts. No service writes."""
from pathlib import Path
import base64, html, json, re
from datetime import datetime
from zoneinfo import ZoneInfo
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image, PageBreak, KeepTogether
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT, TA_CENTER
from reportlab.lib.utils import ImageReader
from pypdf import PdfReader

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT/'output'/'pdf'; OUT.mkdir(parents=True, exist_ok=True)
TMP = ROOT/'tmp'/'pdfs'/'user-manual'; TMP.mkdir(parents=True, exist_ok=True)
PDF = OUT/'知营使用说明书与自媒体账号接入指南.pdf'
HTML = ROOT/'docs'/'USER_MANUAL.html'
CHECK = json.loads((ROOT/'docs/account-connection-inspection.json').read_text(encoding='utf-8'))
CHECKED = datetime.fromisoformat(CHECK['checked_at'].replace('Z','+00:00')).astimezone(ZoneInfo('Asia/Singapore')).strftime('%Y年%m月%d日 %H:%M')
PAGES = []

def page(title, *blocks): PAGES.append({'title': title, 'blocks':list(blocks)})
def p(text): return {'type':'p','text':text}
def h(text): return {'type':'h','text':text}
def steps(*items): return {'type':'steps','items':list(items)}
def bullets(*items): return {'type':'bullets','items':list(items)}
def table(headers, rows, widths=None): return {'type':'table','headers':headers,'rows':rows,'widths':widths}
def picture(name, caption, height=230): return {'type':'image','path':'docs/screenshots/manual/'+name+'.png','caption':caption,'max_height':height}
def note(text): return {'type':'note','text':text}

page('知营使用说明书',
 p('教育机构运营工作台与自媒体账号接入指南'),
 p('适用版本 0.4.0 rc1　｜　检查日期 2026年10月23日　｜　适用人员 机构负责人 员工 部署维护人员'),
 p('知营用于协同管理招生、学员、教务、课返完成考核、财务、经营报表和自媒体矩阵。一人可以兼任多个岗位，也可以由多人分工；负责人统一分配功能授权。'),
 note('当前页面属于独立企业演示环境。账号列表可以展示和建档，但真实扫码、模型调用、发布及回复均被拦截。接入真实平台必须使用另外的测试环境，并先连接发布执行节点。'),
 h('阅读路线'),
 table(['页码','内容','建议阅读者'],[
 ['2','登录和岗位授权','负责人及所有员工'],['3至4','招生报名 学员档案 教务和课返','招生 教务 授课 排班'],['5至7','财务 报表 流程和社群','负责人 财务 教务'],['8至10','账号连接 三平台能力及核验','负责人 内容运营 运维'],['11至12','内容制作 预算 排程和复盘','负责人 内容运营'],['13至14','部署接入 故障排查 交接清单','部署维护人员及负责人']], [60,237,194]),
 h('第一次体验'),
 steps('打开本机 http://127.0.0.1:8188/，选择机构负责人进入演示。外网使用负责人当天提供的临时域名，先在网页输入演示访问码，无需用户名，也无需手动添加 #demo。','先看企业演示总览，再按招生线索、学员档案、财务台账、经营报表、自媒体矩阵的顺序操作。','切换授课、招生或财务岗位，核对菜单和数据范围变化。演示号码和票据均为虚构示例。'),
 p('账号连接的完整操作在第8至10页；需要部署人员配合的设置在第13页。'))

page('登录和岗位授权',
 p('员工通过负责人发出的邀请加入指定机构，不需要另建自己的机构。一个账号可以加入多个机构，操作前先核对页面右上方的当前机构。'),
 table(['岗位','默认可处理的内容','范围和限制'],[
 ['机构负责人','本机构全部业务和配置','管理成员 账号绑定 预算及策略'],['招生','线索 预约 试听和订单','本人负责的业务；不能登记收退款'],['授课','班级 学员 签到 课返KPI及反馈','本人任教范围；不能改财务和课时余额'],['排班','查看班级并维护排课','不包含学员联系方式 签到及财务'],['教务','学员 分班 请假补课 课时及反馈','新增排课修改能力需另授排班'],['整体营收查看','实收 退款和净收汇总 趋势','不含订单 费用 票据及学生明细'],['财务','订单 收退款 费用 票据及结算','只读必要学员资料，不读教学反馈'],['内容运营','内容 素材 账号查看 发布及复盘','本机构全部自媒体账号；不能管理绑定和预算']], [76,195,220]),
 h('负责人如何分配'),
 steps('进入成员与授权，邀请员工时填写邮箱并勾选岗位。邀请24小时有效，可撤销，只能接受一次；正式环境需要可用邮件服务。','已有员工点击调整授权，可以同时选择多个岗位；保存后后续请求和未执行任务会重新校验。','员工离职时停用其成员资格。至少保留一名有效负责人，不能把最后一名负责人撤销或停用。'),
 note('兼任按具体操作合并。例如授课加营收查看可以看营收汇总，学员和家庭反馈仍限任教范围。平台管理员管理机构权益，访问业务也需要该机构成员身份。'),
 p('企业演示中的角色选择和切换仅用于展示。演示环境不发送真实邀请邮件；正式使用时不要共享演示密码。'))

page('招生录入和报名',
 p('入口为招生线索。先建立线索，再记录联系、预约、到场和报名；纸表或Excel中的收款标记不能代替财务登记。'),
 h('招生表的使用'),
 steps('下载系统Excel模板或打印PDF模板。为每个孩子保留稳定线索编号，同一家长的不同孩子分行填写。','填写学员、年级、家长及关系、家长手机号、来源、意向班级、负责人、预约、阶段和备注。正在跟进的记录无需虚构流失原因。','上传Excel，或在启用OCR的环境上传清晰图片和多页PDF。单文件最多25MB、PDF最多20页、最多500行。','识别后对照原件逐行检查，处理低置信度、重复候选、负责人和班级匹配，再选择确认导入。缺编号时人工选择候选，不能只凭手机号合并。','导入后更新联系阶段、跟进时间和预约。记录试听到场；未成交需填写实际原因。状态以系统中的业务记录联动。'),
 note('当前企业演示可实际解析Excel；图片和PDF真实OCR关闭。扫描到已收款、已报名或已退费时只进入待核对信息，不会自动产生账款。'),
 h('从线索到正式报名'),
 steps('为学员建立档案，在财务台账或有权限的课程订单入口新增报名订单。直接填写项目名称、金额、优惠、购买课时、招生负责人，并关联线索及可选班级。','财务核对实际到账，登记收款。定金可以单列，未缴清不计正式报名转化。','缴清应收后，在教务管理的报名与课时中确认报名和课时账户，必要时分班。正式报名状态由这些业务记录产生。'),
 table(['状态','实际含义'],[['已预约','已确认试听安排，尚未说明到场或付款'],['已到场','已经试听，不自动等于正式报名'],['正式报名','缴清应收并完成报名课时确认'],['未成交','结束本轮跟进，保留实际原因']], [100,391]),
 p('列表、关联下拉、导出和报表均按当前岗位过滤。多人页面会持续刷新；如出现版本冲突，先刷新读取最新记录，再修改。'))

page('学员档案和教务',
 picture('07-students','图1 从班级进入学员档案，家长手机号使用独立的联系字段。',215),
 h('学员档案'),
 steps('进入学员档案，按班级查看，或搜索学员、家长和手机号；可以筛选老师和在读状态。','点击学员，查看家长姓名、关系、手机号、档案备注、报名、剩余课时和出勤。按实际情况维护多个家长；不同孩子分别建档。','分班、调班、退班使用对应业务入口并记录生效时间和原因，不用普通编辑覆盖报名历史。'),
 h('排课 签到 请假和补课'),
 bullets('排班人员维护课次时间、时长和状态。教师只操作任教班级；教务授权不自动包含排课修改。','签到每次扣减1课时；同一报名同一课次重复签到不重复扣减。已结束的报名不能继续签到。','批准请假后原课不扣课时，补课安排到另一实际课次，再按实际到课签到。课时调整由有权限人员填写原因并留痕。'),
 h('课返完成考核和家庭反馈'),
 p('老师在排课或签到相关页面确认本班本课次的课返是否完成。默认课程结束后24小时截止，取消课次不考核；教务纠正记录必须写原因。不再编辑或AI生成课返正文。'),
 p('学员家长反馈另行记录教学、课程安排、服务等真实意见及可选1至5分评分。处理后填写结果。家庭反馈与教师课返KPI是两类记录，未评分不推断为满意。'))

page('财务台账和票据',
 picture('06-finance','图2 财务图表可筛选日期、班级和来源渠道，再进入流水和票据。',228),
 steps('在财务台账选择期间、班级或来源，查看实收、退款、净收、已确认费用及收支差额。点击图表定位相关明细。','点击订单或查看票据与详情，检查关联收款、费用、票据原件、识别草稿、核对和操作记录。可以关联多张图片或PDF。','按真实发生登记收款、费用或退款。OCR和AI提取只提供草稿，财务核对后才确认入账；当前演示不运行真实OCR。'),
 h('登记退款'),
 bullets('先核对购买、已上、未上课时及调整明细；填写实际退款金额和必填原因，系统保存退款当时的课时快照。','部分退款但继续就读时保留报名关系，不计流失。退读退费时明确结束哪些报名；同一学员仍有其他有效报名时不计机构学员流失。','误登记使用有依据的冲正或调整，保留原流水；不要重复新增一笔退款来抵消错误。'),
 note('系统是财务台账，不执行银行转账、银行退款或发票开具。营收图表为已登记现金口径，不等于按课时确认收入，也不能直接视为利润。'),
 p('财务可看必要的学员关联资料，但不能因此读取任课内容和家庭反馈。仅有整体营收查看授权的人员不能进入票据和交易明细。'))

page('周报月报和异常提醒',
 p('经营周报和月报汇总招生、在读变化、出勤、课返、现金收支及家庭反馈。当前经营文字摘要由确定性规则生成，真实AI润色需另接模型。'),
 table(['指标','系统口径'],[
 ['线索转化率','本周新增线索中截至统计时正式报名数，除以本周新增线索数；跨周成交回补原批次。'],['试听转化率','本周首次到场的线索中截至统计时正式报名数，除以本周首次到场线索数。'],['新增在读','本期首次缴清并确认报名的去重学员；续费和重新入读另列。'],['月度流失率','本月退读人数，除以月初在读和本月新增在读的去重人数。'],['月度出勤率','已结束课次的实到人次，除以应到人次；批准请假仍是未出勤，取消课次不计。']], [95,396]),
 h('查看和保存报告'),
 steps('进入经营周报 / 月报，选择周期。查看当前授权范围内的指标及原因明细；负责人可以查看机构完整报告。','已保存报告是快照，不覆盖旧版。补录和冲正后需要更正版时生成新版本，比较版本时核对生成时间。','缺分母显示暂无数据，缺历史期初或日期时标为待校准；先补齐依据，不能把缺失改成零。'),
 h('异常和管理群推送'),
 p('负责人在经营规则与提醒设置阈值、适用班级、报告时间和管理群机器人。默认流失率达到或超过30%触发异常，记录触发值、周期、关联明细和处理意见；恢复后保留历史。'),
 p('默认中国时区每周一09:00生成上周周报，每月1日09:00生成上月月报。正式环境需Worker和调度器运行；企业演示关闭自动调度和真实群推送。'),
 note('通知只发送经营摘要和登录查看链接，不含儿童资料、手机号或家庭反馈原文。结果未知时先到群里核实，再决定是否重试。管理群通知与暂停的微信AI客服独立。'))

page('表单流程和社群运营',
 h('表单与流程'),
 steps('负责人进入表单与流程，新建定义或加载模板。表单可添加字段、排序、分组、必填、选项、条件显示和岗位读写限制。','流程画布连接开始、填写、审批、条件、并行、通知、业务动作和结束节点。选择实际审批岗位或成员；发布前检查分支、审批人和权限。','先预览和试运行，确认后发布。独立表单可提交申请；需要约束费用、退款等业务时，另外启用对应业务流程。'),
 table(['场景','是否拦截原业务'],[['财务直接登记','默认保留，可以按权限直接登记'],['已发布但未启用的业务流程','仍不拦截原业务'],['已发布且已启用的对应业务流程','原业务接口同时检查审批，不可绕过'],['独立表单和独立流程','按显式提交运行，不必启用业务拦截']], [174,317]),
 p('提交实例固定表单及流程版本，新版本只影响新提交。退回后修改关键数据需重新审批；审批人停用时转负责人待分配，不自动通过。财务实际发生确认仍由财务完成。'),
 h('社群运营'),
 steps('建立活动任务，填写目标家庭分组、文案、计划时间和实际发送渠道。','当前主要使用员工人工发送路径。员工在官方渠道实际处理后，登记真实的触达、跟进和转化结果。','没有已授权发送渠道时只保存文案和任务，不会自动给家长群发送。'),
 note('网页咨询、微信AI客服、评论和私信自动回复当前暂停。数字人直播入口已隐藏，真实数字人直播未接入。演示中已有的活动和审批案例仅为虚构业务示例。'))

page('自媒体账号接入总览',
 p('入口为自媒体矩阵。账号连接不是在网页中填写平台密码，也不是粘贴任意MCP网址。系统通过平台维护的发布执行节点，为每个机构和每个平台账号管理独立登录状态。'),
 table(['顺序','组件','谁负责'],[['1','网页矩阵账号中心','负责人填写品牌和账号资料并发起扫码'],['2','FastAPI业务后端','检查机构、岗位、预算、计划和任务版本'],['3','受控发布网关','部署人员设置地址及认证，转发允许的MCP工具'],['4','机构执行环境内的独立账号上下文','对应平台扫码、身份回读、发布和结果核实']], [38,220,233]),
 h('当前本机检查结果'),
 p('检查时间 '+CHECKED+' UTC+8。青禾演示机构当前有'+str(CHECK['account_count'])+'条账号记录，已连接0条、身份已核实0条。账号数量是当时快照，新增记录后会变化。'),
 bullets('服务健康，但任务模式为demo；发布节点未配置，模型未配置，真实发布关闭。','向账号登录接口发起不对外发送的检查，返回409 DEMO_EXTERNAL_DISABLED。这是演示隔离措施，不是二维码扫码失败。','添加账号可保存平台、备注、品牌、定位和预算；这一步只建档，不代表已经绑定真实账号。'),
 note('当前演示可以看流程和操作虚构记录，不能拿来接真实账号。正式联调需另一套数据库、媒体存储、密钥和发布节点状态，保留8188与当前外网演示。'),
 h('开始连接前准备'),
 bullets('负责人账号和目标机构已确认；已建立品牌、确认知识库并标明素材授权。','发布网关可达、浏览器环境可运行，小红书固定版本MCP二进制可用。','持有各平台账号的有权人员可逐个扫码；先关闭真实发送，完成身份和只读能力检查。'))

page('负责人连接账号的操作',
 picture('02-add-account','图3 添加账号只保存管理资料，真实登录在保存后的扫码入口完成。',280),
 steps('在品牌与分组先建立品牌，填写受众和风格，选择已审核知识库及授权素材。','回到矩阵账号，点击添加账号。填写账号备注，选择平台与品牌，设置定位、引导语、默认形式和账号月预算。','保存后，在该账号行点击扫码登录。执行环境生成二维码或登录页面截图，由对应平台手机应用扫码；每个账号分别完成。','点击扫码后检查身份，或勾选账号后批量检查身份。核对平台实际账号ID；不能只看昵称、备注或已登录文字。','点击核验能力，查看逐项状态和具体原因。小红书当前会额外尝试搜索能力；发布和指标仍分别需要真实回执。','同品牌账号可加入一个或多个分组。同平台多个账号分别扫码；重叠分组在新运行创建时去重，不会重复投递。'),
 note('配置和扫码由负责人控制。内容运营可以操作本机构全部账号的内容和任务，不能自行绑定账号、提高预算或扩大自动发布策略。'))

page('三平台的能力和验收',
 table(['项目','小红书','抖音','微信视频号'],[
 ['发布实现','现有小红书MCP','浏览器发布适配器','浏览器发布适配器'],['成品形式','图文 视频','图文 视频','视频；图文不支持'],['可靠身份回读','已实现本人资料ID回读，待真实账号验收','已实现显式本人主页链接识别，待真实页面验证','稳定账号ID回读尚待适配'],['自动发布前提','身份和发布能力分别核实','身份和发布能力分别核实','身份能力未完成前不能开无人值守'],['评论','源码有读取和回复适配；当前产品暂停互动','需官方权限及账号授权；当前暂停互动','当前未接通，官方后台人工处理'],['私信','当前连接器不支持','需对应官方权限与授权，未完成实际收发验收','当前未接通，官方后台人工处理']], [83,136,136,136]),
 h('如何理解页面状态'),
 bullets('未连接或待授权：先检查执行节点和登录状态；出现验证码或账号异常时到官方端处理。','已登录或已连接：表示登录检测通过，不自动说明真实账号身份和发布能力已核实。','身份已核实：连接器回读到可靠账号ID。同机构重复绑定同一平台账号会被拦截；发现身份改变会暂停并要求重新核验。','能力待验证：需要对应能力的真实测试。可用才说明已验证这一项；不支持的项目使用官方后台人工操作。'),
 note('核验能力按钮不会发送一篇测试作品，也不会替代评论、私信的官方授权。三平台真实账号尚未在当前项目完成验收，不承诺扫码后即可全自动运营。'),
 p('真实发布后必须保存可核实的作品编号和链接。视频号当前的稳定身份适配仍是无人值守接入的明确阻塞项；不能人为填写身份标志绕过。'))

page('内容制作和预算',
 p('品牌是知识、受众、风格和素材的边界。进入内容工作室管理选题、素材和成品；进入自媒体矩阵管理多账号的版本化运营计划。内容工作室里的旧自动计划只保留历史提示。'),
 h('建立运营计划'),
 steps('选择品牌，明确选择账号或分组。母题矩阵模式共享选题，按账号生成不同内容；独立运营模式按账号定位分别选题。','选择常青选题、平台允许的RSS/Atom来源或已验证的小红书搜索。外部Feed域名由平台维护白名单。','设置星期、时刻、制作方式、视频时长、审核方式和费用来源。默认中国时区周二、周五18:00、视频45至90秒、逐条审核；每个计划最多12个时刻。','保存计划。内容运营保存的版本需负责人授权试运行预算；预算或策略调整后形成新版本，并重新核验。'),
 table(['预算层级','用途'],[['平台额度或机构自带Key','确定实际用哪套模型凭证；不足不自动换Key'],['机构月预算','限制整个机构矩阵的模型支出'],['账号月预算','限制该账号任务的支出'],['计划日预算和单次预算','限制计划当天及单次运行费用']], [185,306]),
 p('未配置额度或预算按零处理。机构、账号、计划多个约束共同生效，调用前预占，完成后按实际用量结算；共享选题成本单列一次。软件使用期与模型额度分开展示。'),
 h('试运行的费用和结果'),
 note('试运行不自动发布，但在正常测试环境会调用模型并可能收费，不能把它当免费预览。企业演示环境会阻止实际生成。执行预览只展示目标和预算范围，不产生模型成品。'),
 p('视频可用程序合成、AIGC或混合制作，最终成品才固定版本并独立盲评。当前模型服务连接为阿里云百炼，尚无独立DeepSeek适配，不能把DeepSeek Key填进百炼连接框。'))

page('发布排程和复盘',
 h('先完成一个账号的闭环'),
 steps('确认品牌知识、授权素材和预算，完成当前计划版本的一次成品及盲评试运行；检查每个账号子任务的成品。','在内容工作室选择固定成品版本，处理内容检查提示并完成独立盲评，再点击安排发布，选择明确账号和时间。','在独立联调环境，由部署人员开启应用与发布节点的真实发布开关，负责人授权机构发布。确认该次操作将向外部账号提交后，再执行首次真实作品。','到官方后台核对发布结果，保存作品ID和链接。当前账号对应发布能力通过真实回执确认；指标能力通过实际作品回收确认。','负责人在当前计划版本试运行通过、身份及发布能力均核实后，启用计划。正常逐条审核模式仍需审核后排期。'),
 h('日历和运行记录'),
 bullets('发布日历的计划时段是预排，不保证在该分钟已经公开可见。当前到时才创建运行，素材生成、审核和上传都会影响实际发布时间。','调度处理15分钟内到期的时段，更早错过的时段不会集中补发。保持Worker和调度服务运行；不需要持续打开浏览器或ChatGPT。','任务与复盘显示步骤、成品版本、费用、错误和账号子任务。部分成功时只处理失败账号，已成功作品不重新发布。'),
 h('异常和数据回收'),
 p('结果未知时先查询并在官方后台核对，不再次点击发布。暂停会阻止后续新调用和未提交发布；已经提交的付费任务继续查询、保存和结算。明确失败与未知结果采用不同恢复方式。'),
 p('默认T+3天回收作品指标，缺失不按零计算，可手工补录。不同平台分别查看口径；通过专属预约链接进入的招生可追踪归因，未带来源不推测。'),
 note('成品修改会形成新版本，原预测保留，新版本需重新盲评和排期。品牌、计划、知识或账号身份变化时，旧任务执行前会重新校验。'))

page('部署人员接入说明',
 p('本页供部署人员操作。负责人页面不能直接填写任意MCP服务地址；后端只调用平台维护的发布网关。小红书MCP、抖音和视频号浏览器能力均在网关后运行。'),
 table(['配置项','用途和要求'],[
 ['OPS_PUBLISHER_URL','应用和Worker可访问的受控网关地址；本机开发通常为 http://127.0.0.1:8900。'],['OPS_PUBLISHER_TOKEN','应用侧网关认证主密钥，至少32位；不填入品牌资料或前端。'],['PUB_MASTER_KEY','生产网关侧使用与应用一致的主密钥，并派生机构级凭证。'],['OPS_ALLOW_LIVE_PUBLISH 和 PUB_ALLOW_LIVE','应用和执行节点两侧真实发布开关；初始均关闭，真实发布联调时按授权启用。'],['OPS_ALLOW_LIVE_REPLIES 和 PUB_ALLOW_REPLIES','回复的两侧开关；当前产品互动暂停，打开开关不能替代功能适配和权限验证。'],['OPS_MATRIX_SOURCE_HOSTS','RSS/Atom HTTPS域名白名单；空值禁用外部Feed。'],['OPS_MATRIX_MAX_RUNNING','每机构运行推进并发，默认2；还受宿主和浏览器资源限制。']], [183,308]),
 p('Windows开发执行节点默认读取 .local/xiaohongshu-mcp.exe，可通过 scripts/build-mcp.ps1 构建。仅下载MCP源码不会自动接入网页；执行节点还需Chromium和依赖。生产镜像中包含固定版本的MCP执行程序。'),
 h('真实账号使用独立环境'),
 steps('使用独立端口，例如8192，另建数据库、数据目录、应用主密钥和发布节点状态；OPS_DEMO_MODE=false。不得指向8188及现有外网演示的数据库或状态卷。','先部署固定版本的发布网关、Chromium和小红书MCP。Windows开发节点与生产rootless Docker节点是两种部署路径。','在独立测试机构创建负责人、品牌和账号，先保持真实发送关闭，检查网关健康、扫码、可靠身份和只读能力。','配置模型、单价、额度和预算后，进行有成本的成品试运行；再分别联调真实发布、作品回读和T+3指标。'),
 note('现有 scripts/dev.ps1 -Publisher 使用常规开发配置，不会自动建立独立真实账号环境。请先显式配置独立数据库等资源，避免覆盖已有工作区。不要把此脚本当作独立联调环境的一键创建工具。'),
 p('生产发布镜像和网关当前使用0.4.0 rc1，版本以publisher/compose.yaml及镜像锁为准。浏览器节点与客户财务数据库隔离，不公开裸网关端口；跨主机采用受限私网TLS接入。'))

page('故障排查和交接核对',
 table(['现象','处理方式'],[
 ['演示环境拦截扫码登录','目前在企业演示。保留演示，切换到独立账号联调环境。'],['发布执行节点尚未连接','运维核对网关地址、认证密钥、节点健康、网络可达性和浏览器安装。'],['没有二维码或二维码过期','检查节点是否运行及账号上下文；重新获取登录图，使用对应平台应用逐个扫码。'],['已连接但身份待核验','核对连接器是否回读真实账号ID。抖音待真实页面验证，视频号稳定ID尚待适配。'],['核验能力后仍不能自动发布','检查真实发布回执、当前版本试运行、账号和机构预算、负责人授权及两端发送开关。'],['额度或预算不足','检查平台额度或所选自带Key、机构月、账号月、计划日与单次预算及预占。'],['已改计划但旧任务停止','使用新版本重新试运行和授权，不能让旧任务静默改投新账号。'],['发布超时或结果未知','先查官方作品和任务回执，保留待核实，不盲目重新提交。'],['评论 私信或微信客服不可用','当前功能暂停；按能力状态到官方后台人工处理，不能只打开环境开关。']], [172,319]),
 h('首次真实接入的交接清单'),
 bullets('机构、账号实际身份、品牌和分组对应正确；凭证互不覆盖，同平台重复绑定得到拦截。','记录应用版本、计划版本、知识版本、预算、发送授权人和测试时间。','保留真实作品编号、链接和官方核对记录；模拟测试、协议测试与真实账号测试分开。','验证重登、账号暂停、权限撤销、服务重启及未知结果处理；停止旧的重复发送调度后再切换。'),
 h('维护本手册时的代码依据'),
 p('账号页面见 frontend/src/MatrixPage.tsx；发布入口见 backend/app/routes_ai.py；身份、计划与预算见 backend/app/matrix.py；网关调用见 backend/app/integrations/publishing.py；执行和平台适配见 publisher/service.py。当前实机检查记录保存在 docs/account-connection-inspection.json。'),
 p('业务与权限参考 docs/MANAGEMENT_031.md、docs/MEDIA_MATRIX.md。旧版手册中仍提及的数字人页面和互动接待能力，不代表当前入口已启用；以本手册日期对应的代码及实际能力状态为准。'))

# Persist the reviewed content for subsequent manual updates.
(ROOT/'docs/user-manual.content.json').write_text(json.dumps({'version':'0.4.0-rc1','checked_at':CHECK['checked_at'],'migration_in_scope':False,'pages':PAGES},ensure_ascii=False,indent=2),encoding='utf-8')

# Embed Chinese fonts rather than depending on a reader's installed fonts.
pdfmetrics.registerFont(TTFont('YaHei','C:/Windows/Fonts/msyh.ttc',subfontIndex=0))
pdfmetrics.registerFont(TTFont('YaHeiBold','C:/Windows/Fonts/msyhbd.ttc',subfontIndex=0))
W=595.2756; H=841.8898; M=48; CW=W-2*M
styles={
 'p':ParagraphStyle('body',fontName='YaHei',fontSize=10,leading=16,textColor=colors.HexColor('#263b31'),wordWrap='CJK',spaceAfter=8),
 'h':ParagraphStyle('subheading',fontName='YaHeiBold',fontSize=12,leading=18,textColor=colors.black,spaceBefore=8,spaceAfter=7,keepWithNext=True,wordWrap='CJK'),
 'title':ParagraphStyle('title',fontName='YaHeiBold',fontSize=20,leading=28,textColor=colors.black,spaceAfter=16,wordWrap='CJK'),
 'cell':ParagraphStyle('cell',fontName='YaHei',fontSize=9.1,leading=13.6,textColor=colors.HexColor('#293e33'),wordWrap='CJK'),
 'head':ParagraphStyle('head',fontName='YaHeiBold',fontSize=9.2,leading=14,textColor=colors.white,wordWrap='CJK'),
 'caption':ParagraphStyle('caption',fontName='YaHei',fontSize=8.3,leading=12,textColor=colors.HexColor('#68776c'),wordWrap='CJK',spaceAfter=8),
 'note':ParagraphStyle('note',fontName='YaHei',fontSize=9.5,leading=15,textColor=colors.HexColor('#224b3a'),wordWrap='CJK'),
}
def para(text, kind='p'): return Paragraph(html.escape(text).replace('\n','<br/>'),styles[kind])
def make_table(b):
    widths=b['widths'] or [CW/len(b['headers'])]*len(b['headers'])
    scale=CW/sum(widths);widths=[v*scale for v in widths]
    rows=[[para(x,'head') for x in b['headers']]]+[[para(str(x),'cell') for x in row] for row in b['rows']]
    t=Table(rows,colWidths=widths,repeatRows=1,hAlign='LEFT')
    t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#314b60')),('ROWBACKGROUNDS',(0,1),(-1,-1),[colors.white,colors.HexColor('#f4f7fa')]),('GRID',(0,0),(-1,-1),.45,colors.HexColor('#D9D9D9')),('VALIGN',(0,0),(-1,-1),'MIDDLE'),('LEFTPADDING',(0,0),(-1,-1),7),('RIGHTPADDING',(0,0),(-1,-1),7),('TOPPADDING',(0,0),(-1,-1),6),('BOTTOMPADDING',(0,0),(-1,-1),6)]))
    return t
story=[]
for n,pg in enumerate(PAGES):
    if n: story.append(PageBreak())
    story.append(para(pg['title'],'title'))
    for b in pg['blocks']:
        typ=b['type']
        if typ in ('p','h'): story.append(para(b['text'],typ))
        elif typ in ('steps','bullets'):
            for i,text in enumerate(b['items'],1): story.append(para((str(i)+'. ' if typ=='steps' else '• ')+text))
        elif typ=='table': story.extend([make_table(b),Spacer(1,9)])
        elif typ=='note':
            t=Table([[para(b['text'],'note')]],colWidths=[CW]);t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,-1),colors.HexColor('#eef4e6')),('BOX',(0,0),(-1,-1),.5,colors.HexColor('#d4e1c7')),('TOPPADDING',(0,0),(-1,-1),10),('BOTTOMPADDING',(0,0),(-1,-1),10),('LEFTPADDING',(0,0),(-1,-1),12),('RIGHTPADDING',(0,0),(-1,-1),12)]));story.extend([t,Spacer(1,9)])
        elif typ=='image':
            file=ROOT/b['path'];iw,ih=ImageReader(str(file)).getSize();factor=min(CW/iw,b['max_height']/ih)
            story.append(KeepTogether([Image(str(file),width=iw*factor,height=ih*factor,hAlign='CENTER'),Spacer(1,5),para(b['caption'],'caption')]))
def decorate(c,doc):
    c.saveState();c.setFont('YaHei',8);c.setFillColor(colors.HexColor('#778478'));c.drawString(M,H-29,'知营使用说明书    0.4.0 rc1');c.drawRightString(W-M,H-29,'2026年10月23日')
    c.drawString(M,25,'当前能力以机构授权和真实联调结果为准');c.drawRightString(W-M,25,str(doc.page));c.restoreState()
class ManualDoc(SimpleDocTemplate):
    def afterFlowable(self, flowable):
        if isinstance(flowable, Paragraph) and flowable.style.name == 'title':
            title=flowable.getPlainText();key='chapter-'+str(self.page)
            self.canv.bookmarkPage(key)
            self.canv.addOutlineEntry(title,key,level=0,closed=False)
doc=ManualDoc(str(PDF),pagesize=(W,H),rightMargin=M,leftMargin=M,topMargin=57,bottomMargin=43,title='知营使用说明书与自媒体账号接入指南',author='知营产品项目',allowSplitting=1)
doc.build(story,onFirstPage=decorate,onLaterPages=decorate)

# A single-file, searchable browser edition, with no credentials or live API calls.
chunks=[]
for i,pg in enumerate(PAGES,1):
    out=[f'<section id="chapter-{i}"><span class="page-label">{i:02d} / {len(PAGES)}</span><h1>{html.escape(pg["title"])}</h1>']
    for b in pg['blocks']:
        typ=b['type']
        if typ in ('p','h'): out.append(f'<{"p" if typ=="p" else "h2"}>{html.escape(b["text"])}</{"p" if typ=="p" else "h2"}>')
        elif typ in ('steps','bullets'):
            tag='ol' if typ=='steps' else 'ul';out.append('<'+tag+'>'+''.join('<li>'+html.escape(v)+'</li>' for v in b['items'])+'</'+tag+'>')
        elif typ=='note': out.append('<aside class="note">'+html.escape(b['text'])+'</aside>')
        elif typ=='table': out.append('<div class="table"><table><thead><tr>'+''.join('<th>'+html.escape(v)+'</th>' for v in b['headers'])+'</tr></thead><tbody>'+''.join('<tr>'+''.join('<td>'+html.escape(str(v))+'</td>' for v in row)+'</tr>' for row in b['rows'])+'</tbody></table></div>')
        elif typ=='image':
            encoded=base64.b64encode((ROOT/b['path']).read_bytes()).decode();out.append('<figure><img alt="'+html.escape(b['caption'])+'" src="data:image/png;base64,'+encoded+'"><figcaption>'+html.escape(b['caption'])+'</figcaption></figure>')
    out.append('</section>');chunks.append(''.join(out))
nav=''.join(f'<a href="#chapter-{i}"><span>{i:02d}</span>{html.escape(pg["title"])}</a>' for i,pg in enumerate(PAGES,1))
page_html='''<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>知营使用说明书与自媒体账号接入指南</title><style>
*{box-sizing:border-box}html{scroll-behavior:smooth}body{margin:0;background:#f4f6ef;color:#273f32;font:15px/1.9 Microsoft YaHei,system-ui,sans-serif}nav{position:fixed;inset:0 auto 0 0;width:260px;background:#183f32;color:#eef5e6;overflow:auto;padding:30px 20px}nav strong{font-size:24px;display:block;margin-bottom:5px}nav small{color:#b2c3a4}nav a{display:flex;gap:12px;font-size:13px;line-height:1.5;padding:10px 8px;color:#d5e4ca;text-decoration:none;border-radius:6px}nav a:hover{background:#2a5540}nav a span{color:#abc692}main{margin-left:260px;max-width:1240px;padding:28px 42px}section{background:white;border:1px solid #e0e6d8;border-radius:14px;padding:36px 42px;margin-bottom:28px;scroll-margin-top:20px}.page-label{font:12px system-ui;letter-spacing:2px;color:#7f946e}h1{color:#000;font-size:27px;line-height:1.5;margin:12px 0 23px}h2{color:#000;font-size:19px;margin:26px 0 12px}p{margin:0 0 16px}li{padding:3px 0;margin-bottom:5px}.note{background:#edf4e5;border:1px solid #d6e3c8;border-radius:8px;padding:16px 19px;margin:18px 0;color:#28513b}.table{overflow-x:auto;margin:18px 0}table{border-collapse:collapse;width:100%;font-size:13px}th,td{border:1px solid #d9d9d9;padding:11px 13px;vertical-align:middle;text-align:left}th{background:#314b60;color:#fff;font-weight:600}tr:nth-child(even){background:#f4f7fa}figure{margin:20px 0}img{max-width:100%;height:auto;border:1px solid #e1e7da;border-radius:7px}figcaption{font-size:12px;color:#7b8973;line-height:1.6;margin-top:8px}button{font:inherit;border:0;border-radius:7px;background:#d9edb5;color:#194735;padding:7px 13px;margin:16px 0;cursor:pointer}@media(max-width:850px){nav{position:relative;width:auto;max-height:300px}main{margin:0;padding:18px}section{padding:24px 19px}h1{font-size:24px}}@media print{@page{size:A4;margin:16mm}nav{display:none}main{margin:0;padding:0;max-width:none}body{background:white;font-size:10pt}section{border:0;border-radius:0;margin:0;padding:0;page-break-after:always}section:last-child{page-break-after:auto}h1{font-size:20pt}h2{font-size:13pt}table{font-size:9pt}img{max-height:85mm;width:auto}p,li{line-height:1.65}tr,figure,.note{break-inside:avoid}thead{display:table-header-group}}
</style></head><body><nav><strong>知营使用说明</strong><small>0.4.0 rc1 · 2026年10月23日</small><button onclick="window.print()">打印或保存PDF</button>NAV</nav><main>CONTENT</main></body></html>'''
HTML.write_text(page_html.replace('NAV',nav).replace('CONTENT',''.join(chunks)),encoding='utf-8')
reader=PdfReader(str(PDF));texts=[pg.extract_text() or '' for pg in reader.pages]
expected=[pg['title'] for pg in PAGES]
info={'created_at':datetime.now(ZoneInfo('Asia/Singapore')).isoformat(),'pdf':str(PDF),'html':str(HTML),'expected_pages':len(PAGES),'actual_pages':len(reader.pages),'page_text_lengths':[len(t) for t in texts],'chapter_titles_found':all(any(title in t for t in texts) for title in expected),'source_check':str(ROOT/'docs/account-connection-inspection.json'),'real_external_actions':False,'credentials_included':False}
(TMP/'structure-check.json').write_text(json.dumps(info,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(info,ensure_ascii=True))
if len(reader.pages)!=len(PAGES): raise SystemExit('Page overflow: review and reduce the affected page before delivery.')
if not info['chapter_titles_found']: raise SystemExit('Missing chapter heading in exported PDF.')
