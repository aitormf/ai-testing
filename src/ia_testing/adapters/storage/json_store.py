"""JSON implementation of the ResultStore port."""

import json
from pathlib import Path

from ia_testing.domain.run import RunLocation, RunRecord, RunResult, StoreError

SCHEMA_VERSION = 1
_MAX_SUFFIX = 1000


def _path(value: Path | None) -> str | None:
    return None if value is None else str(value)


def _result_to_json(result: RunResult) -> dict[str, object]:
    return {
        "id": result.id,
        "runner": result.runner,
        "model": result.model,
        "local": result.local,
        "status": result.status.value,
        "reason": result.reason,
        "duration_s": result.duration_s,
        "worktree": _path(result.worktree),
        "branch": result.branch,
        "cost_usd": result.cost_usd,
        "input_tokens": result.input_tokens,
        "output_tokens": result.output_tokens,
        "stdout_log": _path(result.stdout_log),
        "stderr_log": _path(result.stderr_log),
    }


def _record_to_json(record: RunRecord) -> dict[str, object]:
    return {
        "schema_version": SCHEMA_VERSION,
        "run_id": record.run_id,
        "started_at": record.started_at.isoformat(),
        "task_type": record.task_type.value,
        "repo": str(record.repo),
        "ref": record.ref,
        "commit": record.commit,
        "results": [_result_to_json(r) for r in record.results],
    }


class JsonResultStore:
    def create_run(self, base_id: str, base_dir: Path) -> RunLocation:
        """Create `<base_dir>/<run-id>/` exclusively, adding `-2`, `-3`... if it exists."""
        try:
            base_dir.mkdir(parents=True, exist_ok=True)
            for attempt in range(1, _MAX_SUFFIX + 1):
                run_id = base_id if attempt == 1 else f"{base_id}-{attempt}"
                run_dir = base_dir / run_id
                try:
                    run_dir.mkdir(exist_ok=False)
                except FileExistsError:
                    continue
                (run_dir / "logs").mkdir()
                (run_dir / "worktrees").mkdir()
                return RunLocation(run_id=run_id, dir=run_dir)
        except OSError as exc:
            raise StoreError("cannot create run directory") from exc
        raise StoreError("cannot create run directory")

    def save(self, location: RunLocation, record: RunRecord) -> Path:
        """Write results.json atomically (temporary file, then rename) and return its path."""
        target = location.dir / "results.json"
        temporary = location.dir / "results.json.tmp"
        try:
            text = json.dumps(_record_to_json(record), indent=2, ensure_ascii=False)
            temporary.write_text(text + "\n", encoding="utf-8")
            temporary.replace(target)
        except OSError as exc:
            raise StoreError("cannot write results") from exc
        return target
