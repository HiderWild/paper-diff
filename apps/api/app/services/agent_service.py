"""Agent analyze / propose / apply / chat (stub provider by default)."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from app.core.config import Settings
from app.core.errors import AppError
from app.infra.workspace_fs import Workspace
from app.services.project_service import ProjectService


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class AgentService:
    def __init__(self, settings: Settings):
        self.settings = settings

    def _ws(self, project_id: str) -> Workspace:
        return Workspace(self.settings.workspace_root, project_id)

    def _require_project(self, project_id: str) -> Workspace:
        ws = self._ws(project_id)
        if not ws.meta_path.exists():
            raise AppError("PROJECT_NOT_FOUND", "project not found", status_code=404)
        return ws

    def _provider_mode(self) -> str:
        """Return stub | off | http."""
        provider = (self.settings.agent_provider or "stub").strip().lower()
        if provider in ("off", "disabled", "none"):
            return "off"
        if provider == "http":
            if self.settings.agent_api_key:
                return "http"
            # no key → fall through to stub if allowed
            if self.settings.agent_stub:
                return "stub"
            return "off"
        if provider == "stub" or self.settings.agent_stub:
            return "stub"
        return "off"

    def _not_configured(self, project_id: str) -> dict:
        return {
            "status": "not_configured",
            "message": "Agent provider not configured. Set PAPER_DIFF_AGENT_PROVIDER=stub|http.",
            "project_id": project_id,
        }

    def analyze(
        self,
        project_id: str,
        path: str | None = None,
        left_text: str | None = None,
        right_text: str | None = None,
        units: list[dict] | None = None,
        zone_id: str | None = None,
    ) -> dict:
        mode = self._provider_mode()
        if mode == "off":
            return self._not_configured(project_id)
        self._require_project(project_id)

        left = left_text or ""
        right = right_text or ""
        unit_count = len(units or [])
        left_len = len(left)
        right_len = len(right)
        delta = right_len - left_len

        summary_parts = []
        if path:
            summary_parts.append(f"Path: {path}.")
        if zone_id:
            summary_parts.append(f"Zone: {zone_id}.")
        summary_parts.append(
            f"Compared spans: {unit_count} unit(s); left {left_len} chars, right {right_len} chars."
        )
        if delta > 0:
            summary_parts.append(f"Right side is longer by {delta} characters.")
        elif delta < 0:
            summary_parts.append(f"Right side is shorter by {-delta} characters.")
        else:
            summary_parts.append("Sides have equal length.")

        left_strengths = []
        right_strengths = []
        if left_len and left_len <= right_len:
            left_strengths.append("Concise relative to the revision.")
        if right_len and right_len >= left_len:
            right_strengths.append("May introduce additional detail or corrections.")
        if unit_count:
            right_strengths.append(f"{unit_count} discrete change unit(s) identified.")
        if not left_strengths:
            left_strengths.append("Baseline work content available for review.")
        if not right_strengths:
            right_strengths.append("Compare zone or proposal available as alternative.")

        risks = []
        if unit_count > 20:
            risks.append("Large number of units — review for unintended rewrites.")
        if abs(delta) > 500:
            risks.append("Substantial length change — check section structure.")
        if not risks:
            risks.append("No automatic high-severity risks detected (stub heuristic).")

        recommendations = [
            "Spot-check scientific claims and citations after accepting.",
            "Prefer unit-level accepts for mixed-quality revisions.",
        ]
        if unit_count:
            recommendations.append("Start with high-impact units (abstract/intro/method).")

        return {
            "status": "ok",
            "provider": "stub",
            "project_id": project_id,
            "path": path,
            "zone_id": zone_id,
            "summary": " ".join(summary_parts),
            "left_strengths": left_strengths,
            "right_strengths": right_strengths,
            "risks": risks,
            "recommendations": recommendations,
            "stats": {
                "units": unit_count,
                "left_chars": left_len,
                "right_chars": right_len,
            },
        }

    def propose(
        self,
        project_id: str,
        path: str | None = None,
        left_text: str | None = None,
        right_text: str | None = None,
        units: list[dict] | None = None,
        zone_id: str | None = None,
        instruction: str = "",
    ) -> dict:
        mode = self._provider_mode()
        if mode == "off":
            return self._not_configured(project_id)
        self._require_project(project_id)

        draft_id = uuid.uuid4().hex[:12]
        preferred = right_text if right_text is not None else left_text
        if preferred is None:
            preferred = ""
        comment = (
            f"% paper-diff agent draft ({draft_id})"
            + (f": {instruction.strip()}" if instruction and instruction.strip() else "")
            + "\n"
        )
        proposed = comment + preferred
        rationale = "Stub: prefer right-side text (or left if right missing), prepend draft comment."
        if instruction and instruction.strip():
            rationale += f" Instruction noted: {instruction.strip()[:200]}"

        return {
            "status": "ok",
            "provider": "stub",
            "draft_id": draft_id,
            "path": path,
            "proposed_content": proposed,
            "rationale": rationale,
            "zone_id": zone_id,
            "project_id": project_id,
        }

    def apply(
        self,
        project_id: str,
        path: str,
        content: str,
        expected_revision: int = 0,
    ) -> dict:
        mode = self._provider_mode()
        if mode == "off":
            return self._not_configured(project_id)
        if not path:
            raise AppError("VALIDATION_ERROR", "path required", status_code=422)
        if content is None:
            raise AppError("VALIDATION_ERROR", "content required", status_code=422)

        ws = self._require_project(project_id)
        meta = ws.load_meta()
        current = meta.get("revisions", {}).get(path, 0)
        if expected_revision and expected_revision != current:
            raise AppError(
                "REVISION_MISMATCH",
                "work file revision mismatch",
                status_code=409,
                details={"expected": expected_revision, "actual": current},
            )

        psvc = ProjectService(self.settings)
        written = psvc.put_work_file(project_id, path, content)

        def mut(m: dict) -> dict:
            log = m.setdefault("agent_log", [])
            log.append(
                {
                    "action": "apply",
                    "path": path,
                    "revision": written.get("revision"),
                    "at": _now_iso(),
                    "provider": "stub",
                }
            )
            # keep bounded
            if len(log) > 200:
                m["agent_log"] = log[-200:]
            return m

        ws.mutate_meta(mut)
        return {
            "status": "ok",
            "provider": "stub",
            "project_id": project_id,
            "path": path,
            "revision": written.get("revision"),
            "sha256": written.get("sha256"),
        }

    def chat(
        self,
        project_id: str,
        message: str,
        path: str | None = None,
        selection: str | None = None,
        zone_id: str | None = None,
    ) -> dict:
        mode = self._provider_mode()
        if mode == "off":
            return self._not_configured(project_id)
        self._require_project(project_id)
        msg = (message or "").strip()
        if not msg:
            raise AppError("VALIDATION_ERROR", "message required", status_code=422)

        bits = [f"You said: {msg[:500]}"]
        if path:
            bits.append(f"Regarding path `{path}`.")
        if zone_id:
            bits.append(f"Active zone context: {zone_id}.")
        if selection:
            snip = selection[:200].replace("\n", " ")
            bits.append(f'Selection preview: "{snip}{"…" if len(selection) > 200 else ""}".')
        bits.append(
            "Stub agent: configure PAPER_DIFF_AGENT_PROVIDER=http and an API key for real LLM replies."
        )
        reply = " ".join(bits)
        suggested_patch = None
        if selection and path:
            suggested_patch = {
                "path": path,
                "note": "stub does not rewrite selection; use /agent/propose for a full draft",
            }
        return {
            "status": "ok",
            "provider": "stub",
            "project_id": project_id,
            "reply": reply,
            "suggested_patch": suggested_patch,
        }

    def chat_stream_events(
        self,
        project_id: str,
        message: str,
        path: str | None = None,
        selection: str | None = None,
        zone_id: str | None = None,
    ) -> list[dict]:
        """Return a short list of SSE-like events for streaming stub."""
        body = self.chat(
            project_id,
            message=message,
            path=path,
            selection=selection,
            zone_id=zone_id,
        )
        if body.get("status") != "ok":
            return [
                {"event": "error", "data": body},
                {"event": "done", "data": {"status": body.get("status")}},
            ]
        reply = body.get("reply") or ""
        mid = max(1, len(reply) // 2)
        return [
            {"event": "token", "data": {"text": reply[:mid]}},
            {"event": "token", "data": {"text": reply[mid:]}},
            {
                "event": "message",
                "data": {
                    "reply": reply,
                    "suggested_patch": body.get("suggested_patch"),
                    "provider": body.get("provider"),
                },
            },
            {"event": "done", "data": {"status": "ok"}},
        ]

    def list_sessions(self, project_id: str) -> dict:
        ws = self._require_project(project_id)
        meta = ws.load_meta()
        log = meta.get("agent_log") or []
        return {"project_id": project_id, "sessions": [], "agent_log": log[-50:]}
