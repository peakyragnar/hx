from __future__ import annotations

import gzip
import json
import os
from pathlib import Path
from typing import Dict, Iterable, List, Optional

import typer


app = typer.Typer(help="Export web artifacts into analytics-friendly JSONL/Parquet files.")


def _load_manifest(path: Path) -> Dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def _load_gzip_json(path: Path) -> List[Dict[str, object]]:
    data = gzip.decompress(path.read_bytes())
    return json.loads(data.decode("utf-8"))


def _write_jsonl(path: Path, rows: Iterable[Dict[str, object]]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False))
            handle.write("\n")


def _maybe_export_parquet(jsonl_path: Path, parquet_path: Path) -> None:
    try:
        import duckdb  # type: ignore
    except ImportError as exc:  # pragma: no cover - optional dependency
        raise RuntimeError(
            "duckdb is required for Parquet export. Install with `uv add duckdb` or skip --parquet."
        ) from exc

    con = duckdb.connect()
    try:
        con.execute("CREATE TABLE tmp AS SELECT * FROM read_json_auto(?)", [str(jsonl_path)])
        con.execute("COPY tmp TO ? (FORMAT PARQUET)", [str(parquet_path)])
    finally:
        con.close()


@app.command()
def export(
    artifact_root: Path = typer.Option(
        Path(os.getenv("HERETIX_ARTIFACT_PATH", "runs/artifacts")),
        exists=True,
        file_okay=False,
        help="Root directory that contains web artifacts.",
    ),
    out_dir: Path = typer.Option(
        Path("runs/exports"),
        file_okay=False,
        help="Directory to write JSONL (and optional Parquet) exports.",
    ),
    parquet: bool = typer.Option(False, help="Also materialize Parquet files (requires duckdb)."),
) -> None:
    """
    Scan web artifact manifests and emit runs.jsonl, docs.jsonl, replicates.jsonl.
    """
    manifests = list(artifact_root.rglob("manifest.json"))
    if not manifests:
        typer.echo(f"No manifests found under {artifact_root}")
        raise typer.Exit(1)

    runs_rows: List[Dict[str, object]] = []
    docs_rows: List[Dict[str, object]] = []
    replicates_rows: List[Dict[str, object]] = []

    for path in manifests:
        manifest = _load_manifest(path)
        artifact_id = manifest.get("artifact_id")
        run_id = manifest.get("run_id")
        base_common = {
            "artifact_id": artifact_id,
            "run_id": run_id,
            "manifest_path": str(path),
        }
        runs_rows.append(
            {
                **base_common,
                "mode": manifest.get("mode"),
                "claim": manifest.get("claim"),
                "created_at": manifest.get("created_at"),
                "p_web": manifest.get("web", {}).get("p"),
                "ci_web_lo": (manifest.get("web", {}).get("ci95") or [None, None])[0],
                "ci_web_hi": (manifest.get("web", {}).get("ci95") or [None, None])[1],
                "resolved": manifest.get("web", {}).get("resolved"),
                "resolved_truth": manifest.get("web", {}).get("resolved_truth"),
                "resolved_reason": manifest.get("web", {}).get("resolved_reason"),
                "replicates_uri": manifest.get("replicates_uri"),
                "docs_uri": manifest.get("docs_uri"),
            }
        )

        docs_uri = manifest.get("docs_uri")
        if docs_uri:
            if str(docs_uri).startswith("gs://"):
                typer.echo(f"Skipping docs for {artifact_id}; gs:// export not yet supported")
                docs_payload: List[Dict[str, object]] = []
            else:
                docs_path = Path(docs_uri)
                docs_payload = _load_gzip_json(docs_path)
            for doc in docs_payload:
                docs_rows.append({**base_common, **doc})

        reps_uri = manifest.get("replicates_uri")
        if reps_uri:
            if str(reps_uri).startswith("gs://"):
                typer.echo(f"Skipping replicates for {artifact_id}; gs:// export not yet supported")
                reps_payload: List[Dict[str, object]] = []
            else:
                reps_path = Path(reps_uri)
                reps_payload = _load_gzip_json(reps_path)
            for rep in reps_payload:
                merged = {
                    **base_common,
                    **rep,
                }
                if isinstance(merged.get("docs"), list):
                    merged["docs"] = json.dumps(merged["docs"])
                replicates_rows.append(merged)

    out_dir.mkdir(parents=True, exist_ok=True)
    runs_jsonl = out_dir / "runs.jsonl"
    docs_jsonl = out_dir / "docs.jsonl"
    reps_jsonl = out_dir / "replicates.jsonl"

    _write_jsonl(runs_jsonl, runs_rows)
    _write_jsonl(docs_jsonl, docs_rows)
    _write_jsonl(reps_jsonl, replicates_rows)
    typer.echo(f"Wrote {runs_jsonl}")
    typer.echo(f"Wrote {docs_jsonl}")
    typer.echo(f"Wrote {reps_jsonl}")

    if parquet:
        _maybe_export_parquet(runs_jsonl, out_dir / "runs.parquet")
        _maybe_export_parquet(docs_jsonl, out_dir / "docs.parquet")
        _maybe_export_parquet(reps_jsonl, out_dir / "replicates.parquet")
        typer.echo("Parquet exports completed")


if __name__ == "__main__":
    app()
