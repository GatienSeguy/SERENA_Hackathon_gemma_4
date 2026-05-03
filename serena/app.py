"""SERENA Gradio UI. Conversation history + USER/ADMIN modes + responsive layout."""

from __future__ import annotations

import json
import logging
from datetime import datetime

import gradio as gr
import plotly.graph_objects as go

from serena_core import SerenaCore

logger = logging.getLogger("serena.app")
if not logger.handlers:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

# ─────────────────────────────────────────────────────────────────────
# Design system
# ─────────────────────────────────────────────────────────────────────
BG = "#0a0d12"
SURFACE = "#11151c"
SURFACE_2 = "#161b24"
BORDER = "#1f2630"
BORDER_STRONG = "#2a323e"

TEXT = "#eef1f5"
TEXT_SOFT = "#b6bfcc"
TEXT_MUTED = "#7a8595"
TEXT_DIM = "#586374"

ACCENT = "#7eb09f"
ACCENT_DEEP = "#5b8c7f"
ACCENT_SOFT = "#3a5a52"

STATUS_NORMAL = "#7eb09f"
STATUS_ALERT = "#d4a056"
STATUS_BLOCK = "#c87970"
STATUS_EMERGENCY = "#9a4248"

ACTION_COLORS = {
    "NORMAL": STATUS_NORMAL,
    "ALERT": STATUS_ALERT,
    "BLOCK": STATUS_BLOCK,
    "EMERGENCY": STATUS_EMERGENCY,
}
ACTION_LABELS_FR = {
    "NORMAL": "Normal",
    "ALERT": "Vigilance",
    "BLOCK": "Restreint",
    "EMERGENCY": "Urgence",
}

CUSTOM_CSS = f"""
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=Fraunces:opsz,wght@9..144,500;9..144,600;9..144,700&family=JetBrains+Mono:wght@400;500&display=swap');

:root {{
    --bg: {BG};
    --surface: {SURFACE};
    --surface-2: {SURFACE_2};
    --border: {BORDER};
    --border-strong: {BORDER_STRONG};
    --text: {TEXT};
    --text-soft: {TEXT_SOFT};
    --text-muted: {TEXT_MUTED};
    --text-dim: {TEXT_DIM};
    --accent: {ACCENT};
    --accent-deep: {ACCENT_DEEP};
    --accent-soft: {ACCENT_SOFT};
}}

* {{
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif !important;
    -webkit-font-smoothing: antialiased;
    -moz-osx-font-smoothing: grayscale;
    box-sizing: border-box;
}}

html, body, .gradio-container {{
    background-color: var(--bg) !important;
    color: var(--text) !important;
}}

.gradio-container {{
    max-width: 100% !important;
    width: 100% !important;
    margin: 0 auto !important;
    padding: 0 clamp(12px, 3vw, 32px) !important;
    min-height: 100vh;
}}

footer, .footer, .show-api, .built-with {{
    display: none !important;
}}

/* ── Header ── */
#serena-header {{
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: clamp(16px, 3vw, 28px) 4px clamp(14px, 2.5vw, 24px) 4px;
    border-bottom: 1px solid var(--border);
    margin-bottom: clamp(16px, 2.5vw, 28px);
    flex-wrap: wrap;
    gap: 12px;
}}
#serena-wordmark {{
    display: flex;
    flex-direction: column;
    line-height: 1.1;
}}
#serena-wordmark .name {{
    font-family: 'Fraunces', serif !important;
    font-size: clamp(20px, 2.5vw, 26px);
    font-weight: 600;
    color: var(--text);
    letter-spacing: 2px;
}}
#serena-wordmark .tagline {{
    color: var(--text-muted);
    font-size: 11px;
    font-weight: 500;
    letter-spacing: 1.2px;
    text-transform: uppercase;
    margin-top: 4px;
}}
#serena-mode-pill {{
    display: inline-flex;
    align-items: center;
    gap: 8px;
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 999px;
    padding: 6px 14px;
    font-size: 11px;
    font-weight: 600;
    letter-spacing: 1.5px;
    text-transform: uppercase;
    color: var(--text-muted);
}}
#serena-mode-pill.admin {{
    background: var(--accent-soft);
    border-color: var(--accent);
    color: var(--accent);
}}
#serena-mode-pill::before {{
    content: '';
    width: 6px;
    height: 6px;
    border-radius: 50%;
    background: var(--accent);
    box-shadow: 0 0 8px var(--accent);
}}

/* ── Mode toggle ── */
#mode-toggle-row {{
    display: flex;
    justify-content: flex-end;
    margin-bottom: 12px;
}}
#mode-toggle-row label {{
    color: var(--text-muted) !important;
    font-size: 12px !important;
    font-weight: 500 !important;
    letter-spacing: 0.5px !important;
}}

/* ── Sidebar (conversations) ── */
#sidebar {{
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 14px;
    padding: 16px 12px;
    height: 100%;
    min-height: 560px;
    display: flex;
    flex-direction: column;
    gap: 12px;
}}
#sidebar h4 {{
    color: var(--text-muted) !important;
    font-size: 11px !important;
    font-weight: 600 !important;
    text-transform: uppercase;
    letter-spacing: 1.5px;
    margin: 0 4px 8px 4px !important;
}}
#sidebar .gr-radio,
#sidebar .gr-form {{
    background: transparent !important;
    border: none !important;
    padding: 0 !important;
}}
#sidebar input[type="radio"] {{
    display: none !important;
}}
#sidebar label {{
    display: block !important;
    padding: 10px 12px !important;
    margin-bottom: 4px !important;
    border-radius: 8px !important;
    color: var(--text-soft) !important;
    font-size: 13px !important;
    font-weight: 500 !important;
    cursor: pointer !important;
    transition: all 0.12s ease !important;
    background: transparent !important;
    border: 1px solid transparent !important;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
}}
#sidebar label:hover {{
    background: var(--surface-2) !important;
    color: var(--text) !important;
}}
#sidebar input[type="radio"]:checked + span,
#sidebar label.selected,
#sidebar [aria-checked="true"] {{
    background: var(--accent-soft) !important;
    color: var(--accent) !important;
    border-color: var(--accent) !important;
}}

/* ── Chatbot ── */
.chatbot {{
    background-color: var(--surface) !important;
    border: 1px solid var(--border) !important;
    border-radius: 16px !important;
    box-shadow: 0 1px 0 rgba(255,255,255,0.02) inset, 0 8px 24px rgba(0,0,0,0.25);
}}
.chatbot * {{
    color: var(--text) !important;
}}
.message {{
    padding: 14px 18px !important;
    line-height: 1.6 !important;
    font-size: 14.5px !important;
}}
.message.user {{
    background: var(--accent-soft) !important;
    border-radius: 14px 14px 4px 14px !important;
}}
.message.bot, .message.assistant {{
    background: var(--surface-2) !important;
    border-radius: 14px 14px 14px 4px !important;
}}

/* ── Input ── */
.input-row {{
    margin-top: 16px;
    gap: 10px !important;
}}
textarea, input[type="text"] {{
    background-color: var(--surface) !important;
    color: var(--text) !important;
    border: 1px solid var(--border) !important;
    border-radius: 12px !important;
    padding: 14px 16px !important;
    font-size: 14.5px !important;
    line-height: 1.5 !important;
    resize: none !important;
    transition: border-color 0.15s ease, box-shadow 0.15s ease;
    width: 100% !important;
}}
textarea:focus, input[type="text"]:focus {{
    border-color: var(--accent) !important;
    box-shadow: 0 0 0 3px rgba(126, 176, 159, 0.12) !important;
    outline: none !important;
}}
textarea::placeholder, input::placeholder {{
    color: var(--text-dim) !important;
}}

/* ── Buttons ── */
button {{
    font-weight: 600 !important;
    letter-spacing: 0.2px !important;
    border-radius: 10px !important;
    transition: all 0.15s ease !important;
}}
button.primary, .gr-button-primary {{
    background: var(--accent) !important;
    color: var(--bg) !important;
    border: 1px solid var(--accent) !important;
    padding: 12px 20px !important;
    font-size: 14px !important;
}}
button.primary:hover, .gr-button-primary:hover {{
    background: var(--accent-deep) !important;
    border-color: var(--accent-deep) !important;
    transform: translateY(-1px);
}}
button.secondary, .gr-button-secondary {{
    background: transparent !important;
    color: var(--text-muted) !important;
    border: 1px solid var(--border) !important;
    padding: 8px 14px !important;
    font-size: 13px !important;
}}
button.secondary:hover {{
    color: var(--text) !important;
    border-color: var(--border-strong) !important;
}}

#new-conv-btn {{
    width: 100% !important;
    margin-bottom: 8px !important;
}}

/* ── Dashboard ── */
.dashboard-card {{
    background-color: var(--surface) !important;
    border: 1px solid var(--border) !important;
    border-radius: 12px !important;
    padding: 16px !important;
    margin-bottom: 12px !important;
}}
.dashboard-card .gr-markdown h4 {{
    color: var(--text-muted) !important;
    margin: 0 0 12px 0 !important;
    font-size: 11px !important;
    font-weight: 600 !important;
    text-transform: uppercase;
    letter-spacing: 1.5px;
}}
.dashboard-card .gr-markdown {{
    color: var(--text-soft) !important;
    font-size: 13.5px !important;
}}
.dashboard-card table {{
    width: 100% !important;
    border-collapse: collapse !important;
    font-size: 12.5px !important;
}}
.dashboard-card table th {{
    color: var(--text-muted) !important;
    font-weight: 500 !important;
    text-align: left !important;
    padding: 6px 8px !important;
    border-bottom: 1px solid var(--border) !important;
    font-size: 11px !important;
    text-transform: uppercase;
    letter-spacing: 0.8px;
}}
.dashboard-card table td {{
    padding: 8px !important;
    color: var(--text-soft) !important;
    border-bottom: 1px solid var(--border) !important;
}}
.dashboard-card code {{
    background: var(--surface-2) !important;
    color: var(--accent) !important;
    padding: 2px 6px !important;
    border-radius: 4px !important;
    font-family: 'JetBrains Mono', monospace !important;
    font-size: 11.5px !important;
}}

/* ── Action banner ── */
#action-banner {{
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 10px;
    padding: 14px 18px;
    border-radius: 12px;
    font-size: 13px;
    font-weight: 700;
    letter-spacing: 2px;
    text-transform: uppercase;
    color: white;
    background-color: {STATUS_NORMAL};
    margin-bottom: 12px;
    box-shadow: 0 4px 14px rgba(0,0,0,0.2);
}}
#action-banner .dot {{
    width: 8px;
    height: 8px;
    border-radius: 50%;
    background: white;
    box-shadow: 0 0 12px rgba(255,255,255,0.6);
}}

.plot-container, .js-plotly-plot {{
    background: transparent !important;
}}

.gr-accordion {{
    background: var(--surface) !important;
    border: 1px solid var(--border) !important;
    border-radius: 12px !important;
}}
.gr-accordion summary {{
    color: var(--text-muted) !important;
    font-size: 12px !important;
    font-weight: 500 !important;
    letter-spacing: 0.5px !important;
}}

pre, code, .gr-code {{
    background: var(--bg) !important;
    color: var(--text-soft) !important;
    border: 1px solid var(--border) !important;
    border-radius: 8px !important;
    font-family: 'JetBrains Mono', monospace !important;
    font-size: 12px !important;
    line-height: 1.6 !important;
}}

::-webkit-scrollbar {{ width: 8px; height: 8px; }}
::-webkit-scrollbar-track {{ background: transparent; }}
::-webkit-scrollbar-thumb {{ background: var(--border-strong); border-radius: 4px; }}
::-webkit-scrollbar-thumb:hover {{ background: var(--text-dim); }}

hr {{
    border: none !important;
    border-top: 1px solid var(--border) !important;
    margin: 16px 0 !important;
}}

.gr-form > .gr-block.gr-box {{
    border: none !important;
    background: transparent !important;
}}

/* ── Responsive ── */
@media (max-width: 1024px) {{
    .gradio-container {{
        padding: 0 16px !important;
    }}
}}

@media (max-width: 768px) {{
    #sidebar {{
        min-height: auto !important;
        max-height: 220px;
        overflow-y: auto;
    }}
    .chatbot {{
        height: 420px !important;
    }}
    #serena-wordmark .name {{
        font-size: 18px;
    }}
    #serena-wordmark .tagline {{
        font-size: 10px;
    }}
    .message {{
        font-size: 13.5px !important;
        padding: 12px 14px !important;
    }}
    .gr-row {{
        flex-direction: column !important;
    }}
}}

@media (max-width: 480px) {{
    #serena-mode-pill {{
        font-size: 10px;
        padding: 4px 10px;
    }}
    button.primary {{
        padding: 10px 16px !important;
        font-size: 13px !important;
    }}
}}
"""


# ─────────────────────────────────────────────────────────────────────
# Plot helpers
# ─────────────────────────────────────────────────────────────────────
def _gauge_figure(score: float, action: str) -> go.Figure:
    color = ACTION_COLORS.get(action, STATUS_NORMAL)
    fig = go.Figure(
        go.Indicator(
            mode="gauge+number",
            value=score,
            number={"font": {"color": TEXT, "size": 30, "family": "Inter"}, "valueformat": ".2f"},
            gauge={
                "axis": {
                    "range": [0, 1],
                    "tickcolor": TEXT_MUTED,
                    "tickfont": {"color": TEXT_MUTED, "size": 10, "family": "Inter"},
                    "tickwidth": 1,
                    "tickvals": [0, 0.3, 0.6, 0.85, 1.0],
                },
                "bar": {"color": color, "thickness": 0.28},
                "bgcolor": "rgba(0,0,0,0)",
                "borderwidth": 0,
                "steps": [
                    {"range": [0, 0.29], "color": "rgba(126,176,159,0.10)"},
                    {"range": [0.29, 0.59], "color": "rgba(212,160,86,0.10)"},
                    {"range": [0.59, 0.84], "color": "rgba(200,121,112,0.10)"},
                    {"range": [0.84, 1.0], "color": "rgba(154,66,72,0.14)"},
                ],
                "threshold": {"line": {"color": TEXT, "width": 2}, "thickness": 0.75, "value": score},
            },
        )
    )
    fig.update_layout(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font={"color": TEXT, "family": "Inter"},
        height=200,
        margin=dict(l=20, r=20, t=10, b=10),
        autosize=True,
    )
    return fig


def _history_figure(history: list[float]) -> go.Figure:
    xs = list(range(1, len(history) + 1))
    fig = go.Figure()
    fig.add_hrect(y0=0.0, y1=0.29, fillcolor=STATUS_NORMAL, opacity=0.06, line_width=0)
    fig.add_hrect(y0=0.29, y1=0.59, fillcolor=STATUS_ALERT, opacity=0.06, line_width=0)
    fig.add_hrect(y0=0.59, y1=0.84, fillcolor=STATUS_BLOCK, opacity=0.06, line_width=0)
    fig.add_hrect(y0=0.84, y1=1.0, fillcolor=STATUS_EMERGENCY, opacity=0.10, line_width=0)
    fig.add_trace(
        go.Scatter(
            x=xs,
            y=history,
            mode="lines+markers",
            line=dict(color=ACCENT, width=2.5, shape="spline", smoothing=0.4),
            marker=dict(color=ACCENT, size=7, line=dict(color=BG, width=2)),
            name="Score",
            hovertemplate="Tour %{x}<br>Score %{y:.2f}<extra></extra>",
        )
    )
    fig.update_layout(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font={"color": TEXT_SOFT, "family": "Inter", "size": 11},
        height=180,
        margin=dict(l=36, r=12, t=10, b=30),
        autosize=True,
        xaxis=dict(
            title=None,
            gridcolor="rgba(255,255,255,0.04)",
            zerolinecolor="rgba(255,255,255,0.04)",
            tickfont=dict(color=TEXT_MUTED, size=10),
        ),
        yaxis=dict(
            title=None,
            range=[0, 1],
            gridcolor="rgba(255,255,255,0.04)",
            zerolinecolor="rgba(255,255,255,0.04)",
            tickfont=dict(color=TEXT_MUTED, size=10),
            tickvals=[0, 0.3, 0.6, 0.85, 1.0],
        ),
        showlegend=False,
        hoverlabel=dict(bgcolor=SURFACE_2, bordercolor=BORDER_STRONG, font_color=TEXT, font_family="Inter"),
    )
    return fig


def _signals_markdown(signals: dict) -> str:
    if not signals:
        return "_Aucun signal détecté._"
    lines = ["| Signal | Tour | × | Sévérité |", "|---|---|---|---|"]
    for name, info in signals.items():
        lines.append(
            f"| `{name}` | {info.get('first_seen', '?')} "
            f"| {info.get('count', 1)} | {info.get('severity', '—')} |"
        )
    return "\n".join(lines)


def _action_banner_html(action: str) -> str:
    color = ACTION_COLORS.get(action, STATUS_NORMAL)
    label = ACTION_LABELS_FR.get(action, action)
    return (
        f"<div id='action-banner' style='background-color:{color};'>"
        f"<span class='dot'></span>{label}"
        "</div>"
    )


def _condition_markdown(condition: str, confidence: float) -> str:
    if not condition:
        return "**Condition probable** &nbsp;·&nbsp; _aucune_"
    return (
        f"**Condition probable** &nbsp;·&nbsp; {condition}  \n"
        f"**Confiance du modèle** &nbsp;·&nbsp; {confidence:.0%}"
    )


def _empty_dashboard():
    return (
        _gauge_figure(0.0, "NORMAL"),
        _history_figure([]),
        _signals_markdown({}),
        _condition_markdown("", 0.0),
        _action_banner_html("NORMAL"),
        "{}",
    )


def _truncate(text: str, n: int = 32) -> str:
    text = (text or "").strip().replace("\n", " ")
    return text if len(text) <= n else text[: n - 1] + "…"


# ─────────────────────────────────────────────────────────────────────
# App
# ─────────────────────────────────────────────────────────────────────
class App:
    def __init__(self) -> None:
        # conversation store: id -> {"title": str, "core": SerenaCore, "created": datetime}
        self.conversations: dict[str, dict] = {}
        self.active_id: str | None = None
        self._counter = 0
        self._new_conversation()  # start with one

    def _new_conversation(self) -> str:
        self._counter += 1
        cid = f"conv_{self._counter}"
        self.conversations[cid] = {
            "title": f"Conversation {self._counter}",
            "core": SerenaCore(),
            "created": datetime.now(),
        }
        self.active_id = cid
        return cid

    def _choices(self) -> list[tuple[str, str]]:
        # Return (label, value) pairs, newest first
        items = sorted(
            self.conversations.items(),
            key=lambda kv: kv[1]["created"],
            reverse=True,
        )
        return [(c["title"], cid) for cid, c in items]

    def _chat_history_for(self, cid: str) -> list[dict]:
        core = self.conversations[cid]["core"]
        return [
            {"role": m["role"], "content": m["content"]}
            for m in core.memory.conversation_history
        ]

    def _state_snapshot(self, cid: str):
        core = self.conversations[cid]["core"]
        mem = core.memory
        gauge = _gauge_figure(mem.cumulative_risk_score, mem.current_action)
        hist = _history_figure(mem.risk_history)
        signals_md = _signals_markdown(mem.detected_signals)
        cond_md = _condition_markdown(mem.probable_condition, mem.confidence)
        banner = _action_banner_html(mem.current_action)
        # debug shows last pass1 raw if available — we don't store it, leave empty until next message
        debug = "{}"
        return gauge, hist, signals_md, cond_md, banner, debug

    # ── Handlers ──────────────────────────────────────────────────
    def respond(self, message: str, chat_history: list, active_id: str):
        message = (message or "").strip()
        if not message or active_id not in self.conversations:
            gauge, hist, signals_md, cond_md, banner, debug = _empty_dashboard()
            yield (
                chat_history, gauge, hist, signals_md, cond_md, banner, debug, "",
                gr.update(),
            )
            return

        core: SerenaCore = self.conversations[active_id]["core"]

        # Auto-title on first user message
        is_first = len(core.memory.conversation_history) == 0
        if is_first:
            self.conversations[active_id]["title"] = _truncate(message, 32)

        chat_history = list(chat_history) + [
            {"role": "user", "content": message},
            {"role": "assistant", "content": "_…analyse en cours…_"},
        ]
        gauge, hist, signals_md, cond_md, banner, debug = _empty_dashboard()
        yield (
            chat_history, gauge, hist, signals_md, cond_md, banner, debug, "",
            gr.update(),
        )

        result = core.process_message(message)
        chat_history[-1] = {"role": "assistant", "content": result["response"]}

        gauge = _gauge_figure(result["score"], result["action"])
        hist = _history_figure(result["score_history"])
        signals_md = _signals_markdown(result["signals"])
        cond_md = _condition_markdown(core.memory.probable_condition, core.memory.confidence)
        banner = _action_banner_html(result["action"])
        debug = json.dumps(result["pass1_raw"], indent=2, ensure_ascii=False)

        sidebar_update = (
            gr.update(choices=self._choices(), value=active_id) if is_first else gr.update()
        )

        yield (
            chat_history, gauge, hist, signals_md, cond_md, banner, debug, "",
            sidebar_update,
        )

    def new_conversation(self):
        cid = self._new_conversation()
        gauge, hist, signals_md, cond_md, banner, debug = _empty_dashboard()
        return (
            [],                                    # chat
            gauge, hist, signals_md, cond_md, banner, debug,
            "",                                    # input
            gr.update(choices=self._choices(), value=cid),
            cid,                                   # state
        )

    def switch_conversation(self, new_id: str):
        if not new_id or new_id not in self.conversations:
            return gr.update(), *_empty_dashboard(), new_id
        self.active_id = new_id
        chat = self._chat_history_for(new_id)
        gauge, hist, signals_md, cond_md, banner, debug = self._state_snapshot(new_id)
        return chat, gauge, hist, signals_md, cond_md, banner, debug, new_id

    # ── Build ─────────────────────────────────────────────────────
    def build(self) -> gr.Blocks:
        with gr.Blocks(title="SERENA — L'IA qui protège de l'IA") as demo:
            header_html = gr.HTML(self._render_header("USER"))

            with gr.Row(elem_id="mode-toggle-row"):
                admin_toggle = gr.Checkbox(label="Mode administrateur", value=False, scale=0)

            initial_choices = self._choices()
            initial_id = initial_choices[0][1] if initial_choices else None
            active_state = gr.State(value=initial_id)

            with gr.Row():
                # ── Sidebar: conversations ──
                with gr.Column(scale=2, min_width=180, elem_id="sidebar-col"):
                    with gr.Group(elem_id="sidebar"):
                        gr.Markdown("#### Conversations")
                        new_btn = gr.Button(
                            "+ Nouvelle conversation",
                            variant="primary",
                            elem_id="new-conv-btn",
                        )
                        conv_radio = gr.Radio(
                            choices=initial_choices,
                            value=initial_id,
                            show_label=False,
                            container=False,
                        )

                # ── Chat ──
                with gr.Column(scale=7, min_width=320):
                    chatbot = gr.Chatbot(
                        show_label=False,
                        height=560,
                        elem_classes="chatbot",
                        avatar_images=(None, None),
                        render_markdown=True,
                    )
                    with gr.Row(elem_classes="input-row"):
                        user_input = gr.Textbox(
                            placeholder="Écrivez votre message à SERENA…",
                            show_label=False,
                            scale=8,
                            lines=2,
                            max_lines=8,
                            container=False,
                        )
                        send_btn = gr.Button("Envoyer", variant="primary", scale=1, min_width=120)

                # ── Admin panel ──
                with gr.Column(scale=4, min_width=280, visible=False) as admin_col:
                    action_banner = gr.HTML(_action_banner_html("NORMAL"))

                    with gr.Group(elem_classes="dashboard-card"):
                        gr.Markdown("#### Score de risque")
                        gauge_plot = gr.Plot(
                            value=_gauge_figure(0.0, "NORMAL"),
                            show_label=False,
                            container=False,
                        )

                    with gr.Group(elem_classes="dashboard-card"):
                        gr.Markdown("#### Évolution par tour")
                        history_plot = gr.Plot(
                            value=_history_figure([]),
                            show_label=False,
                            container=False,
                        )

                    with gr.Group(elem_classes="dashboard-card"):
                        gr.Markdown("#### Signaux détectés")
                        signals_md = gr.Markdown(_signals_markdown({}))

                    with gr.Group(elem_classes="dashboard-card"):
                        condition_md = gr.Markdown(_condition_markdown("", 0.0))

                    with gr.Accordion("Analyse Pass 1 (JSON brut)", open=False):
                        debug_json = gr.Code(value="{}", language="json", show_label=False)

            # ── Wiring ──
            def _toggle_admin(enabled: bool):
                mode = "ADMIN" if enabled else "USER"
                return gr.update(visible=enabled), self._render_header(mode)

            admin_toggle.change(
                fn=_toggle_admin,
                inputs=[admin_toggle],
                outputs=[admin_col, header_html],
            )

            send_outputs = [
                chatbot, gauge_plot, history_plot, signals_md, condition_md,
                action_banner, debug_json, user_input, conv_radio,
            ]
            send_btn.click(
                fn=self.respond,
                inputs=[user_input, chatbot, active_state],
                outputs=send_outputs,
            )
            user_input.submit(
                fn=self.respond,
                inputs=[user_input, chatbot, active_state],
                outputs=send_outputs,
            )

            new_btn.click(
                fn=self.new_conversation,
                inputs=[],
                outputs=[
                    chatbot, gauge_plot, history_plot, signals_md, condition_md,
                    action_banner, debug_json, user_input, conv_radio, active_state,
                ],
            )

            conv_radio.change(
                fn=self.switch_conversation,
                inputs=[conv_radio],
                outputs=[
                    chatbot, gauge_plot, history_plot, signals_md, condition_md,
                    action_banner, debug_json, active_state,
                ],
            )

        return demo

    @staticmethod
    def _render_header(mode: str) -> str:
        pill_class = "admin" if mode == "ADMIN" else ""
        pill_label = "Admin" if mode == "ADMIN" else "En ligne"
        return (
            "<div id='serena-header'>"
            "  <div id='serena-wordmark'>"
            "    <span class='name'>SERENA</span>"
            "    <span class='tagline'>L'IA qui protège de l'IA</span>"
            "  </div>"
            f"  <div id='serena-mode-pill' class='{pill_class}'>{pill_label}</div>"
            "</div>"
        )


def main() -> None:
    app = App()
    demo = app.build()
    demo.queue()
    demo.launch(
        server_name="0.0.0.0",
        server_port=7860,
        share=True,
        css=CUSTOM_CSS,
        theme=gr.themes.Base(
            primary_hue=gr.themes.colors.emerald,
            neutral_hue=gr.themes.colors.slate,
            font=[gr.themes.GoogleFont("Inter"), "system-ui", "sans-serif"],
            font_mono=[gr.themes.GoogleFont("JetBrains Mono"), "monospace"],
        ),
    )


if __name__ == "__main__":
    main()
