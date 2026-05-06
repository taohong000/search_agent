"""Gradio Web UI for Search Agent with real-time log streaming."""

from __future__ import annotations

import contextlib
import logging
import queue
import threading
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
):
    """Generator yielding (chat_history, log_text, agent_answer | None).

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
                    question, web_policy=web_policy, top_k=top_k
                )
        except Exception as exc:
            error_holder.append(exc)
        finally:
            log_q.put(None)  # sentinel

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()

    collected_logs: list[str] = []
    MAX_LOG_LINES = 500

    while True:
        try:
            msg = log_q.get(timeout=0.3)
        except queue.Empty:
            yield [], "\n".join(collected_logs[-MAX_LOG_LINES:]), None
            continue
        if msg is None:
            break
        collected_logs.append(msg)
        yield [], "\n".join(collected_logs[-MAX_LOG_LINES:]), None

    # Drain any remaining messages
    while not log_q.empty():
        collected_logs.append(log_q.get_nowait())

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
    yield chat_update, "\n".join(collected_logs[-MAX_LOG_LINES:]), agent_answer


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
            lines.append(f"- **{src.title}** (`{src.path}`)")
            if src.matched_terms:
                lines.append(f"  命中关键词: {', '.join(src.matched_terms)}")
    if agent_answer.web_sources:
        lines.append("\n### 网络来源\n")
        for src in agent_answer.web_sources:
            lines.append(f"- [{src.title}]({src.url})")
            if src.date:
                lines.append(f"  日期: {src.date}")
    return "\n".join(lines) if lines else "无来源信息"


# ---------------------------------------------------------------------------
# Gradio UI
# ---------------------------------------------------------------------------


def create_ui(agent: SearchAgent) -> gr.Blocks:
    with gr.Blocks(title="资料库搜索 Agent") as demo:
        gr.Markdown("# 资料库关键词搜索 Agent")
        gr.Markdown("输入问题，Agent 将搜索本地资料库并（可选）联网验证后回答。")

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
                clear_btn = gr.Button("清空对话")

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
            history: list,
            policy: str,
            top_k_val: float,
        ):
            question = (question or "").strip()
            if not question:
                yield history, "", "", gr.update()
                return

            history = history + [
                {"role": "user", "content": question},
                {"role": "assistant", "content": "正在搜索，请稍候..."},
            ]
            yield history, "正在初始化...", "", gr.update()

            agent_answer = None
            for chat_update, log_text, aa in ask_with_logs(
                agent, question, web_policy=policy, top_k=int(top_k_val)
            ):
                agent_answer = aa
                if chat_update:
                    yield chat_update, log_text, build_sources_markdown(aa), gr.update()
                else:
                    yield history, log_text, build_sources_markdown(agent_answer), gr.update()

            final_history = chat_update if chat_update else history
            yield final_history, log_text, build_sources_markdown(agent_answer), ""

        def on_clear():
            return [], "", ""

        submit_args = dict(
            fn=on_submit,
            inputs=[question_input, chatbot, web_policy, top_k],
            outputs=[chatbot, log_display, sources_display, question_input],
        )
        submit_btn.click(**submit_args)
        question_input.submit(**submit_args)
        clear_btn.click(fn=on_clear, outputs=[chatbot, log_display, sources_display])

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
