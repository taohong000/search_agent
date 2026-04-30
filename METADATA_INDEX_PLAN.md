# Markdown 元数据与索引分层计划

## 目标

将政策资料的元数据、业务索引、事项索引和版本索引分层维护，降低数据库耦合，同时让本地 Markdown 知识库更适合 agent 检索、证据展示和人工维护。

## 索引分层

### 1. 固定元数据

固定元数据由爬虫系统生成 Markdown 时写入 front matter。

典型字段：

- `policy_document_id`
- `source_url`
- `source_name`
- `source_type`
- `city_code`
- `title`
- `publish_date`
- `effective_date`

这部分来自爬虫和数据库，不建议人工手动维护。

### 2. 业务线与事项索引

业务线和事项索引在文档进入本地资料系统后维护。

维护方式：

- AI 初步补充
- 人工校正
- 不回写数据库
- 写入 Markdown front matter

典型字段：

- `primary_business_line`
- `business_lines`
- `service_items`
- `doc_kind`
- `agent_eligible`
- `index_confidence`
- `index_reason`

### 3. 版本索引

版本索引单独生成版本目录 Markdown。

建议目录：

```text
本地数据/
  _indexes/
    version/
      公积金/
      社保/
      医保/
```

版本索引来自数据库中的 `policy_document` 和 `policy_change_log` 映射关系。

原文 Markdown 只保留轻量版本字段：

- `version_group_key`
- `version_no`
- `version_status`

完整版本链放在版本索引 Markdown 中。

## 原文 Markdown front matter 示例

```yaml
---
policy_document_id: 228051
source_url: "https://..."
source_name: "上海住房公积金网"
source_type: "website"
city_code: "310000"

title: "关于调整2025年度上海市住房公积金缴存基数、比例以及月缴存额上下限的通知"
publish_date: "2025-06-25"
effective_date: "2025-07-01"
normalized_text_path: "output/shzfgjj/markdown/..."
content_hash: "..."

primary_business_line: "公积金"
business_lines: ["公积金"]
service_items: ["缴存基数调整", "缴存比例调整", "月缴存额上下限"]
doc_kind: "policy_notice"
agent_eligible: true
index_confidence: 0.92
index_reason: "标题和正文命中缴存基数、比例、月缴存额上下限"

version_group_key: "上海市住房公积金年度缴存基数比例月缴存额上下限调整"
version_no: 2025
version_status: "current"
---
```

## 版本索引 Markdown 示例

```yaml
---
index_type: "version_index"
business_line: "公积金"
service_item: "缴存基数调整"
version_group_key: "上海市住房公积金年度缴存基数比例月缴存额上下限调整"
current_policy_document_id: 228051
current_version_no: 2025
source: "policy_document + policy_change_log"
updated_at: "2026-04-29"
confidence: 0.94
---
```

```md
# 上海市住房公积金年度缴存基数比例月缴存额上下限调整

## 当前有效版本

| 版本 | 文档ID | 标题 | 有效期 | 原文 |
|---|---:|---|---|---|
| 2025 | 228051 | 关于调整2025年度... | 2025-07-01 至 2026-06-30 | source_url |

## 历史版本

| 版本 | 状态 | 文档ID | 标题 | 替代关系 |
|---|---|---:|---|---|
| 2024 | superseded | 221903 | 关于调整2024年度... | 被 2025 替代 |
```

## Agent 使用方式

agent 读取 Markdown 时应：

1. 优先解析 front matter。
2. 将 YAML 从正文检索文本中剥离。
3. 使用业务线和事项字段做候选过滤。
4. 使用版本索引判断当前版本。
5. 答案中展示 `source_url`。
6. 如果版本证据不足，返回无法完成标志，交由人工客服兜底。

## 维护原则

- 数据库保存爬虫事实和版本映射。
- Markdown front matter 保存本地检索需要的元数据。
- 业务线和事项索引不进入数据库。
- 版本索引是数据库映射的本地快照。
- 旧 Markdown 没有 front matter 时，系统应保持兼容。
