# 资料库关键词搜索 Agent

一个不使用 RAG、向量库或 embedding 的资料库查询 CLI。它会搜索本地 Markdown 的路径、标题和正文，按需调用 SerpAPI 联网核对，再用阿里百炼 OpenAI 兼容接口生成回答。

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

`[web_fetch]` 默认关闭。打开后，联网搜索会先用 Jina Reader 抓网页正文，正文太短、失败或质量不足时再用本机 Crawl4AI 兜底。

```toml
[web_fetch]
enabled = true
provider = "jina"
fallback_provider = "crawl4ai"
max_pages = 3
```

PDF 链接目前只会标记为 `pdf_unsupported`，后续需要单独接 PDF 下载和文本解析。

## 测试

```powershell
python -m unittest discover -v
```
