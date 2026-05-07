"""Gradio Web UI for Search Agent with real-time log streaming."""

from __future__ import annotations

import contextlib
import logging
import queue
import threading
import time
from pathlib import Path
from typing import TYPE_CHECKING

import gradio as gr

if TYPE_CHECKING:
    from .agent_loop import SearchAgent
    from .models import AgentAnswer

# ---------------------------------------------------------------------------
# Log streaming infrastructure
# ---------------------------------------------------------------------------


class QueueLogHandler(logging.Handler):
    """Pushes formatted log records into the given queue."""

    def __init__(self, log_queue: queue.Queue[str | None]) -> None:
        super().__init__()
        self._queue = log_queue
        self.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")
        )

    def emit(self, record: logging.LogRecord) -> None:
        try:
            self._queue.put(self.format(record))
        except Exception:
            pass


@contextlib.contextmanager
def _log_streaming(log_queue: queue.Queue[str | None]):
    """Install QueueLogHandler on the search_agent logger for the duration."""
    logger = logging.getLogger("search_agent")
    handler = QueueLogHandler(log_queue)
    logger.addHandler(handler)
    try:
        yield
    finally:
        logger.removeHandler(handler)


# ---------------------------------------------------------------------------
# Core generator
# ---------------------------------------------------------------------------


def ask_with_logs(
    agent: SearchAgent,
    question: str,
    web_policy: str = "auto",
    top_k: int = 8,
    history: list[dict] | None = None,
):
    """Generator yielding (chat_history, log_text, agent_answer | None, stats_text).

    Yields intermediate updates while the agent runs, then a final update
    with the complete answer and the AgentAnswer object.
    """
    log_q: queue.Queue[str | None] = queue.Queue()

    result_holder: dict = {}
    error_holder: list = []

    def _run() -> None:
        try:
            with _log_streaming(log_q):
                result_holder["answer"] = agent.ask(
                    question, web_policy=web_policy, top_k=top_k, history=history
                )
        except Exception as exc:
            error_holder.append(exc)
        finally:
            log_q.put(None)  # sentinel

    thread = threading.Thread(target=_run, daemon=True)
    start_time = time.monotonic()
    thread.start()

    collected_logs: list[str] = []
    MAX_LOG_LINES = 500

    while True:
        try:
            msg = log_q.get(timeout=0.3)
        except queue.Empty:
            elapsed = time.monotonic() - start_time
            yield [], "\n".join(collected_logs[-MAX_LOG_LINES:]), None, f"⏱ 处理中... {elapsed:.1f}s"
            continue
        if msg is None:
            break
        collected_logs.append(msg)
        elapsed = time.monotonic() - start_time
        yield [], "\n".join(collected_logs[-MAX_LOG_LINES:]), None, f"⏱ 处理中... {elapsed:.1f}s"

    # Drain any remaining messages
    while not log_q.empty():
        collected_logs.append(log_q.get_nowait())

    total_elapsed = time.monotonic() - start_time

    # Build final answer
    if error_holder:
        answer_text = f"处理出错: {error_holder[0]}"
    elif "answer" in result_holder:
        aa = result_holder["answer"]
        answer_text = aa.answer if hasattr(aa, "answer") else str(aa)
    else:
        answer_text = "未获取到答案"

    chat_update = [
        {"role": "user", "content": question},
        {"role": "assistant", "content": answer_text},
    ]
    agent_answer = result_holder.get("answer")

    # Build stats summary
    stats_parts = [f"⏱ 耗时 {total_elapsed:.1f}s"]
    if agent_answer and hasattr(agent_answer, "local_sources"):
        n_local = len(agent_answer.local_sources)
        n_web = len(agent_answer.web_sources)
        n_rounds = len(agent_answer.search_rounds)
        stats_parts.append(f"来源 {n_local} 本地 + {n_web} 网络")
        stats_parts.append(f"搜索 {n_rounds} 轮")
        stats_parts.append(f"{'✅ 可回答' if agent_answer.answerable else '❌ 证据不足'}")
    stats_text = " | ".join(stats_parts)

    yield chat_update, "\n".join(collected_logs[-MAX_LOG_LINES:]), agent_answer, stats_text


# ---------------------------------------------------------------------------
# Source formatting
# ---------------------------------------------------------------------------


def build_sources_markdown(agent_answer: AgentAnswer | None) -> str:
    if agent_answer is None:
        return ""
    lines: list[str] = []
    if agent_answer.local_sources:
        lines.append("### 本地来源\n")
        for src in agent_answer.local_sources:
            meta = src.metadata or {}
            source_url = meta.get("source_url", "")
            if source_url:
                lines.append(f"- **[{src.title}]({source_url})**")
            else:
                lines.append(f"- **{src.title}**")
            if src.matched_terms:
                lines.append(f"  命中关键词: {', '.join(src.matched_terms)}")
            version_info = _read_version_info(src.path, meta)
            if version_info:
                lines.append(version_info)
    if agent_answer.web_sources:
        lines.append("\n### 网络来源\n")
        for src in agent_answer.web_sources:
            lines.append(f"- [{src.title}]({src.url})")
            if src.date:
                lines.append(f"  日期: {src.date}")
    return "\n".join(lines) if lines else "无来源信息"


def _read_version_info(doc_path: Path, metadata: dict) -> str:
    """Read version index file if version_index_path exists in metadata."""
    vip = metadata.get("version_index_path", "").strip()
    if not vip:
        return ""
    index_path = doc_path.parent / vip
    try:
        text = index_path.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeDecodeError):
        return ""
    return _parse_version_index(text)


def _parse_version_index(text: str) -> str:
    """Extract version table rows from a version index Markdown file."""
    lines: list[str] = []
    pending_header: str | None = None
    in_table = False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("|") and "---" in stripped:
            # This is a separator; the previous line was the header
            in_table = True
            continue
        if stripped.startswith("|") and not in_table:
            # Potential header row (before separator)
            pending_header = stripped
            continue
        if in_table and stripped.startswith("|"):
            cols = [c.strip() for c in stripped.strip("|").split("|")]
            # Determine table shape from header
            header_cols = [c.strip() for c in (pending_header or "").strip("|").split("|")]
            if len(header_cols) >= 6 and len(cols) >= 5:
                # Historical: | 版本 | 状态 | 文档ID | 标题 | 原文 | 替代关系 |
                ver, title, url = cols[0], cols[3], cols[4]
            elif len(cols) >= 4:
                # Current: | 版本 | 文档ID | 标题 | 生效日期 | 原文 |
                ver, title = cols[0], cols[2]
                date = cols[3] if len(cols) > 3 else ""
                url = cols[4] if len(cols) > 4 else ""
            else:
                continue
            label = f"v{ver}"
            if len(header_cols) <= 5 and len(cols) > 3:
                label = f"v{ver} ({cols[3]})"
            if url.startswith("http"):
                lines.append(f"  - {label}: [{title}]({url})")
            else:
                lines.append(f"  - {label}: {title}")
        elif in_table and not stripped.startswith("|"):
            in_table = False
            pending_header = None
    if lines:
        return "  版本历史:\n" + "\n".join(lines)
    return ""


def _append_sources_to_answer(
    chat_history: list[dict], agent_answer: AgentAnswer | None
) -> list[dict]:
    """Append data sources to the last assistant message for inline display."""
    if not agent_answer or not chat_history:
        return chat_history
    src_lines: list[str] = []
    if agent_answer.local_sources:
        src_lines.append("\n\n---\n**数据来源:**\n")
        for src in agent_answer.local_sources:
            meta = src.metadata or {}
            source_url = meta.get("source_url", "")
            if source_url:
                src_lines.append(f"- [{src.title}]({source_url})")
            else:
                src_lines.append(f"- {src.title}")
    if agent_answer.web_sources:
        src_lines.append("\n**网络来源:**\n")
        for src in agent_answer.web_sources:
            src_lines.append(f"- [{src.title}]({src.url})")
    if src_lines:
        result = list(chat_history)
        last = dict(result[-1])
        last["content"] = last.get("content", "") + "".join(src_lines)
        result[-1] = last
        return result
    return chat_history


def merge_chat_update(chat_display: list[dict], chat_update: list[dict]) -> list[dict]:
    """Replace the current placeholder turn while preserving previous turns."""
    if not chat_update:
        return chat_display
    if len(chat_display) >= 2:
        return list(chat_display[:-2]) + list(chat_update)
    return list(chat_update)


# ---------------------------------------------------------------------------
# Gradio UI
# ---------------------------------------------------------------------------


def create_ui(agent: SearchAgent) -> gr.Blocks:
    with gr.Blocks(title="资料库搜索 Agent") as demo:
        gr.Markdown("# 资料库关键词搜索 Agent")
        gr.Markdown("输入问题，Agent 将搜索本地资料库并（可选）联网验证后回答。支持多轮对话和澄清追问。")

        conversation_state = gr.State([])

        with gr.Row():
            with gr.Column(scale=3):
                chatbot = gr.Chatbot(label="对话", height=400)
                with gr.Row():
                    question_input = gr.Textbox(
                        label="输入问题",
                        placeholder="例如: 灵活就业人员社保缴费标准是什么？",
                        lines=2,
                        scale=4,
                    )
                    submit_btn = gr.Button("发送", variant="primary", scale=1)
                with gr.Row():
                    new_conversation_btn = gr.Button("新建对话")
                    compress_btn = gr.Button("压缩对话")

                with gr.Accordion("搜索设置", open=False):
                    web_policy = gr.Radio(
                        choices=["auto", "always", "never"],
                        value="auto",
                        label="联网策略",
                    )
                    top_k = gr.Slider(
                        minimum=1, maximum=20, value=8, step=1,
                        label="返回来源数量",
                    )

            with gr.Column(scale=2):
                stats_display = gr.Markdown(label="统计", value="")
                log_display = gr.Textbox(
                    label="实时日志",
                    lines=20,
                    max_lines=50,
                    interactive=False,
                    buttons=["copy"],
                )
                sources_display = gr.Markdown(label="来源详情")

        def on_submit(
            question: str,
            chat_display: list,
            policy: str,
            top_k_val: float,
            conv_state: list,
        ):
            question = (question or "").strip()
            if not question:
                yield chat_display, "", "", "", gr.update(), conv_state
                return

            chat_display = chat_display + [
                {"role": "user", "content": question},
                {"role": "assistant", "content": "正在分析问题，请稍候..."},
            ]
            yield chat_display, "正在分析问题...", "⏱ 启动中...", "", "", conv_state

            agent_answer = None
            last_log = ""
            last_stats = ""
            chat_update = []
            for chat_update, log_text, aa, stats in ask_with_logs(
                agent, question, web_policy=policy, top_k=int(top_k_val), history=conv_state
            ):
                agent_answer = aa
                last_log = log_text
                last_stats = stats
                if chat_update:
                    merged_update = merge_chat_update(chat_display, chat_update)
                    answer_with_sources = _append_sources_to_answer(merged_update, agent_answer)
                    yield answer_with_sources, log_text, stats, build_sources_markdown(aa), gr.update(), conv_state
                else:
                    yield chat_display, log_text, stats, build_sources_markdown(agent_answer), gr.update(), conv_state

            new_conv_state = agent_answer.conversation_history if agent_answer else conv_state

            if agent_answer and agent_answer.needs_clarification:
                chat_update = [
                    {"role": "user", "content": question},
                    {"role": "assistant", "content": agent_answer.answer},
                ]
                merged = merge_chat_update(chat_display, chat_update)
                yield merged, last_log, last_stats, "", gr.update(), new_conv_state
            else:
                final_history = merge_chat_update(chat_display, chat_update) if chat_update else chat_display
                final_with_sources = _append_sources_to_answer(final_history, agent_answer)
                yield final_with_sources, last_log, last_stats, build_sources_markdown(agent_answer), "", new_conv_state

        def on_new_conversation():
            return [], "", "", "", []

        def on_compress(conv_state: list):
            if not conv_state or len(conv_state) < 6:
                return conv_state
            try:
                compressed = agent.llm_client.compress_conversation(conv_state, keep_recent=4)
                return compressed
            except Exception:
                return conv_state

        submit_args = dict(
            fn=on_submit,
            inputs=[question_input, chatbot, web_policy, top_k, conversation_state],
            outputs=[chatbot, log_display, stats_display, sources_display, question_input, conversation_state],
        )
        submit_btn.click(**submit_args)
        question_input.submit(**submit_args)

        new_conversation_btn.click(
            fn=on_new_conversation,
            outputs=[chatbot, log_display, stats_display, sources_display, conversation_state],
        )
        compress_btn.click(
            fn=on_compress,
            inputs=[conversation_state],
            outputs=[conversation_state],
        )

    return demo


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main(
    config_path: str | None = None,
    server_name: str = "0.0.0.0",
    server_port: int = 7860,
) -> None:
    from .agent_loop import SearchAgent
    from .config import Settings
    from .logging_config import configure_logging

    settings = Settings.from_sources(config_path)
    configure_logging(
        enabled=settings.log_enabled,
        level=settings.log_level,
        file_path=settings.log_file,
    )
    agent = SearchAgent.from_settings(settings)
    demo = create_ui(agent)
    demo.launch(server_name=server_name, server_port=server_port)
