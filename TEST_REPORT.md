# 测试报告

测试时间：2026-04-27 16:31:54 +08:00

## 结论

- 单元测试通过：10/10。
- 配置文件 `search-agent.toml` 可被 CLI 正常读取。
- 已确认配置后的阿里百炼模型调用链路可用：本地检索结果被模型组织成自然语言回答。
- 已确认 SerpAPI 联网调用链路可用：`--web` 模式返回网络来源。
- 质量观察：联网测试成功返回来源，但当前搜索结果没有直接给出“上海灵活就业社保最低缴费金额”，模型按证据不足进行了保守回答。

## 测试 1：单元测试

命令：

```powershell
python -m unittest discover -v
```

退出码：0

输出：

```text
test_auto_policy_uses_web_for_current_question (tests.test_agent_loop.SearchAgentTests.test_auto_policy_uses_web_for_current_question) ... ok
test_no_web_policy_skips_network_even_for_current_question (tests.test_agent_loop.SearchAgentTests.test_no_web_policy_skips_network_even_for_current_question) ... ok
test_environment_values_override_config_file (tests.test_config.SettingsTests.test_environment_values_override_config_file) ... ok
test_reads_keys_from_environment_without_requiring_values_in_code (tests.test_config.SettingsTests.test_reads_keys_from_environment_without_requiring_values_in_code) ... ok
test_reads_values_from_toml_config_file (tests.test_config.SettingsTests.test_reads_values_from_toml_config_file) ... ok
test_search_matches_path_heading_and_body_with_scores (tests.test_local_search.LocalSearchEngineTests.test_search_matches_path_heading_and_body_with_scores) ... ok
test_search_returns_empty_for_unmatched_terms (tests.test_local_search.LocalSearchEngineTests.test_search_returns_empty_for_unmatched_terms) ... ok
test_specific_policy_phrase_beats_generic_many_term_match (tests.test_local_search.LocalSearchEngineTests.test_specific_policy_phrase_beats_generic_many_term_match) ... ok
test_expands_unemployment_social_security_question (tests.test_query_planner.QueryPlannerTests.test_expands_unemployment_social_security_question) ... ok
test_next_round_adds_missing_policy_terms (tests.test_query_planner.QueryPlannerTests.test_next_round_adds_missing_policy_terms) ... ok

----------------------------------------------------------------------
Ran 10 tests in 0.074s

OK
```

## 测试 2：本地资料检索 + 模型回答

命令：

```powershell
python -m search_agent ask "上海公积金如何缴存" --config search-agent.toml --no-web --show-sources
```

退出码：0

输出：

```text
根据现有本地资料，上海公积金的缴存主要通过单位进行年度基数调整和按月汇缴完成。以下是基于资料的关键信息：

1. **缴存基数调整时间**：每年7月启动（如2024年度调整于2024年7月开始，2025年度调整于2025年7月启动）。单位需在末次缴存月份为6月后办理基数调整（来源：[本地1]、[本地2]）。

2. **办理渠道**：可通过“上海公积金”微信公众号或上海“一网通办”平台（“税费综合申报”栏目）办理基数调整和缴存（来源：[本地1]、[本地5]）。

3. **缴存比例**：单位在基数调整时选择缴存比例，同一缴存年度内不能更改（来源：[本地7]）。如需降低缴存比例或缓缴，需向各区管理部提交材料，经市公积金中心审批（审批时限不超过10个工作日）（来源：[本地7]）。

4. **月缴存额计算**：根据职工上一年月平均工资和缴存比例计算（来源：[本地6]）。

**注意**：以上信息主要围绕基数调整流程，未提供完整的日常缴存操作步骤（如首次开户、汇缴扣款等）。如需更详细的缴存指南（如新单位开户、个人账户转移等），建议直接咨询上海公积金官方渠道或查阅其官网。

**参考来源**：
- [本地1] 2024年度住房公积金缴存基数调整操作温馨提示（上海公积金公众号，2024年6月30日）
- [本地2] 2025年度住房公积金缴存基数调整温馨提示（上海公积金公众号，2025年6月30日）
- [本地5] 进一步了解一网通办平台办理2021年度住房公积金基数调整（上海公积金公众号，2021年8月31日）
- [本地6] 六、住房公积金月缴存额如何计算？（上海公积金公众号，2019年2月14日）
- [本地7] 《关于调整2018年度上海市住房公积金缴存比例的补充通知》的问答（上海公积金公众号）

本地来源:
- 2024年度住房公积金缴存基数调整操作温馨提示 | D:\查询机器人资料\本地数据\公众号\上海公积金公众号\2024年度住房公积金缴存基数调整操作温馨提示.md | 命中: 上海, 公积金, 住房公积金, 缴存, 基数调整
- 2025年度住房公积金缴存基数调整温馨提示 | D:\查询机器人资料\本地数据\公众号\上海公积金公众号\2025年度住房公积金缴存基数调整温馨提示.md | 命中: 上海, 公积金, 住房公积金, 缴存, 基数调整
- 问答 | 2018年度住房公积金基数调整权威解答 | D:\查询机器人资料\本地数据\公众号\上海公积金公众号\问答丨2018年度住房公积金基数调整权威解答.md | 命中: 上海, 公积金, 住房公积金, 缴存, 基数调整
- 关于今年本市社保费年度缴费工资申报及住房公积金年度基数调整的 | D:\查询机器人资料\本地数据\公众号\上海公积金公众号\关于今年本市社保费年度缴费工资申报及住房公积金年度基数调整的温馨提示.md | 命中: 上海, 公积金, 住房公积金, 缴存, 基数调整
- 进一步了解一网通办平台办理2021年度住房公积金基数调整 | D:\查询机器人资料\本地数据\公众号\上海公积金公众号\进一步了解一网通办平台办理2021年度住房公积金基数调整.md | 命中: 上海, 公积金, 住房公积金, 缴存, 基数调整
- 六、住房公积金月缴存额如何计算？ | D:\查询机器人资料\本地数据\公众号\上海公积金公众号\权威丨2019年度住房公积金基数调整问题解答.md | 命中: 上海, 公积金, 住房公积金, 缴存, 基数调整
- 《关于调整2018年度上海市住房公积金缴存比例的补充通知》的问答 | D:\查询机器人资料\本地数据\公众号\上海公积金公众号\《关于调整2018年度上海市住房公积金缴存比例的补充通知》的问答.md | 命中: 上海, 公积金, 住房公积金, 缴存, 基数调整
- 通过“一网通办”平台提前申报2022年度住房公积金缴存基数业务问答 | D:\查询机器人资料\本地数据\公众号\上海公积金公众号\通过“一网通办”平台提前申报2022年度住房公积金缴存基数业务问答.md | 命中: 上海, 公积金, 住房公积金, 缴存, 基数调整

网络来源:
```

## 测试 3：强制联网检索 + 模型回答

命令：

```powershell
python -m search_agent ask "现在上海灵活就业社保最低交多少钱" --config search-agent.toml --web --show-sources
```

退出码：0

输出：

```text
根据现有资料，**无法确定上海灵活就业社保当前的最低缴费金额**。本地资料均为2016-2020年的历史内容，未包含具体缴费标准；联网资料仅提供查询入口和操作指南，未列出金额数据。建议您通过以下官方渠道获取最新信息：

- 拨打税务服务热线 **021-12366**（来源：[网络5]）
- 登录“随申办”小程序或“一网通办”平台查询（来源：[网络1]、[网络5]）

参考来源：
[网络1] 上海社保查询_养老保险个人账户明细查询
[网络5] 灵活就业人员社会保险费缴费 - 一网通办

本地来源:
- 社会保险参保缴费问答（二） | D:\查询机器人资料\本地数据\公众号\上海社保公众号\社会保险参保缴费问答（二）.md | 命中: 上海, 社保, 社会保险, 参保, 参保缴费, 缴费
- 社会保险参保缴费问答(一) | D:\查询机器人资料\本地数据\公众号\上海社保公众号\社会保险参保缴费问答（一）.md | 命中: 上海, 社保, 社会保险, 参保, 参保缴费, 缴费
- 实用! 简单三步, 教您打印职工参保缴费情况 | D:\查询机器人资料\本地数据\公众号\上海社保公众号\实用！简单三步，教您打印职工参保缴费情况.md | 命中: 上海, 社保, 社会保险, 参保, 参保缴费, 养老保险, 缴费
- 【案例】以灵活就业人员身份连续参保缴费，达到什么条件时才可以领取城镇职工基本养老金？ | D:\查询机器人资料\本地数据\公众号\上海社保公众号\【案例】以灵活就业人员身份连续参保缴费，达到什么条件时才可以领取城镇职工基本养老金？.md | 命中: 上海, 社保, 社会保险, 参保, 参保缴费, 养老保险, 缴费
- 【缴费】疫情期间如何为职工办理参保缴费? | D:\查询机器人资料\本地数据\公众号\上海社保公众号\【缴费】疫情期间如何为职工办理参保缴费？.md | 命中: 上海, 社保, 参保, 参保缴费, 缴费
- 【参保】贫困人员参保缴费提示 | D:\查询机器人资料\本地数据\公众号\上海社保公众号\【参保】贫困人员参保缴费提示.md | 命中: 上海, 社保, 参保, 参保缴费, 缴费
- 【课堂】如何办理跨省转移接续养老保险关系？ | D:\查询机器人资料\本地数据\公众号\上海社保公众号\【课堂】如何办理跨省转移接续养老保险关系？.md | 命中: 上海, 社保, 参保, 参保缴费, 养老保险, 缴费
- 步骤1 | 步骤2 | 步骤3 | D:\查询机器人资料\本地数据\公众号\上海社保公众号\“五证合一”新办企业如何在网上为职工办理参保缴费手续？.md | 命中: 上海, 社保, 社会保险, 参保, 参保缴费, 交, 缴费

网络来源:
- 上海社保查询_养老保险个人账户明细查询 | https://m12333.cn/shebao/shanghai.aspx
- 个人社保参保证明查询打印 - 社保查询 | https://si.12333.gov.cn/184996.jhtml
- 上海市税务局社会保险费缴费操作指南（适用个人） | https://shanghai.chinatax.gov.cn/zcfw/zcfgk/sbf/202206/P020220630550461189492.pdf
- 上海市个人社保（养老/医保）缴费 | https://m12333.cn/pay/shanghai.aspx
- 灵活就业人员社会保险费缴费 - 一网通办 | https://zwdt.sh.gov.cn/govPortals/bsfw/item/bb5b8d6d-f747-4ae7-8423-b0ea42093055
```

## 后续建议

- 联网搜索建议增加官方域名优先级，例如 `rsj.sh.gov.cn`、`ybj.sh.gov.cn`、`shanghai.chinatax.gov.cn`、`zwdt.sh.gov.cn`。
- 对“多少钱、比例、基数、标准”这类问题，可以自动追加搜索词“2025年度 社保缴费基数 上下限 官方”等，提高精确数字命中率。
