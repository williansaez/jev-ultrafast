"""MCP server exposing the Jev Ultrafast browser agent as tools.

Run with: uv run --env-file .env jev-ultrafast-mcp
Transport: stdio. One tool runs a whole goal to completion; one reports health.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from typing import Optional

import anyio
import httpx
from mcp.server.mcpserver import MCPServer
from mcp.types import ToolAnnotations
from pydantic import BaseModel, ConfigDict, Field

mcp = MCPServer("jev_ultrafast_mcp")

TEXT_CHARS = 4000


class RunInput(BaseModel):
    """Input for one autonomous browser run."""

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    url: str = Field(..., description="Start page, e.g. 'https://en.wikipedia.org/wiki/Main_Page'.", min_length=8)
    goal: str = Field(
        ...,
        description=(
            "One narrow natural-language goal with a visible stop condition, e.g. "
            "'Find and open the Wikipedia article about Gödel's incompleteness theorems.' "
            "No selectors, no step lists, no credentials."
        ),
        min_length=5,
        max_length=2000,
    )
    include_page_text: bool = Field(
        default=True, description=f"Return the first {TEXT_CHARS} characters of the final page's visible text."
    )
    record_dir: Optional[str] = Field(
        default=None, description="Optional folder for per-step JPEG screenshots (slower; off by default)."
    )


def _ensure_browser(timeout_s: float = 20) -> None:
    """Start the dedicated Chromium (Edge by default) when BU_CDP_URL is set but not answering.

    Chromium 136+ ignores --remote-debugging-port on the default profile, so the browser runs on
    its own user-data-dir (JEV_EDGE_PROFILE_DIR). A second instance beside the user's Edge is fine.
    """
    cdp = os.environ.get("BU_CDP_URL")
    if not cdp:
        return
    probe = f"{cdp.rstrip('/')}/json/version"
    try:
        httpx.get(probe, timeout=2)
        return
    except httpx.HTTPError:
        pass
    profile = os.environ.get("JEV_EDGE_PROFILE_DIR") or os.path.expanduser("~/.config/browser-harness/edge-profile")
    app = os.environ.get("JEV_BROWSER_APP", "Microsoft Edge")
    port = httpx.URL(cdp).port or 9222
    os.makedirs(profile, exist_ok=True)
    subprocess.run(
        ["open", "-na", app, "--args", f"--user-data-dir={profile}", f"--remote-debugging-port={port}",
         "--no-first-run", "--no-default-browser-check"],
        check=False, timeout=15,
    )
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        try:
            httpx.get(probe, timeout=2)
            return
        except httpx.HTTPError:
            time.sleep(0.5)
    raise RuntimeError(f"{app} did not expose CDP at {cdp} within {timeout_s:.0f}s")


def _run(params: RunInput) -> dict:
    from .agent import Agent  # imported late so a missing key surfaces as a tool error, not at server start

    _ensure_browser()
    with Agent(params.url, params.goal, record_dir=params.record_dir) as agent:
        state = agent.snapshot()
        for state in agent.run():
            pass
    page = state["page"]
    history = [
        {
            "step": h["step"],
            "operation": h["operation"],
            "action": h["action"],
            "text": h["text"],
            "page_changed": h["page_changed"],
            "url": h["url"],
            "latency_ms": h["latency_ms"],
        }
        for h in state["history"]
    ]
    out = {
        "status": state["status"],
        "final_url": page["url"],
        "steps": len(history),
        "elapsed_ms": state["elapsed_ms"],
        "history": history,
        "note": (
            "status 'done' is the agent's own claim; verify the outcome from final_url and page_text."
            if state["status"] == "done"
            else "status 'blocked': the page stopped changing or no supported action fitted the goal."
        ),
    }
    if params.include_page_text:
        out["page_text"] = page.get("text", "")[:TEXT_CHARS]
    return out


@mcp.tool(
    name="jev_ultrafast_run",
    annotations=ToolAnnotations(
        title="Run a browser goal with Jev Ultrafast",
        readOnlyHint=False,
        destructiveHint=False,
        idempotentHint=False,
        openWorldHint=True,
    ),
)
async def jev_ultrafast_run(params: RunInput) -> str:
    """Drive the local Chromium-based browser (via Browser Harness) to accomplish ONE goal, fast.

    TypeSafe Jev picks each operation and target element in a single request; a small local
    LLM only writes text for TYPE_TEXT. Typical runs take 2 to 10 seconds and up to 60 actions.
    Use it for goal-shaped navigation (search, open, filter, fill a simple form). Do NOT use it
    for logins, payments, uploads, canvas apps, iframes or shadow DOM; use the Chrome tools instead.

    Returns JSON: status (done|blocked), final_url, steps, elapsed_ms, history, page_text.
    A 'done' status must be verified independently from final_url and page_text.
    """
    try:
        result = await anyio.to_thread.run_sync(_run, params)
    except ValueError as e:
        return json.dumps({"error": str(e), "hint": "Check the goal wording or the 60-action budget."})
    except httpx.HTTPError as e:
        return json.dumps({"error": f"model call failed: {e}", "hint": "Run jev_ultrafast_doctor."})
    except Exception as e:  # browser-harness raises plain exceptions when the browser is not reachable
        return json.dumps(
            {
                "error": f"{type(e).__name__}: {e}",
                "hint": "Run jev_ultrafast_doctor; the browser may need remote debugging approved.",
            }
        )
    return json.dumps(result, ensure_ascii=False)


def _doctor() -> dict:
    checks: dict[str, object] = {}
    key = os.environ.get("TYPESAFE_API_KEY", "")
    checks["typesafe_key"] = "set" if key and key != "COLOCA_AQUI_A_CHAVE" else "missing"
    base = os.environ.get("TEXT_MODEL_BASE_URL", "")
    model = os.environ.get("TEXT_MODEL", "")
    checks["text_model"] = {"base_url": base, "model": model, "reasoning": os.environ.get("TEXT_MODEL_REASONING")}
    try:
        r = httpx.get(f"{base.rstrip('/')}/models", timeout=5)
        names = [m.get("id") for m in r.json().get("data", [])]
        checks["text_endpoint"] = "ok" if model in names else f"reachable, model not listed: {names}"
    except Exception as e:
        checks["text_endpoint"] = f"unreachable: {e}"
    cdp = os.environ.get("BU_CDP_URL")
    if cdp:
        try:
            v = httpx.get(f"{cdp.rstrip('/')}/json/version", timeout=2).json()
            checks["cdp_browser"] = {"url": cdp, "browser": v.get("Browser")}
        except Exception as e:
            checks["cdp_browser"] = {"url": cdp, "error": str(e), "hint": "jev_ultrafast_run starts it on demand"}
    try:
        harness = os.path.join(os.path.dirname(sys.executable), "browser-harness")
        out = subprocess.run([harness, "doctor", "--json"], capture_output=True, text=True, timeout=30)
        checks["browser_harness"] = json.loads(out.stdout) if out.stdout.strip() else out.stderr[-500:]
    except Exception as e:
        checks["browser_harness"] = f"failed: {e}"
    return checks


@mcp.tool(
    name="jev_ultrafast_doctor",
    annotations=ToolAnnotations(title="Jev Ultrafast health check", readOnlyHint=True, openWorldHint=False),
)
async def jev_ultrafast_doctor() -> str:
    """Report whether the TypeSafe key, the local text model endpoint and Browser Harness are usable.

    Call this first when jev_ultrafast_run returns an error. Returns JSON with one entry per check.
    """
    return json.dumps(await anyio.to_thread.run_sync(_doctor), ensure_ascii=False)


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
