# 员工服务 v1：答案复核材料

48 道有依据问题的标准事实、首次回答和引用。另列8道无依据问题。
这是合成材料；标准答案由代理编写。未填写任何正确性结论或人类复核签名。
请业务负责人确认制度/标准事实后，逐题判断必要事实是否覆盖、答案与引用是否支持该决策。
请求错误没有可复核答案；不得计为正确。复核记录填入本地 state.json 的 reviews 后运行 report。
固定数据指纹：`cdfb0b2a9f1cb2d590d6d8354173b222e0aa3511d2d4e9109cb4c122e3ca9adc`。

## qa_travel_01 · development

问题：境内出差每晚住宿和每天餐补分别是多少？

标准要点：每晚住宿上限500元，每天餐补80元。

必要事实：

- 住宿上限为每人每晚500元
- 餐补为每人每天80元

来源证据：

- [travel](../../benchmarks/business_baseline/data/docs/travel.txt)：住宿上限为每人每晚500元
- [travel](../../benchmarks/business_baseline/data/docs/travel.txt)：餐补为每人每天80元

首次回答（answered）：

> 境内出差住宿上限为每人每晚500元，餐补为每人每天80元。

实际引用：

- travel：境内出差住宿上限为每人每晚500元，餐补为每人每天80元。

复核：待复核；正确性：____；逐项事实支持：____；复核人/日期：____。

## qa_travel_02 · development

问题：上周出差结束了，什么时候之前提交报销，需要什么材料？

标准要点：结束后15个自然日内，附发票和已批准的出差申请。

必要事实：

- 出差结束后15个自然日内提交
- 附发票和已批准的出差申请

来源证据：

- [travel](../../benchmarks/business_baseline/data/docs/travel.txt)：出差结束后15个自然日内提交
- [travel](../../benchmarks/business_baseline/data/docs/travel.txt)：附发票和已批准的出差申请

首次回答（answered）：

> 请在出差结束后15个自然日内提交报销，并附上发票和已批准的出差申请。

实际引用：

- travel：报销须在出差结束后15个自然日内提交，附发票和已批准的出差申请。

复核：待复核；正确性：____；逐项事实支持：____；复核人/日期：____。

## qa_travel_03 · development

问题：我要订每晚650元的酒店，能先订再申请超标吗？

标准要点：不能按常规先订后补；超过上限须预订前取得部门负责人书面批准。

必要事实：

- 超过住宿上限须在预订前取得部门负责人书面批准

来源证据：

- [travel](../../benchmarks/business_baseline/data/docs/travel.txt)：超过住宿上限须在预订前取得部门负责人书面批准

首次请求：ERROR，HTTP 502；无可复核答案。

复核：待复核；正确性：____；逐项事实支持：____；复核人/日期：____。

## qa_travel_04 · development

问题：出差高铁费是否包含在每天80元餐补中？

标准要点：餐补每天80元；交通费用按有效票据另行实报实销。

必要事实：

- 餐补为每人每天80元
- 交通费用按有效票据实报实销

来源证据：

- [travel](../../benchmarks/business_baseline/data/docs/travel.txt)：餐补为每人每天80元
- [travel](../../benchmarks/business_baseline/data/docs/travel.txt)：交通费用按有效票据实报实销

首次请求：ERROR，HTTP 502；无可复核答案。

复核：待复核；正确性：____；逐项事实支持：____；复核人/日期：____。

## qa_leave_01 · development

问题：我准备下周休年假，要提前多久申请，由谁批准？

标准要点：至少提前3个工作日申请，直属经理批准。

必要事实：

- 年假须至少提前3个工作日提交申请
- 由直属经理批准后生效

来源证据：

- [leave](../../benchmarks/business_baseline/data/docs/leave.txt)：年假须至少提前3个工作日提交申请
- [leave](../../benchmarks/business_baseline/data/docs/leave.txt)：由直属经理批准后生效

首次回答（answered）：

> 年假须至少提前3个工作日提交申请，并由直属经理批准后生效。

实际引用：

- leave：年假须至少提前3个工作日提交申请，由直属经理批准后生效。

复核：待复核；正确性：____；逐项事实支持：____；复核人/日期：____。

## qa_leave_02 · development

问题：今天生病不能上班，最晚什么时候通知？

标准要点：当天10:00前通知直属经理。

必要事实：

- 病假应在当天10:00前通知直属经理

来源证据：

- [leave](../../benchmarks/business_baseline/data/docs/leave.txt)：病假应在当天10:00前通知直属经理

首次回答（answered）：

> 病假应在当天10:00前通知直属经理。

实际引用：

- leave：病假应在当天10:00前通知直属经理

复核：待复核；正确性：____；逐项事实支持：____；复核人/日期：____。

## qa_leave_03 · development

问题：连续请4天病假需不需要证明？

标准要点：需要医疗证明，连续3个自然日及以上需要。

必要事实：

- 连续3个自然日及以上须提供医疗证明

来源证据：

- [leave](../../benchmarks/business_baseline/data/docs/leave.txt)：连续3个自然日及以上须提供医疗证明

首次回答（answered）：

> 需要。连续请病假4天属于连续3个自然日及以上，须提供医疗证明；并应在当天10:00前通知直属经理。

实际引用：

- leave：病假应在当天10:00前通知直属经理，连续3个自然日及以上须提供医疗证明。

复核：待复核；正确性：____；逐项事实支持：____；复核人/日期：____。

## qa_leave_04 · development

问题：已确认的加班调休多久过期，申请要提前多久？

标准要点：确认日起90个自然日有效，提前1个工作日申请。

必要事实：

- 调休有效期为加班确认日起90个自然日
- 调休须提前1个工作日申请

来源证据：

- [leave](../../benchmarks/business_baseline/data/docs/leave.txt)：调休有效期为加班确认日起90个自然日
- [leave](../../benchmarks/business_baseline/data/docs/leave.txt)：调休须提前1个工作日申请

首次回答（answered）：

> 已确认的加班调休自加班确认日起90个自然日过期；调休须提前1个工作日申请。

实际引用：

- leave：调休有效期为加班确认日起90个自然日，调休须提前1个工作日申请。

复核：待复核；正确性：____；逐项事实支持：____；复核人/日期：____。

## qa_remote_01 · development

问题：一个月能远程办公几天？

标准要点：最多4个工作日。

必要事实：

- 远程办公每月最多4个工作日

来源证据：

- [remote](../../benchmarks/business_baseline/data/docs/remote.txt)：远程办公每月最多4个工作日

首次回答（answered）：

> 每月最多可远程办公4个工作日，且须提前1个工作日由直属经理批准。

实际引用：

- remote：远程办公每月最多4个工作日，须提前1个工作日由直属经理批准。

复核：待复核；正确性：____；逐项事实支持：____；复核人/日期：____。

## qa_remote_02 · development

问题：明天想在家办公，今天要找谁批准？

标准要点：提前1个工作日由直属经理批准。

必要事实：

- 须提前1个工作日由直属经理批准

来源证据：

- [remote](../../benchmarks/business_baseline/data/docs/remote.txt)：须提前1个工作日由直属经理批准

首次回答（answered）：

> 明天在家办公需提前1个工作日由直属经理批准；因此今天应找直属经理批准。

实际引用：

- remote：远程办公每月最多4个工作日，须提前1个工作日由直属经理批准。

复核：待复核；正确性：____；逐项事实支持：____；复核人/日期：____。

## qa_remote_03 · development

问题：远程办公有什么在线时间要求？

标准要点：09:30至18:00保持可联系。

必要事实：

- 远程期间保持09:30至18:00可联系

来源证据：

- [remote](../../benchmarks/business_baseline/data/docs/remote.txt)：远程期间保持09:30至18:00可联系

首次回答（answered）：

> 远程办公期间须保持09:30至18:00可联系。

实际引用：

- remote：远程期间保持09:30至18:00可联系。

复核：待复核；正确性：____；逐项事实支持：____；复核人/日期：____。

## qa_remote_04 · development

问题：在酒店公共电脑上连接VPN后可以访问内网吗？

标准要点：不可以；公共电脑不得登录公司系统，须使用公司管理的设备。

必要事实：

- 只能使用公司管理的设备
- 公共电脑不得登录公司系统

来源证据：

- [remote](../../benchmarks/business_baseline/data/docs/remote.txt)：只能使用公司管理的设备
- [remote](../../benchmarks/business_baseline/data/docs/remote.txt)：公共电脑不得登录公司系统

首次回答（answered）：

> 不可以。即使连接了获批准的VPN，公共电脑仍不得登录公司系统；内部系统只能通过公司管理的设备和获批准的VPN访问。

实际引用：

- remote：只能使用公司管理的设备与批准的VPN访问内部系统。公共电脑不得登录公司系统

复核：待复核；正确性：____；逐项事实支持：____；复核人/日期：____。

## qa_security_01 · development

问题：员工个人信息和未公开财务数据算机密吗？

标准要点：两者均属于机密信息。

必要事实：

- 客户数据、员工个人信息和未公开财务数据属于机密信息

来源证据：

- [security](../../benchmarks/business_baseline/data/docs/security.txt)：客户数据、员工个人信息和未公开财务数据属于机密信息

首次回答（answered）：

> 是。员工个人信息和未公开财务数据均属于机密信息。

实际引用：

- security：客户数据、员工个人信息和未公开财务数据属于机密信息。

复核：待复核；正确性：____；逐项事实支持：____；复核人/日期：____。

## qa_security_02 · development

问题：可以把客户名单传给公共AI总结吗？

标准要点：不可以，机密信息不得上传公共AI服务。

必要事实：

- 机密信息不得上传公共AI服务或个人网盘

来源证据：

- [security](../../benchmarks/business_baseline/data/docs/security.txt)：机密信息不得上传公共AI服务或个人网盘

首次回答（answered）：

> 不可以。客户数据属于机密信息，禁止上传至公共AI服务。

实际引用：

- security：客户数据、员工个人信息和未公开财务数据属于机密信息。机密信息不得上传公共AI服务或个人网盘。

复核：待复核；正确性：____；逐项事实支持：____；复核人/日期：____。

## qa_security_03 · development

问题：向外部合作方发送机密材料前要做什么？

标准要点：先脱敏，并取得数据负责人批准。

必要事实：

- 外发机密材料须先脱敏，并取得数据负责人批准

来源证据：

- [security](../../benchmarks/business_baseline/data/docs/security.txt)：外发机密材料须先脱敏，并取得数据负责人批准

首次回答（answered）：

> 向外部合作方发送机密材料前，须先脱敏，并取得数据负责人批准。

实际引用：

- security：外发机密材料须先脱敏，并取得数据负责人批准。

复核：待复核；正确性：____；逐项事实支持：____；复核人/日期：____。

## qa_security_04 · development

问题：发现疑似泄露后多久报告，要不要删除日志？

标准要点：30分钟内报告安全值班渠道，保留证据，不自行删除日志。

必要事实：

- 发现疑似泄露须在30分钟内报告安全值班渠道
- 保留证据，不自行删除日志

来源证据：

- [security](../../benchmarks/business_baseline/data/docs/security.txt)：发现疑似泄露须在30分钟内报告安全值班渠道
- [security](../../benchmarks/business_baseline/data/docs/security.txt)：保留证据，不自行删除日志

首次回答（answered）：

> 发现疑似泄露后，须在30分钟内报告安全值班渠道；应保留证据，不要自行删除日志。

实际引用：

- security：发现疑似泄露须在30分钟内报告安全值班渠道，保留证据，不自行删除日志。

复核：待复核；正确性：____；逐项事实支持：____；复核人/日期：____。

## qa_access_01 · development

问题：申请IT访问要填写哪些字段？

标准要点：目标系统、访问级别、业务理由、有效天数。

必要事实：

- IT访问申请必须填写目标系统、访问级别、业务理由和有效天数

来源证据：

- [access](../../benchmarks/business_baseline/data/docs/access.txt)：IT访问申请必须填写目标系统、访问级别、业务理由和有效天数

首次回答（answered）：

> 申请IT访问必须填写：目标系统、访问级别、业务理由和有效天数（1至90天）。

实际引用：

- access：IT访问申请必须填写目标系统、访问级别、业务理由和有效天数。有效天数范围为1至90天。

复核：待复核；正确性：____；逐项事实支持：____；复核人/日期：____。

## qa_access_02 · development

问题：生产数据库可以申请标准写权限吗？

标准要点：不可以，生产数据库只允许申请只读权限。

必要事实：

- 生产数据库只允许申请只读权限

来源证据：

- [access](../../benchmarks/business_baseline/data/docs/access.txt)：生产数据库只允许申请只读权限

首次回答（answered）：

> 不可以。生产数据库只允许申请只读权限，不能申请标准写权限。

实际引用：

- access：生产数据库只允许申请只读权限。

复核：待复核；正确性：____；逐项事实支持：____；复核人/日期：____。

## qa_access_03 · development

问题：临时访问的有效期可以填120天吗？

标准要点：不可以，有效天数范围1至90天。

必要事实：

- 有效天数范围为1至90天

来源证据：

- [access](../../benchmarks/business_baseline/data/docs/access.txt)：有效天数范围为1至90天

首次回答（answered）：

> 不可以。IT访问申请的有效天数范围为1至90天，120天超出范围。

实际引用：

- access：有效天数范围为1至90天。

复核：待复核；正确性：____；逐项事实支持：____；复核人/日期：____。

## qa_access_04 · development

问题：提交权限申请后就能用了吗，我可以批准自己的申请吗？

标准要点：提交不代表授予；同Workspace系统管理员人工审核，申请人不得自审。

必要事实：

- 同Workspace系统管理员人工审核
- 申请人不得审核自己的申请
- 提交申请不代表权限已经授予

来源证据：

- [access](../../benchmarks/business_baseline/data/docs/access.txt)：同Workspace系统管理员人工审核
- [access](../../benchmarks/business_baseline/data/docs/access.txt)：申请人不得审核自己的申请
- [access](../../benchmarks/business_baseline/data/docs/access.txt)：提交申请不代表权限已经授予

首次回答（answered）：

> 不能。提交权限申请不代表权限已授予，须经同Workspace系统管理员人工审核；申请人不得审核自己的申请。

实际引用：

- access：申请需要同Workspace系统管理员人工审核，申请人不得审核自己的申请。提交申请不代表权限已经授予。

复核：待复核；正确性：____；逐项事实支持：____；复核人/日期：____。

## qa_helpdesk_01 · development

问题：普通IT工单的受理时间是什么？

标准要点：工作日09:00至18:00。

必要事实：

- IT服务台工作日09:00至18:00受理普通工单

来源证据：

- [helpdesk](../../benchmarks/business_baseline/data/docs/helpdesk.txt)：IT服务台工作日09:00至18:00受理普通工单

首次回答（answered）：

> 普通IT工单的受理时间为工作日09:00至18:00。

实际引用：

- helpdesk：IT服务台工作日09:00至18:00受理普通工单。

复核：待复核；正确性：____；逐项事实支持：____；复核人/日期：____。

## qa_helpdesk_02 · development

问题：普通电脑故障多久首次响应，是4个自然小时吗？

标准要点：目标为4个工作小时，并非4个自然小时。

必要事实：

- 普通故障目标首次响应时间为4个工作小时

来源证据：

- [helpdesk](../../benchmarks/business_baseline/data/docs/helpdesk.txt)：普通故障目标首次响应时间为4个工作小时

首次回答（answered）：

> 不是。普通故障的目标首次响应时间为4个工作小时，而非4个自然小时。

实际引用：

- helpdesk：普通故障目标首次响应时间为4个工作小时。

复核：待复核；正确性：____；逐项事实支持：____；复核人/日期：____。

## qa_helpdesk_03 · development

问题：忘了密码，可以把验证码发给客服帮我重置吗？

标准要点：不可发送密码或验证码；走批准的自助重置入口。

必要事实：

- 忘记密码应通过批准的自助重置入口处理
- 不向任何人发送密码或验证码

来源证据：

- [helpdesk](../../benchmarks/business_baseline/data/docs/helpdesk.txt)：忘记密码应通过批准的自助重置入口处理
- [helpdesk](../../benchmarks/business_baseline/data/docs/helpdesk.txt)：不向任何人发送密码或验证码

首次回答（answered）：

> 不可以。忘记密码应通过批准的自助重置入口处理，不要向任何人发送密码或验证码。

实际引用：

- helpdesk：忘记密码应通过批准的自助重置入口处理，不向任何人发送密码或验证码。

复核：待复核；正确性：____；逐项事实支持：____；复核人/日期：____。

## qa_helpdesk_04 · development

问题：公司电脑丢了，是不是开工单等4小时？

标准要点：立即报告IT服务台和安全值班渠道，不等待普通响应。

必要事实：

- 设备丢失须立即报告IT服务台和安全值班渠道
- 不等待普通工单响应

来源证据：

- [helpdesk](../../benchmarks/business_baseline/data/docs/helpdesk.txt)：设备丢失须立即报告IT服务台和安全值班渠道
- [helpdesk](../../benchmarks/business_baseline/data/docs/helpdesk.txt)：不等待普通工单响应

首次请求：ERROR，HTTP 502；无可复核答案。

复核：待复核；正确性：____；逐项事实支持：____；复核人/日期：____。

## qa_onboarding_01 · development

问题：入职第一天找谁确认资料和领设备？

标准要点：由HR确认资料并登记设备领取。

必要事实：

- 新员工入职首日由HR确认资料并登记设备领取

来源证据：

- [onboarding](../../benchmarks/business_baseline/data/docs/onboarding.txt)：新员工入职首日由HR确认资料并登记设备领取

首次回答（answered）：

> 入职第一天由HR确认资料并登记设备领取。

实际引用：

- onboarding：新员工入职首日由HR确认资料并登记设备领取。

复核：待复核；正确性：____；逐项事实支持：____；复核人/日期：____。

## qa_onboarding_02 · development

问题：新员工安全培训和保密承诺要多久完成？

标准要点：入职5个工作日内。

必要事实：

- 入职5个工作日内须完成信息安全培训和保密承诺

来源证据：

- [onboarding](../../benchmarks/business_baseline/data/docs/onboarding.txt)：入职5个工作日内须完成信息安全培训和保密承诺

首次回答（answered）：

> 新员工须在入职5个工作日内完成信息安全培训和保密承诺。

实际引用：

- onboarding：入职5个工作日内须完成信息安全培训和保密承诺。

复核：待复核；正确性：____；逐项事实支持：____；复核人/日期：____。

## qa_onboarding_03 · development

问题：谁负责明确我的岗位职责，账号按什么原则开通？

标准要点：经理明确岗位职责，账号按最小权限申请。

必要事实：

- 经理负责明确岗位职责
- 系统账号按最小权限申请

来源证据：

- [onboarding](../../benchmarks/business_baseline/data/docs/onboarding.txt)：经理负责明确岗位职责
- [onboarding](../../benchmarks/business_baseline/data/docs/onboarding.txt)：系统账号按最小权限申请

首次回答（answered）：

> 经理负责明确岗位职责；系统账号按最小权限原则申请。

实际引用：

- onboarding：经理负责明确岗位职责，系统账号按最小权限申请。

复核：待复核；正确性：____；逐项事实支持：____；复核人/日期：____。

## qa_onboarding_04 · development

问题：还没参加安全培训，可以先申请生产数据库访问吗？

标准要点：不可以，未完成培训不得申请。

必要事实：

- 未完成信息安全培训不得申请生产数据库访问

来源证据：

- [onboarding](../../benchmarks/business_baseline/data/docs/onboarding.txt)：未完成信息安全培训不得申请生产数据库访问

首次回答（answered）：

> 不可以。未完成信息安全培训不得申请生产数据库访问。

实际引用：

- onboarding：未完成信息安全培训不得申请生产数据库访问。

复核：待复核；正确性：____；逐项事实支持：____；复核人/日期：____。

## qa_learning_01 · development

问题：外部培训个人季度预算多少？

标准要点：每季度上限1500元。

必要事实：

- 个人外部培训每季度预算上限为1500元

来源证据：

- [learning](../../benchmarks/business_baseline/data/docs/learning.txt)：个人外部培训每季度预算上限为1500元

首次回答（answered）：

> 个人外部培训每季度预算上限为1500元。

实际引用：

- learning：个人外部培训每季度预算上限为1500元

复核：待复核；正确性：____；逐项事实支持：____；复核人/日期：____。

## qa_learning_02 · development

问题：培训可以先付款再找经理批准吗？

标准要点：须报名缴费前获得直属经理批准。

必要事实：

- 须报名缴费前获得直属经理批准

来源证据：

- [learning](../../benchmarks/business_baseline/data/docs/learning.txt)：须报名缴费前获得直属经理批准

首次回答（answered）：

> 不可以。个人外部培训须在报名缴费前获得直属经理批准。

实际引用：

- learning：个人外部培训每季度预算上限为1500元，须报名缴费前获得直属经理批准。

复核：待复核；正确性：____；逐项事实支持：____；复核人/日期：____。

## qa_learning_03 · development

问题：申请培训要准备哪些资料？

标准要点：课程大纲、费用、与岗位相关的说明。

必要事实：

- 申请材料包含课程大纲、费用和与岗位相关的说明

来源证据：

- [learning](../../benchmarks/business_baseline/data/docs/learning.txt)：申请材料包含课程大纲、费用和与岗位相关的说明

首次回答（answered）：

> 申请个人外部培训需准备：课程大纲、费用说明，以及与岗位相关的说明。

实际引用：

- learning：申请材料包含课程大纲、费用和与岗位相关的说明。

复核：待复核；正确性：____；逐项事实支持：____；复核人/日期：____。

## qa_learning_04 · development

问题：培训结束后何时交分享和凭证，超预算找谁批准？

标准要点：10个工作日内提交；超预算先由部门负责人批准。

必要事实：

- 完成培训后10个工作日内提交学习分享和费用凭证
- 超预算申请须先由部门负责人批准

来源证据：

- [learning](../../benchmarks/business_baseline/data/docs/learning.txt)：完成培训后10个工作日内提交学习分享和费用凭证
- [learning](../../benchmarks/business_baseline/data/docs/learning.txt)：超预算申请须先由部门负责人批准

首次请求：ERROR，HTTP 502；无可复核答案。

复核：待复核；正确性：____；逐项事实支持：____；复核人/日期：____。

## qa_procurement_01 · holdout

问题：买一台2800元显示器需要谁批准？

标准要点：直属经理批准。

必要事实：

- 单笔采购金额不超过3000元由直属经理批准

来源证据：

- [procurement](../../benchmarks/business_baseline/data/docs/procurement.txt)：单笔采购金额不超过3000元由直属经理批准

首次回答（answered）：

> 购买一台2800元显示器，单笔采购金额不超过3000元，需由直属经理在下单前批准。

实际引用：

- procurement：单笔采购金额不超过3000元由直属经理批准。超过3000元须部门负责人批准并提供至少2家供应商报价。采购申请须在下单前完成批准。

复核：待复核；正确性：____；逐项事实支持：____；复核人/日期：____。

## qa_procurement_02 · holdout

问题：采购5000元设备要谁审批，准备几家报价？

标准要点：部门负责人批准，至少2家供应商报价。

必要事实：

- 超过3000元须部门负责人批准并提供至少2家供应商报价

来源证据：

- [procurement](../../benchmarks/business_baseline/data/docs/procurement.txt)：超过3000元须部门负责人批准并提供至少2家供应商报价

首次回答（answered）：

> 采购5000元设备属于超过3000元的单笔采购，须由部门负责人批准，并提供至少2家供应商报价；须在下单前完成批准。

实际引用：

- procurement：超过3000元须部门负责人批准并提供至少2家供应商报价。采购申请须在下单前完成批准。

复核：待复核；正确性：____；逐项事实支持：____；复核人/日期：____。

## qa_procurement_03 · holdout

问题：采购流程能不能先下单后补批准？

标准要点：不能，申请须下单前完成批准。

必要事实：

- 采购申请须在下单前完成批准

来源证据：

- [procurement](../../benchmarks/business_baseline/data/docs/procurement.txt)：采购申请须在下单前完成批准

首次回答（answered）：

> 不能。采购申请须在下单前完成批准。

实际引用：

- procurement：采购申请须在下单前完成批准。

复核：待复核；正确性：____；逐项事实支持：____；复核人/日期：____。

## qa_procurement_04 · holdout

问题：把5000元拆成两单各2500元能省审批吗，普通员工能签合同吗？

标准要点：不得拆单规避审批；只有授权签字人可签署合同。

必要事实：

- 员工不得拆分订单规避审批
- 采购合同只允许授权签字人签署

来源证据：

- [procurement](../../benchmarks/business_baseline/data/docs/procurement.txt)：员工不得拆分订单规避审批
- [procurement](../../benchmarks/business_baseline/data/docs/procurement.txt)：采购合同只允许授权签字人签署

首次回答（answered）：

> 不能。不得拆分订单规避审批；5000元采购属于超过3000元，须部门负责人批准并提供至少2家供应商报价，且须在下单前完成批准。普通员工不能签采购合同，只有授权签字人可以签署。

实际引用：

- procurement：超过3000元须部门负责人批准并提供至少2家供应商报价。采购申请须在下单前完成批准。员工不得拆分订单规避审批；采购合同只允许授权签字人签署。

复核：待复核；正确性：____；逐项事实支持：____；复核人/日期：____。

## qa_incident_01 · holdout

问题：生产服务整体不可用是什么等级，通知谁？

标准要点：P1，立即通知技术值班人员。

必要事实：

- 生产服务整体不可用定义为P1事件
- 须立即通知技术值班人员

来源证据：

- [incident](../../benchmarks/business_baseline/data/docs/incident.txt)：生产服务整体不可用定义为P1事件
- [incident](../../benchmarks/business_baseline/data/docs/incident.txt)：须立即通知技术值班人员

首次回答（answered）：

> 生产服务整体不可用定义为 P1 事件，须立即通知技术值班人员。

实际引用：

- incident：生产服务整体不可用定义为P1事件，须立即通知技术值班人员。

复核：待复核；正确性：____；逐项事实支持：____；复核人/日期：____。

## qa_incident_02 · holdout

问题：P1事故多久更新一次状态？

标准要点：每15分钟。

必要事实：

- P1事件每15分钟更新一次状态

来源证据：

- [incident](../../benchmarks/business_baseline/data/docs/incident.txt)：P1事件每15分钟更新一次状态

首次回答（answered）：

> P1事故每15分钟更新一次状态。

实际引用：

- incident：P1事件每15分钟更新一次状态。

复核：待复核；正确性：____；逐项事实支持：____；复核人/日期：____。

## qa_incident_03 · holdout

问题：服务恢复后多久交复盘，复盘包括什么？

标准要点：2个工作日内；时间线、影响范围、根因、改进责任人。

必要事实：

- 恢复后2个工作日内提交复盘
- 包含时间线、影响范围、根因和改进责任人

来源证据：

- [incident](../../benchmarks/business_baseline/data/docs/incident.txt)：恢复后2个工作日内提交复盘
- [incident](../../benchmarks/business_baseline/data/docs/incident.txt)：包含时间线、影响范围、根因和改进责任人

首次回答（answered）：

> 服务恢复后2个工作日内提交复盘。复盘应包含：时间线、影响范围、根因和改进责任人。

实际引用：

- incident：恢复后2个工作日内提交复盘，包含时间线、影响范围、根因和改进责任人。

复核：待复核；正确性：____；逐项事实支持：____；复核人/日期：____。

## qa_incident_04 · holdout

问题：排障时可否直接修改生产数据？

标准要点：未经授权不得修改。

必要事实：

- 未经授权不得在排障中修改生产数据

来源证据：

- [incident](../../benchmarks/business_baseline/data/docs/incident.txt)：未经授权不得在排障中修改生产数据

首次回答（answered）：

> 不可直接修改。排障中未经授权不得修改生产数据。

实际引用：

- incident：未经授权不得在排障中修改生产数据。

复核：待复核；正确性：____；逐项事实支持：____；复核人/日期：____。

## qa_assets_01 · holdout

问题：可以把公司笔记本借给家人吗？

标准要点：不可以，不得转借非公司人员。

必要事实：

- 公司设备仅供工作用途
- 不得转借非公司人员

来源证据：

- [assets](../../benchmarks/business_baseline/data/docs/assets.txt)：公司设备仅供工作用途
- [assets](../../benchmarks/business_baseline/data/docs/assets.txt)：不得转借非公司人员

首次回答（answered）：

> 不可以。公司设备仅供工作用途，不得转借给非公司人员；家人属于非公司人员。

实际引用：

- assets：公司设备仅供工作用途，不得转借非公司人员。

复核：待复核；正确性：____；逐项事实支持：____；复核人/日期：____。

## qa_assets_02 · holdout

问题：笔记本故障可以自己拆开修吗？

标准要点：不得自行拆机，应报IT服务台。

必要事实：

- 设备故障应报IT服务台，不得自行拆机

来源证据：

- [assets](../../benchmarks/business_baseline/data/docs/assets.txt)：设备故障应报IT服务台，不得自行拆机

首次回答（answered）：

> 不可以。公司设备发生故障应报IT服务台，不得自行拆机。

实际引用：

- assets：设备故障应报IT服务台，不得自行拆机。

复核：待复核；正确性：____；逐项事实支持：____；复核人/日期：____。

## qa_assets_03 · holdout

问题：离职设备什么时候归还，谁确认？

标准要点：最后工作日归还，由IT确认交接。

必要事实：

- 员工离职须在最后工作日归还设备并由IT确认交接

来源证据：

- [assets](../../benchmarks/business_baseline/data/docs/assets.txt)：员工离职须在最后工作日归还设备并由IT确认交接

首次回答（answered）：

> 员工离职须在最后工作日归还设备，并由IT确认交接。

实际引用：

- assets：员工离职须在最后工作日归还设备并由IT确认交接。

复核：待复核；正确性：____；逐项事实支持：____；复核人/日期：____。

## qa_assets_04 · holdout

问题：设备遗失先报告哪里？

标准要点：立即报告IT服务台和安全值班渠道。

必要事实：

- 设备遗失须立即报告IT服务台和安全值班渠道

来源证据：

- [assets](../../benchmarks/business_baseline/data/docs/assets.txt)：设备遗失须立即报告IT服务台和安全值班渠道

首次回答（answered）：

> 设备遗失须立即报告IT服务台和安全值班渠道。

实际引用：

- assets：设备遗失须立即报告IT服务台和安全值班渠道。

复核：待复核；正确性：____；逐项事实支持：____；复核人/日期：____。

## qa_meetings_01 · holdout

问题：会议室普通预约最长多久，超时找谁？

标准要点：最长2小时，超时由行政人员确认。

必要事实：

- 会议室预约最长为2小时，超时须行政人员确认

来源证据：

- [meetings](../../benchmarks/business_baseline/data/docs/meetings.txt)：会议室预约最长为2小时，超时须行政人员确认

首次回答（answered）：

> 会议室普通预约最长为2小时；如需超时，须由行政人员确认。

实际引用：

- meetings：会议室预约最长为2小时，超时须行政人员确认。

复核：待复核；正确性：____；逐项事实支持：____；复核人/日期：____。

## qa_meetings_02 · holdout

问题：会议没人签到多久会释放？

标准要点：开始后15分钟。

必要事实：

- 会议开始后15分钟无人签到将释放预约

来源证据：

- [meetings](../../benchmarks/business_baseline/data/docs/meetings.txt)：会议开始后15分钟无人签到将释放预约

首次回答（answered）：

> 会议开始后15分钟无人签到，将释放预约。

实际引用：

- meetings：会议开始后15分钟无人签到将释放预约。

复核：待复核；正确性：____；逐项事实支持：____；复核人/日期：____。

## qa_meetings_03 · holdout

问题：客户来访要提前多久登记，由谁陪同？

标准要点：提前1个工作日登记，接待员工全程陪同。

必要事实：

- 外部访客须提前1个工作日登记，由接待员工全程陪同

来源证据：

- [meetings](../../benchmarks/business_baseline/data/docs/meetings.txt)：外部访客须提前1个工作日登记，由接待员工全程陪同

首次回答（answered）：

> 外部访客须提前1个工作日登记，并由接待员工全程陪同。

实际引用：

- meetings：外部访客须提前1个工作日登记，由接待员工全程陪同。

复核：待复核；正确性：____；逐项事实支持：____；复核人/日期：____。

## qa_meetings_04 · holdout

问题：访客可以接内网网线或自由进入办公区吗？

标准要点：不可以连接内部有线网络，也不得进入未批准区域。

必要事实：

- 访客不得进入未获批准的办公区域
- 不得连接内部有线网络

来源证据：

- [meetings](../../benchmarks/business_baseline/data/docs/meetings.txt)：访客不得进入未获批准的办公区域
- [meetings](../../benchmarks/business_baseline/data/docs/meetings.txt)：不得连接内部有线网络

首次回答（answered）：

> 不可以。访客不得连接内部有线网络，也不得进入未经批准的办公区域；外部访客须提前1个工作日登记，并由接待员工全程陪同。

实际引用：

- meetings：外部访客须提前1个工作日登记，由接待员工全程陪同。访客不得进入未获批准的办公区域，也不得连接内部有线网络。

复核：待复核；正确性：____；逐项事实支持：____；复核人/日期：____。

## 无依据问题：首次 API 结果

下列8题均返回 unsupported、无答案和引用；这是结构性拒答观察。

| ID | 问题 | 结果 |
|---|---|---|
| refusal_missing_policy_01 | 公司股票期权的行权价是多少？ | unsupported |
| refusal_missing_policy_02 | 公司海外医疗保险的报销比例是多少？ | unsupported |
| refusal_missing_policy_03 | 公司巴黎办公室的停车费标准是多少？ | unsupported |
| refusal_missing_policy_04 | 公司养老金补贴按什么比例发放？ | unsupported |
| refusal_missing_benefit_01 | 公司托育津贴每月金额是多少？ | unsupported |
| refusal_missing_benefit_02 | 公司购房补贴的申请条件是什么？ | unsupported |
| refusal_missing_benefit_03 | 公司长期服务奖的奖金是多少？ | unsupported |
| refusal_missing_benefit_04 | 公司离职后的医疗保险续保多久？ | unsupported |
