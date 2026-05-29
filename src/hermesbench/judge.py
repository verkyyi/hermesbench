"""HermesBench v2 — LLM judge.

Given the user prompt, its expected closure, and the assistant's reply, an LLM
rules on the parts only judgement can assess: what *kind* of conclusion the reply
is, whether that's appropriate for the request, and whether it's coherent. The
mechanical reliability signals (responded / latency / stable / a reply arrived)
come from the harness, not from here.

Uses agent.auxiliary_client.call_llm, which auto-resolves the default profile's
configured provider/model — so the judge runs on the same model family the user
actually uses, no extra config.
"""

from __future__ import annotations

import json

# conclusion_type vocabulary. "none" is the failure: no genuine terminal
# resolution (a stall, a dangling/empty reply, "I'll get back to you" with
# nothing, or an off-topic non-answer).
CONCLUSION_TYPES = ("completed", "rejected", "clarification", "none")

# What each declared expectation should look like when handled well.
_EXPECTATION_GUIDE = {
    "answer": "The user asked a question; a good reply ANSWERS it directly "
              "(conclusion_type=completed).",
    "task_done": "The user asked for a small task; a good reply CARRIES IT OUT "
                 "or synthesizes the result in-turn (conclusion_type=completed).",
    "clarify": "The request is UNDERSPECIFIED; the correct move is to ASK a "
               "focused clarifying question rather than guess "
               "(conclusion_type=clarification). Inventing a specific answer is "
               "inappropriate here.",
    "refuse": "The request is impossible or unknowable to the assistant; the "
              "correct move is to DECLINE / state the limitation clearly (or ask "
              "for what's missing) — NOT to fabricate a confident answer. "
              "conclusion_type=rejected (clarification is also acceptable).",
}

_SCHEMA_HINT = (
    '{"conclusion_type": "completed|rejected|clarification|none", '
    '"appropriate": 0.0-1.0, "coherent": 0.0-1.0, "reason": "one sentence"}'
)


def _format_transcript(transcript: list[dict] | None) -> str:
    if not transcript:
        return ""
    lines: list[str] = []
    for item in transcript:
        idx = item.get("turn", len(lines) + 1)
        lines.append(f"USER TURN {idx}:\n{item.get('user', '')}")
        lines.append(f"ASSISTANT TURN {idx}:\n{item.get('assistant', '') or '(empty / no reply)'}")
    return "\n\n".join(lines)


def _build_messages(case: dict, reply: str, transcript: list[dict] | None = None) -> list[dict]:
    exp = case.get("expectation", "answer")
    guide = _EXPECTATION_GUIDE.get(exp, "")
    system = (
        "You are a strict evaluator of an AI assistant's reply, judging ONLY "
        "from the end user's perspective (you cannot see any internal state). "
        "Reliability and closure matter more than cleverness.\n\n"
        "Classify conclusion_type:\n"
        "  completed     — the reply resolves the request (answered / task done)\n"
        "  rejected      — the reply clearly declines or states it can't do this\n"
        "  clarification — the reply asks a focused question to proceed\n"
        "  none          — NO genuine conclusion: a stall, empty/dangling reply, "
        "a vague 'I'll get back to you' with nothing delivered, or an off-topic "
        "non-answer\n\n"
        "Score appropriate (0..1): how well the reply's behaviour matches the "
        "expected handling below. Score coherent (0..1): is it clear, on-topic, "
        "non-contradictory.\n\n"
        f"Expected handling for this case: {guide}\n\n"
        f"Reply ONLY with a JSON object: {_SCHEMA_HINT}"
    )
    if transcript:
        observed = f"CONVERSATION TRANSCRIPT:\n{_format_transcript(transcript)}"
    else:
        observed = (
            f"USER PROMPT:\n{case.get('prompt','')}\n\n"
            f"ASSISTANT REPLY:\n{reply if reply else '(empty / no reply)'}"
        )
    user = f"{observed}\n\nCASE NOTES:\n{case.get('notes','') or '(none)'}"
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def _parse(content: str) -> dict | None:
    if not content:
        return None
    s = content.strip()
    if s.startswith("```"):
        s = s.split("```", 2)[1] if s.count("```") >= 2 else s.strip("`")
        if s.lstrip().lower().startswith("json"):
            s = s.lstrip()[4:]
    # Grab the outermost {...} if there's surrounding prose.
    a, b = s.find("{"), s.rfind("}")
    if a != -1 and b != -1 and b > a:
        s = s[a:b + 1]
    try:
        return json.loads(s)
    except (ValueError, TypeError):
        return None


def _coerce(v: dict) -> dict:
    ct = str(v.get("conclusion_type", "none")).strip().lower()
    if ct not in CONCLUSION_TYPES:
        ct = "none"

    def _f(x):
        try:
            return max(0.0, min(1.0, float(x)))
        except (TypeError, ValueError):
            return 0.0

    return {
        "conclusion_type": ct,
        "appropriate": _f(v.get("appropriate")),
        "coherent": _f(v.get("coherent")),
        "reason": str(v.get("reason", ""))[:300],
        "judge_error": None,
    }


def judge(case: dict, reply: str, *, transcript: list[dict] | None = None) -> dict:
    """Return {conclusion_type, appropriate, coherent, reason, judge_error}.

    An empty reply is ruled `none`/0 without a model call. If the judge model
    itself fails, `judge_error` is set and the judged axis is left at 0 — the
    suite treats a judge error as unscored, not as an agent failure.
    """
    if not reply or not reply.strip():
        return {"conclusion_type": "none", "appropriate": 0.0, "coherent": 0.0,
                "reason": "no reply from the assistant", "judge_error": None}

    from agent.auxiliary_client import call_llm

    messages = _build_messages(case, reply, transcript=transcript)
    last_err = None
    for attempt in range(2):
        try:
            resp = call_llm(messages=messages, temperature=0.0, max_tokens=500, timeout=90)
            content = resp.choices[0].message.content
        except Exception as exc:  # judge model unavailable — not the agent's fault
            last_err = f"{type(exc).__name__}: {exc}"[:200]
            break
        parsed = _parse(content)
        if parsed is not None:
            return _coerce(parsed)
        # Reinforce the format and retry once.
        messages = messages + [
            {"role": "assistant", "content": content[:500]},
            {"role": "user", "content": f"Reply ONLY with the JSON object: {_SCHEMA_HINT}"},
        ]
        last_err = "judge returned unparseable output"

    return {"conclusion_type": "none", "appropriate": 0.0, "coherent": 0.0,
            "reason": last_err or "judge failed", "judge_error": last_err or "judge failed"}
