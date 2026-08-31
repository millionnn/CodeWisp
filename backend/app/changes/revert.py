"""Revert：将 AgentStep / AgentRun 的写修改恢复到 Snapshot（不删历史）。"""

from __future__ import annotations

from datetime import datetime, timezone

from backend.app.agent.event_sink import AgentEventSink, NullEventSink
from backend.app.agent.events import AgentEvent
from backend.app.changes.apply import apply_snapshot_to_workspace
from backend.app.changes.errors import RevertDeniedError, RevertError, RestoreError
from backend.app.changes.models import RevertReport, SnapshotFile, WorkspaceSnapshot
from backend.app.persistence.snapshot_repository import SnapshotRepository
from backend.app.permissions.decision import PermissionDecision
from backend.app.permissions.handler import PermissionHandler
from backend.app.permissions.request import PermissionRequest
from backend.app.session.models import AgentRun, AgentStep
from backend.app.workspace.workspace import Workspace


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()

#回滚逻辑：先拍安全快照 → 问权限 → 恢复 → 记审计
class RevertService:
    """基于 pre_step Snapshot 恢复工作区；经 PermissionHandler 与 Workspace。"""

    def __init__(
        self,
        workspace: Workspace,
        snapshots: SnapshotRepository,
        *,
        permission_handler: PermissionHandler | None = None,
        event_sink: AgentEventSink | None = None,
    ) -> None:
        self._workspace = workspace
        self._snapshots = snapshots
        self._permission_handler = permission_handler
        self._event_sink: AgentEventSink = event_sink or NullEventSink()

    def revert_step(
        self,
        step: AgentStep,
        *,
        session_workspace: str,
    ) -> RevertReport:
        """恢复指定 Step 对工作区的修改（restore pre_step）。"""
        self._validate_workspace(session_workspace)
        before, _after = self._snapshots.get_step_boundary_snapshots(step.step_id)
        if before is None:
            raise RevertError(f"AgentStep 无可恢复的写操作快照: {step.step_id}")

        return self._revert_snapshots(
            target_type="step",
            target_id=step.step_id,
            targets=[before],
            session_id=step.session_id,
            agent_run_id=step.agent_run_id,
            agent_step_id=step.step_id,
            tool_name="revert_step",
            reason=f"Revert AgentStep {step.step_id}（恢复至 pre_step）",
        )

    def revert_run(
        self,
        run: AgentRun,
        steps: list[AgentStep],
        *,
        session_workspace: str,
    ) -> RevertReport:
        """按 step_index 倒序恢复该 Run 内各 Step 的 pre_step。"""
        self._validate_workspace(session_workspace)
        ordered = sorted(steps, key=lambda s: s.step_index, reverse=True)
        targets: list[WorkspaceSnapshot] = []
        for step in ordered:
            before, _ = self._snapshots.get_step_boundary_snapshots(step.step_id)
            if before is not None:
                targets.append(before)
        if not targets:
            raise RevertError(f"AgentRun 无可恢复的写操作快照: {run.agent_run_id}")

        return self._revert_snapshots(
            target_type="run",
            target_id=run.agent_run_id,
            targets=targets,
            session_id=run.session_id,
            agent_run_id=run.agent_run_id,
            agent_step_id=None,
            tool_name="revert_run",
            reason=f"Revert AgentRun {run.agent_run_id}（倒序恢复各 pre_step）",
        )

    def _revert_snapshots(
        self,
        *,
        target_type: str,
        target_id: str,
        targets: list[WorkspaceSnapshot],
        session_id: str,
        agent_run_id: str,
        agent_step_id: str | None,
        tool_name: str,
        reason: str,
    ) -> RevertReport:
        paths = sorted({f.path for snap in targets for f in snap.files})
        if not self._ask_permission(
            tool_name=tool_name,
            target_id=target_id,
            paths=paths,
            reason=reason,
            session_id=session_id,
            agent_run_id=agent_run_id,
        ):
            self._emit(
                "revert_failed",
                metadata={
                    "target_type": target_type,
                    "target_id": target_id,
                    "denied": True,
                },
            )
            return RevertReport(
                target_type=target_type,
                target_id=target_id,
                safety_snapshot_id=None,
                restored_snapshot_ids=tuple(s.snapshot_id for s in targets),
                applied=(),
                failed=(),
                denied=True,
            )

        self._emit(
            "revert_started",
            metadata={
                "target_type": target_type,
                "target_id": target_id,
                "paths": paths,
                "snapshot_ids": [s.snapshot_id for s in targets],
            },
        )

        try:
            safety = self._capture_safety(
                paths,
                session_id=session_id,
                agent_run_id=agent_run_id,
                agent_step_id=agent_step_id,
            )
            self._emit(
                "snapshot_created",
                metadata={
                    "snapshot_id": safety.snapshot_id,
                    "reason": safety.reason,
                    "paths": [f.path for f in safety.files],
                },
            )

            applied: list[str] = []
            failed: list[tuple[str, str]] = []
            restored_ids: list[str] = []
            for snap in targets:
                report = apply_snapshot_to_workspace(self._workspace, snap)
                restored_ids.append(snap.snapshot_id)
                applied.extend(report.applied)
                failed.extend(report.failed)

            # 审计：revert 后状态快照（历史仍保留）
            self._capture_safety(
                paths,
                session_id=session_id,
                agent_run_id=agent_run_id,
                agent_step_id=agent_step_id,
                reason="post_revert",
            )

            result = RevertReport(
                target_type=target_type,
                target_id=target_id,
                safety_snapshot_id=safety.snapshot_id,
                restored_snapshot_ids=tuple(restored_ids),
                applied=tuple(dict.fromkeys(applied)),
                failed=tuple(failed),
            )
            if result.ok:
                self._emit(
                    "revert_completed",
                    metadata={
                        "target_type": target_type,
                        "target_id": target_id,
                        "safety_snapshot_id": safety.snapshot_id,
                        "applied": list(result.applied),
                    },
                )
            else:
                self._emit(
                    "revert_failed",
                    metadata={
                        "target_type": target_type,
                        "target_id": target_id,
                        "failed": [{"path": p, "error": e} for p, e in result.failed],
                    },
                )
            return result
        except (RestoreError, RevertError, OSError) as exc:
            self._emit(
                "revert_failed",
                metadata={
                    "target_type": target_type,
                    "target_id": target_id,
                    "error": str(exc),
                },
            )
            raise

    def _ask_permission(
        self,
        *,
        tool_name: str,
        target_id: str,
        paths: list[str],
        reason: str,
        session_id: str,
        agent_run_id: str,
    ) -> bool:
        handler = self._permission_handler
        if handler is None:
            return True
        req = PermissionRequest(
            command="revert",
            args=(target_id, *paths[:20]),
            cwd=".",
            reason=reason,
            tool_name=tool_name,
            session_id=session_id,
            agent_run_id=agent_run_id,
        )
        decision = handler.request(req)
        if decision is PermissionDecision.ALLOW:
            return True
        if decision is PermissionDecision.DENY:
            return False
        raise RevertDeniedError(f"未知授权决定: {decision}")

    def _capture_safety(
        self,
        paths: list[str],
        *,
        session_id: str,
        agent_run_id: str,
        agent_step_id: str | None,
        reason: str = "pre_revert",
    ) -> WorkspaceSnapshot:
        files: list[SnapshotFile] = []
        for path in paths:
            state = self._workspace.read_text_state(path)
            if state["exists"]:
                files.append(SnapshotFile.present(state["path"], state["content"]))
            else:
                files.append(SnapshotFile.absent(state["path"]))
        snap = WorkspaceSnapshot.create(
            workspace_root=str(self._workspace.root),
            files=files,
            reason=reason,
            session_id=session_id,
            agent_run_id=agent_run_id,
            agent_step_id=agent_step_id,
            created_at=_utc_now_iso(),
        )
        return self._snapshots.save_snapshot(snap)

    def _validate_workspace(self, session_workspace: str) -> None:
        from pathlib import Path

        expected = str(Path(session_workspace).expanduser().resolve())
        actual = str(self._workspace.root)
        if expected != actual:
            raise RevertError(
                f"Session workspace 与当前 Workspace 不一致: {expected!r} vs {actual!r}"
            )

    def _emit(self, event_type: str, *, metadata: dict) -> None:
        self._event_sink.emit(
            AgentEvent(event_type=event_type, step=0, metadata=metadata)
        )
