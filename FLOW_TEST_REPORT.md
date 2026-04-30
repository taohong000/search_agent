# 完整流程测试报告

测试时间：2026-04-28 14:43:50 +08:00

## 结论

- 单元测试通过：16/16。
- CLI 完整流程通过。
- 本次问题触发了本地资料检索、SerpAPI 网络搜索、Jina Reader 网页抓取、Crawl4AI 兜底抓取、PDF 链接识别和阿里百炼模型回答。
- PDF 链接当前按设计标记为 `pdf_unsupported`，未解析正文。

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
test_web_fetch_content_is_passed_to_llm_after_search (tests.test_agent_loop.SearchAgentTests.test_web_fetch_content_is_passed_to_llm_after_search) ... ok
test_environment_values_override_config_file (tests.test_config.SettingsTests.test_environment_values_override_config_file) ... ok
test_reads_keys_from_environment_without_requiring_values_in_code (tests.test_config.SettingsTests.test_reads_keys_from_environment_without_requiring_values_in_code) ... ok
test_reads_values_from_toml_config_file (tests.test_config.SettingsTests.test_reads_values_from_toml_config_file) ... ok
test_search_matches_path_heading_and_body_with_scores (tests.test_local_search.LocalSearchEngineTests.test_search_matches_path_heading_and_body_with_scores) ... ok
test_search_returns_empty_for_unmatched_terms (tests.test_local_search.LocalSearchEngineTests.test_search_returns_empty_for_unmatched_terms) ... ok
test_specific_policy_phrase_beats_generic_many_term_match (tests.test_local_search.LocalSearchEngineTests.test_specific_policy_phrase_beats_generic_many_term_match) ... ok
test_expands_social_insurance_fee_question (tests.test_query_planner.QueryPlannerTests.test_expands_social_insurance_fee_question) ... ok
test_expands_unemployment_social_security_question (tests.test_query_planner.QueryPlannerTests.test_expands_unemployment_social_security_question) ... ok
test_next_round_adds_missing_policy_terms (tests.test_query_planner.QueryPlannerTests.test_next_round_adds_missing_policy_terms) ... ok
test_falls_back_to_crawl4ai_when_jina_content_is_too_short (tests.test_web_fetch.WebFetchRouterTests.test_falls_back_to_crawl4ai_when_jina_content_is_too_short) ... ok
test_pdf_is_marked_for_pdf_parser_without_browser_fetch (tests.test_web_fetch.WebFetchRouterTests.test_pdf_is_marked_for_pdf_parser_without_browser_fetch) ... ok
test_quality_rejects_precondition_failed_text (tests.test_web_fetch.WebFetchRouterTests.test_quality_rejects_precondition_failed_text) ... ok
test_uses_jina_when_quality_is_good (tests.test_web_fetch.WebFetchRouterTests.test_uses_jina_when_quality_is_good) ... ok

----------------------------------------------------------------------
Ran 16 tests in 0.101s

OK
```

## 测试 2：CLI 完整流程

命令：

```powershell
python -m search_agent ask "现在上海灵活就业社会保险费缴费怎么办理" --config search-agent.toml --web --show-sources
```

退出码：0

输出：

```text
根据现有资料，本地资料中未直接说明上海灵活就业社会保险费缴费的办理流程，仅涉及养老金领取条件（本地1、本地6）和扣款失败处理（本地8）。以下基于联网资料（搜索结果）提供办理方式：

### 办理渠道
1. **线上渠道**
   - **“随申办”小程序**：微信扫码或长按识别“随申办”小程序，进入上海市人力资源和社会保障公共服务目录，可办理灵活就业登记、灵活就业人员社保缴费等业务（来源：搜索3）。
   - **“社保云缴费”小程序**：微信扫码或长按识别，可办理部分城市的灵活就业人员个体社保缴费（来源：搜索3）。
   - **上海市税务局官网**：个人完成参保登记后，可通过上海市税务局相关系统申报缴费，系统自动带出费额，确认后缴费（来源：搜索2）。

2. **线下渠道**
   - **社区事务受理服务中心窗口**：可办理参保登记及缴费（来源：搜索1、搜索5）。
   - **指定银行**：工商银行、农业银行、浦发银行等银行网点可办理缴费（来源：搜索1、搜索5）。
   - **税务局办税服务厅**：例如上海市杨浦区税务局第一税务所办税服务厅窗口（来源：网页1）。

### 注意事项
- 灵活就业人员一般按月缴纳社保费（来源：搜索2）。
- 若扣款失败，可参考本地资料【便民】灵活就业人员社保费扣款失败，什么原因？怎么办？中的原因（如银行账户异常）并联系相关部门处理（来源：本地8）。

### 参考来源
- 联网资料：搜索1（一网通办）、搜索2（上海市税务局PDF）、搜索3（m12333.cn）、搜索5（一网通办）、网页1（一网通办杨浦区页面）。
- 本地资料：本地8（扣款失败处理）。

本地来源:
- 【案例】以灵活就业人员身份连续参保缴费，达到什么条件时才可以领取城镇职工基本养老金？ | D:\查询机器人资料\本地数据\公众号\上海社保公众号\【案例】以灵活就业人员身份连续参保缴费，达到什么条件时才可以领取城镇职工基本养老金？.md | 命中: 上海, 社保, 社会保险, 参保, 参保缴费, 灵活就业, 养老保险
- 社会保险参保缴费问答(一) | D:\查询机器人资料\本地数据\公众号\上海社保公众号\社会保险参保缴费问答（一）.md | 命中: 上海, 社会保险费, 社保, 社会保险, 参保, 参保缴费, 个人缴费
- 本市延长阶段性减免企业社会保险费政策实施期限 | D:\查询机器人资料\本地数据\公众号\上海社保公众号\本市延长阶段性减免企业社会保险费政策实施期限.md | 命中: 上海, 社会保险费, 社保, 社会保险, 参保, 灵活就业, 个人缴费, 养老保险
- HR关心的 | 阶段性减免企业社会保险费划型结果查询热点问题解答! | D:\查询机器人资料\本地数据\公众号\上海社保公众号\HR关心的︱阶段性减免企业社会保险费划型结果查询热点问题解答！.md | 命中: 上海, 社会保险费, 社保, 社会保险, 参保, 灵活就业, 个人缴费, 养老保险
- 社会保险参保缴费问答（二） | D:\查询机器人资料\本地数据\公众号\上海社保公众号\社会保险参保缴费问答（二）.md | 命中: 上海, 社会保险费, 社保, 社会保险, 参保, 参保缴费
- 【案例】按灵活就业办法参保后，达到什么条件时才可以领取城镇职工基本养老金？ | D:\查询机器人资料\本地数据\公众号\上海社保公众号\【案例】按灵活就业办法参保后，达到什么条件时才可以领取城镇职工基本养老金？.md | 命中: 上海, 社保, 参保, 参保缴费, 灵活就业, 养老保险
- 定了! 5月份社会保险费缴纳时间安排新鲜出炉! | D:\查询机器人资料\本地数据\公众号\上海社保公众号\定了！5月份社会保险费缴纳时间安排新鲜出炉！.md | 命中: 上海, 社会保险费, 社保, 社会保险, 参保
- 【便民】灵活就业人员社保费扣款失败，什么原因？怎么办？ | D:\查询机器人资料\本地数据\公众号\上海社保公众号\【便民】灵活就业人员社保费扣款失败，什么原因？怎么办？.md | 命中: 上海, 社保, 灵活就业, 个人缴费

网络来源:
- 灵活就业人员社会保险费缴费 - 一网通办 | https://zwdt.sh.gov.cn/govPortals/bsfw/item/bb5b8d6d-f747-4ae7-8423-b0ea42093055
- 上海市税务局社会保险费缴费操作指南（适用个人） | https://shanghai.chinatax.gov.cn/zcfw/zcfgk/sbf/202206/P020220630550461189492.pdf
- 上海市灵活就业人员(个体户/自由职业者)社保缴费 | https://m12333.cn/gerenjiaofei/shanghai.aspx
- 哪些人员可以按灵活就业人员参保？灵活就业人员每个月缴 ... | https://www.shanghai.gov.cn/xbhygq/20230516/8d0da5bb98b54817b5d0c12c74ecc1cf.html
- 灵活就业人员社会保险费缴费 - 一网通办- 上海市人民政府 | https://zwdt.sh.gov.cn/govPortals/bsfw/item/f3e876ba-3866-42d1-9032-96a2e438c213

网页正文:
- 一网通办 | jina | ok | https://zwdt.sh.gov.cn/govPortals/bsfw/item/bb5b8d6d-f747-4ae7-8423-b0ea42093055
- https://shanghai.chinatax.gov.cn/zcfw/zcfgk/sbf/202206/P020220630550461189492.pdf | pdf | pdf_unsupported | https://shanghai.chinatax.gov.cn/zcfw/zcfgk/sbf/202206/P020220630550461189492.pdf
- 上海市 灵活就业人员/个体社保缴费 | crawl4ai | ok | https://m12333.cn/gerenjiaofei/shanghai.aspx
```

## 观察

- 流程中 `一网通办` 页面由 Jina Reader 成功抓取。
- `m12333` 页面由 Crawl4AI 成功兜底抓取。
- 税务 PDF 被识别但未解析，符合当前设计。
- 回答质量可继续改进：模型仍较多引用搜索摘要而非网页正文，可在后续调整 prompt 权重，让 `网页正文` 优先于 `搜索结果`。
