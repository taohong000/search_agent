# 爬虫入库过滤逻辑建议

## 目标

爬虫系统负责数据清洗、固定元数据生成和入库初判，避免无效内容污染本地知识库。

过滤逻辑不追求一次性判断完美。对于证据不足的内容，应标记为不可直接回答或需要人工复核。

## 1. URL 与来源过滤

优先保留：

- 政府官网政策栏目
- 社保、公积金、人社、医保等官方来源
- 官方公众号中的政策发布、通知公告、办事指南、政策问答
- 有明确标题、发布日期和正文的文章

过滤或降权：

- 登录页、列表页、搜索页、分页页
- 图片预览页、附件下载页本身
- 活动宣传、招聘广告、会议新闻、培训通知
- 领导动态、媒体转载、普通新闻稿
- 正文过短且无附件、无政策信息的页面

建议输出：

```yaml
crawl_filter:
  passed: true
  reason: "official_policy_channel"
  source_trust: "high"
```

## 2. 正文清洗

清洗掉：

- 导航栏、页脚、版权声明
- 分享按钮、阅读量、点赞、二维码提示
- “点击蓝字关注我们”等公众号固定文案
- 重复标题、重复发布日期
- 无业务含义的推广段落
- 与政策无关的图片说明

保留：

- 标题
- 发布机构
- 发布日期
- 正文政策内容
- 表格
- 附件列表
- 原文链接
- 有业务含义的问答内容

建议质量字段：

```yaml
content_quality:
  text_length: 2840
  has_title: true
  has_publish_date: true
  has_policy_terms: true
  has_table: true
  quality: "usable"
```

## 3. 文档类型判定

建议枚举：

```yaml
doc_kind:
  - policy_document
  - policy_notice
  - service_guide
  - faq
  - interpretation
  - news
  - activity
  - noise
  - unknown
```

入库建议：

| 类型 | 入库 | 导出给 agent | 说明 |
|---|---|---|---|
| policy_document | 是 | 是 | 正式政策文件 |
| policy_notice | 是 | 是 | 通知公告 |
| service_guide | 是 | 是 | 办事指南 |
| faq | 是 | 视情况 | 问答类，权威性低于正式政策 |
| interpretation | 是 | 视情况 | 政策解读 |
| news | 是 | 否 | 普通新闻动态 |
| activity | 否 | 否 | 活动宣传 |
| noise | 否 | 否 | 噪声 |
| unknown | 是 | 否 | 等待人工复核 |

建议字段：

```yaml
agent_eligible: true
eligibility_reason: "包含办理条件、缴费基数、缴存比例等可回答用户问题的信息"
```

## 4. 业务线与事项候选

爬虫系统可以生成候选项，但不写最终业务/事项索引。

示例：

```yaml
business_candidates:
  - name: "公积金"
    confidence: 0.94
    evidence: ["住房公积金", "缴存基数", "月缴存额"]

service_item_candidates:
  - name: "缴存基数调整"
    confidence: 0.91
  - name: "缴存比例调整"
    confidence: 0.86
```

最终字段由本地资料系统维护：

```yaml
business_lines:
service_items:
```

## 5. 版本候选判定

优先识别以下信号：

- 标题包含年度，例如 `2025年度`
- 标题包含 `调整`、`修订`、`废止`、`继续执行`、`失效`
- 同来源、同主题、不同年份
- 正文包含 `自 xx 起施行`
- 正文包含 `原 xx 同时废止`
- `policy_change_log` 中存在新旧文档关系

建议输出：

```yaml
version_detection:
  version_candidate: true
  version_group_key: "上海市住房公积金年度缴存基数比例月缴存额上下限调整"
  version_no: 2025
  status_guess: "current"
  confidence: 0.88
  evidence: "标题包含2025年度，主题为缴存基数、比例、月缴存额上下限"
```

证据不足时：

```yaml
version_detection:
  version_candidate: true
  status_guess: "unknown"
  confidence: 0.42
  unable_reason: "缺少明确有效期和替代关系"
```

## 6. 入库决策

每篇文档最终输出统一决策。

```yaml
ingest_decision:
  store_in_db: true
  export_markdown: true
  agent_eligible: true
  needs_human_review: false
  reason: "官方来源，政策通知类，正文质量可用"
```

常见决策：

```yaml
# 正常入库并导出
store_in_db: true
export_markdown: true
agent_eligible: true

# 入库但不导出给 agent
store_in_db: true
export_markdown: false
agent_eligible: false

# 证据不足，等待人工
store_in_db: true
export_markdown: false
agent_eligible: false
needs_human_review: true

# 明确噪声
store_in_db: false
export_markdown: false
agent_eligible: false
```

## 7. 推荐处理顺序

1. 规则过滤明显噪声。
2. 结构化解析标题、日期、来源和正文。
3. 清洗正文并生成 normalized Markdown。
4. 规则判断文档类型和质量。
5. 生成业务线、事项候选。
6. 判断是否可能进入版本索引。
7. 对低置信度样本使用 LLM。
8. 对 `needs_human_review = true` 的内容进行人工复核。

## 原则

- 爬虫系统负责固定元数据和入库初判。
- 本地资料系统负责最终业务线和事项索引。
- 版本索引来自数据库映射。
- 无法判断时不要强行回答，保留人工客服兜底路径。
