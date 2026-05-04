# 资料库关键词搜索 Agent

一个不使用 RAG、向量库或 embedding 的资料库查询 CLI。配置 `DASHSCOPE_API_KEY` 后，它会通过阿里百炼 OpenAI 兼容 Function Calling 循环自主调用本地正文搜索、文件名模糊搜索、文件读取和可选联网工具，最后生成回答。

## 环境变量

PowerShell 示例：

```powershell
$env:DASHSCOPE_API_KEY="你的阿里百炼 API Key"
$env:SERPAPI_API_KEY="你的 SerpAPI Key"
$env:SEARCH_AGENT_DATA_DIR="D:\查询机器人资料\本地数据"
$env:SEARCH_AGENT_MODEL="deepseek-v4-flash"
```

不要把真实 key 写入代码或提交文件。

## 使用

```powershell
python -m search_agent ask "我住在上海，现在失业了，怎么缴纳社保"
python -m search_agent ask "上海公积金如何缴存" --web --show-sources
python -m search_agent ask "解释灵活就业参保" --no-web --show-sources
python -m search_agent ask "上海公积金如何缴存" --config search-agent.toml --no-web
```

没有配置 `DASHSCOPE_API_KEY` 时，程序不会调用模型，会输出检索到的证据摘要，便于调试本地搜索效果。

## 配置文件

默认会读取当前目录下的 `search-agent.toml`。也可以用 `--config` 指定路径。环境变量优先级高于配置文件，适合覆盖密钥或部署参数。

仓库只提交 `search-agent.example.toml`。本地使用时复制为 `search-agent.toml`，真实密钥不要提交。

`[agent] max_tool_steps` 控制 LLM tool-calling 主路径的最大工具循环步数；未配置时复用 `[search] max_rounds`，如果两者都未配置则默认 8。`[search] max_rounds` 仍用于无 `DASHSCOPE_API_KEY` 时的旧离线搜索兜底。

```toml
[agent]
max_tool_steps = 8
```

`[web_fetch]` 默认关闭。打开后，联网搜索会先用 Jina Reader 抓网页正文，正文太短、失败或质量不足时再用本机 Crawl4AI 兜底。

```toml
[web_fetch]
enabled = true
provider = "jina"
fallback_provider = "crawl4ai"
max_pages = 3
```

PDF 链接目前只会标记为 `pdf_unsupported`，后续需要单独接 PDF 下载和文本解析。

## 本地数据同步脚本

脚本默认从 `D:\code\sicrawl\.env.qa` 读取数据库环境变量，数据库正文来自 `policy_document_content.markdown_content`。默认写入 `D:\查询机器人资料\本地数据`，不传 `SourceId` 时不限制渠道。

完整同步流程：

```powershell
.\scripts\sync_all.ps1
```

它会按顺序执行：

```powershell
.\scripts\sync_reviewed_markdown.ps1
.\scripts\add_local_indexes.ps1
.\scripts\build_version_indexes.ps1
```

指定输出目录测试：

```powershell
.\scripts\sync_all.ps1 -DataDir "D:\查询机器人资料\temp_test"
```

指定数据源，例如只同步 `source_id = 3`：

```powershell
.\scripts\sync_all.ps1 -DataDir "D:\查询机器人资料\temp_test" -SourceId 3
```

需要排查某一步时，也可以单独运行三个子脚本。

`sync_reviewed_markdown.ps1` 只拉取 `auto_approved`、`manual_approved`、`filter_disabled` 状态的数据。生成文件名优先使用文档标题，标题重复且正文不同时会追加 `_v版本号`。脚本会写入 front matter，包括 `policy_document_id`、`version_group_id`、`version_index_path`、`source_url`、`review_status`、`content_hash`、`version_no` 等字段。

`add_local_indexes.ps1` 会在 Markdown front matter 中补充本地维护索引字段，包括 `primary_business_line`、`business_lines`、`service_items`、`doc_kind`、`agent_eligible`。已有字段不会被覆盖，便于后续人工维护。

`build_version_indexes.ps1` 会基于 `policy_version_group`、`policy_document`、`policy_change_log` 生成版本索引。只有同一版本组下对应文件两个或两个以上时才创建索引。索引位置根据 `policy_version_group.output_path_parts_json` 定位到正文所在目录，并写入该目录下的 `_indexes/version/`：

```text
正文目录/
  2025年度基数调整问答.md
  2024年度基数调整问答.md
  _indexes/
    version/
      基数调整问答.md
```

正文 front matter 中的 `version_index_path` 会指向这个同目录索引，例如：

```yaml
version_index_path: "_indexes/version/基数调整问答.md"
```

## 测试

```powershell
python -m unittest discover -v
```
