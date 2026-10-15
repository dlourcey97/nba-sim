"""DATA_DIR layout, season partitions, storage cap, and the storage report.

Parquet is the only durable format. DuckDB is used in memory to write and
read those files. Nothing here stores raw API payloads or simulation draws.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Sequence

import duckdb
import pyarrow as pa

from nba_sim.errors import SeasonFrozenError, StorageCapExceeded, StorageError
from nba_sim.schema import SEASON_PATTERN, TABLES, Table
from nba_sim.settings import Settings, assert_outside_repo

_SEASON = re.compile(SEASON_PATTERN)
_COMPLETE = "_COMPLETE"
_DATA_FILE = "data.parquet"
_TMP_DIR = "_tmp"


@dataclass(frozen=True)
class WriteResult:
    table: str
    season: str
    rows_written: int
    rows_skipped: int
    path: Path | None


@dataclass(frozen=True)
class SeasonSize:
    table: str
    season: str
    num_bytes: int


@dataclass(frozen=True)
class StorageReport:
    data_dir: Path
    cap_bytes: int
    used_bytes: int
    rows: tuple[SeasonSize, ...]

    @property
    def within_cap(self) -> bool:
        return self.used_bytes <= self.cap_bytes


def format_bytes(num_bytes: int) -> str:
    size = float(num_bytes)
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if size < 1024 or unit == "TiB":
            if unit == "B":
                return f"{int(size)} B"
            return f"{size:.2f} {unit}"
        size /= 1024
    return f"{num_bytes} B"


def directory_size(path: Path) -> int:
    """Sum file sizes under path. Symlinks are not followed."""
    if not path.exists():
        return 0
    total = 0
    for root, dirs, files in os.walk(path, followlinks=False):
        dirs[:] = [name for name in dirs if not os.path.islink(os.path.join(root, name))]
        for name in files:
            file_path = Path(root) / name
            if file_path.is_symlink():
                continue
            total += file_path.stat().st_size
    return total


def partition_dir(data_dir: Path, table: str, season: str) -> Path:
    if table not in TABLES:
        raise StorageError(f"unknown table {table!r}. See SCHEMA.md.")
    if _SEASON.fullmatch(season) is None:
        raise StorageError(f"invalid season {season!r}. Expected YYYY-YY, for example 2025-26.")
    return data_dir / table / f"season={season}"


def data_file(data_dir: Path, table: str, season: str) -> Path:
    return partition_dir(data_dir, table, season) / _DATA_FILE


def cleanup_temp(data_dir: Path) -> int:
    """Delete scratch files. Returns the number of paths removed."""
    if not data_dir.exists():
        return 0
    removed = 0
    tmp_root = data_dir / _TMP_DIR
    if tmp_root.is_dir() and not tmp_root.is_symlink():
        for root, dirs, files in os.walk(tmp_root, topdown=False, followlinks=False):
            for name in files:
                Path(root, name).unlink(missing_ok=True)
                removed += 1
            for name in dirs:
                Path(root, name).rmdir()
                removed += 1
        tmp_root.rmdir()
        removed += 1
    for root, dirs, files in os.walk(data_dir, followlinks=False):
        dirs[:] = [name for name in dirs if name != _TMP_DIR and not os.path.islink(os.path.join(root, name))]
        for name in files:
            if name.endswith(".tmp"):
                Path(root, name).unlink(missing_ok=True)
                removed += 1
    return removed


def collect_storage_report(settings: Settings) -> StorageReport:
    """Byte sizes by table and season. Does not read Parquet contents."""
    data_dir = settings.data_dir
    used = directory_size(data_dir)
    rows: list[SeasonSize] = []
    seen: set[str] = set()
    if data_dir.is_dir():
        for child in sorted(data_dir.iterdir(), key=lambda path: path.name):
            if child.is_symlink():
                continue
            if child.name == _TMP_DIR and child.is_dir():
                rows.append(SeasonSize(_TMP_DIR, "-", directory_size(child)))
                continue
            if child.is_file():
                rows.append(SeasonSize("(root)", child.name, child.stat().st_size))
                continue
            if not child.is_dir():
                continue
            seen.add(child.name)
            season_rows = _season_sizes(child)
            if season_rows:
                rows.extend(season_rows)
            else:
                rows.append(SeasonSize(child.name, "-", directory_size(child)))
    for name in TABLES:
        if name not in seen:
            rows.append(SeasonSize(name, "-", 0))
    ordered = _order_rows(rows)
    return StorageReport(
        data_dir=data_dir,
        cap_bytes=settings.max_bytes,
        used_bytes=used,
        rows=tuple(ordered),
    )


def format_storage_report(report: StorageReport) -> str:
    lines = [
        f"DATA_DIR: {report.data_dir}",
        f"cap_bytes: {report.cap_bytes}",
        f"used_bytes: {report.used_bytes}",
        f"within_cap: {'yes' if report.within_cap else 'no'}",
        "",
        f"{'table':<32} {'season':<12} {'bytes':>12}  human",
    ]
    for row in report.rows:
        lines.append(
            f"{row.table:<32} {row.season:<12} {row.num_bytes:12d}  {format_bytes(row.num_bytes)}"
        )
    lines.append(
        f"{'TOTAL':<32} {'-':<12} {report.used_bytes:12d}  {format_bytes(report.used_bytes)}"
    )
    return "\n".join(lines)


def print_storage_report(report: StorageReport) -> None:
    print(format_storage_report(report))


def enforce_cap(settings: Settings, *, used: int | None = None) -> int:
    """Abort when DATA_DIR is over the configured cap. Returns the byte size."""
    size = directory_size(settings.data_dir) if used is None else used
    if size > settings.max_bytes:
        raise StorageCapExceeded(
            (
                f"Storage cap exceeded: DATA_DIR is {format_bytes(size)} ({size} bytes), "
                f"cap is {format_bytes(settings.max_bytes)} ({settings.max_bytes} bytes), "
                f"path {settings.data_dir}. Aborting instead of writing more data."
            ),
            used=size,
            cap=settings.max_bytes,
            data_dir=settings.data_dir,
        )
    return size


def finish_run(settings: Settings) -> StorageReport:
    """Delete temp files, print the storage report, and abort if over the cap."""
    assert_outside_repo(settings.data_dir, settings.repo_root)
    cleanup_temp(settings.data_dir)
    report = collect_storage_report(settings)
    print_storage_report(report)
    enforce_cap(settings, used=report.used_bytes)
    return report


def season_is_complete(settings: Settings, table: str, season: str) -> bool:
    """True when this season partition has been frozen with a _COMPLETE marker."""
    if table not in TABLES:
        raise StorageError(f"unknown table {table!r}. See SCHEMA.md.")
    return (partition_dir(settings.data_dir, table, season) / _COMPLETE).is_file()


def mark_season_complete(settings: Settings, table: str, season: str) -> Path:
    """Freeze a season so later runs cannot rewrite it."""
    _prepare_data_dir(settings)
    directory = partition_dir(settings.data_dir, table, season)
    if not (directory / _DATA_FILE).is_file():
        raise StorageError(f"cannot freeze {table} season {season}: partition has no data.parquet.")
    marker = directory / _COMPLETE
    marker.write_text("complete\n", encoding="utf-8")
    enforce_cap(settings)
    return marker


def read_rows(settings: Settings, table: str, season: str) -> list[dict[str, object]]:
    """Read one season partition through DuckDB. Empty when the file is absent."""
    spec = TABLES[table]
    path = data_file(settings.data_dir, table, season)
    loaded = _read_partition(path, spec)
    if loaded is None:
        return []
    return loaded.to_pylist()


def stored_game_ids(settings: Settings, table: str, season: str) -> set[str]:
    """Game ids already present in a table that uses game_id as part of its key."""
    spec = TABLES[table]
    if "game_id" not in spec.key:
        raise StorageError(f"{table} has no game_id key. See SCHEMA.md.")
    index = spec.key.index("game_id")
    return {str(key[index]) for key in stored_keys(settings, table, season)}


def stored_keys(settings: Settings, table: str, season: str) -> set[tuple[object, ...]]:
    """Keys already stored for a season. Empty when the partition does not exist."""
    spec = TABLES[table]
    path = data_file(settings.data_dir, table, season)
    existing = _read_partition(path, spec)
    if existing is None:
        return set()
    return {_key_at(existing, index, spec.key) for index in range(existing.num_rows)}


def list_seasons(data_dir: Path, table: str) -> list[str]:
    """Season labels present on disk for a table. Does not open Parquet files."""
    if table not in TABLES:
        raise StorageError(f"unknown table {table!r}. See SCHEMA.md.")
    parent = data_dir / table
    if not parent.is_dir():
        return []
    seasons: list[str] = []
    for child in parent.iterdir():
        if child.is_dir() and child.name.startswith("season="):
            label = child.name.split("=", 1)[1]
            if _SEASON.fullmatch(label):
                seasons.append(label)
    return sorted(seasons)


def store_rows(
    settings: Settings,
    table: str,
    season: str,
    rows: Sequence[Mapping[str, object]],
    *,
    current_season: str | None = None,
    allow_historical: bool = False,
) -> WriteResult:
    """Write rows using the table policy from SCHEMA.md."""
    spec = TABLES[table]
    active = current_season or settings.current_season
    if _SEASON.fullmatch(active) is None:
        raise StorageError(f"invalid current season {active!r}.")
    _prepare_data_dir(settings)
    directory = partition_dir(settings.data_dir, table, season)
    path = directory / _DATA_FILE
    if spec.policy != "replace":
        _reject_frozen_or_historical(
            directory,
            spec,
            season,
            active,
            allow_historical,
        )
    incoming = _rows_to_table(rows, spec, season)
    if spec.policy == "replace":
        written = _replace_partition(settings, directory, path, incoming)
        skipped = 0
    elif spec.policy == "incremental_current":
        written, skipped = _merge_new_keys(settings, directory, path, incoming, spec)
    elif spec.policy == "upsert_current":
        written, skipped = _upsert_keys(settings, directory, path, incoming, spec)
    else:
        raise StorageError(f"unsupported policy {spec.policy}")
    return WriteResult(table, season, written, skipped, path if path.is_file() else None)


def rewrite_unfrozen_rows(
    settings: Settings,
    table: str,
    season: str,
    rows: Sequence[Mapping[str, object]],
    *,
    allow_historical: bool = False,
) -> int:
    """Replace an unfrozen season file. Backfill uses this to fill a null pace."""
    spec = TABLES[table]
    active = settings.current_season
    _prepare_data_dir(settings)
    directory = partition_dir(settings.data_dir, table, season)
    path = directory / _DATA_FILE
    _reject_frozen_or_historical(directory, spec, season, active, allow_historical)
    incoming = _rows_to_table(rows, spec, season)
    _commit_table(settings, directory, path, incoming, replace_directory=False)
    return incoming.num_rows


def _prepare_data_dir(settings: Settings) -> None:
    assert_outside_repo(settings.data_dir, settings.repo_root)
    if settings.archive_dir is not None:
        assert_outside_repo(settings.archive_dir, settings.repo_root)
    enforce_cap(settings)
    settings.data_dir.mkdir(parents=True, exist_ok=True)


def _reject_frozen_or_historical(
    directory: Path,
    spec: Table,
    season: str,
    current_season: str,
    allow_historical: bool,
) -> None:
    if (directory / _COMPLETE).exists():
        raise SeasonFrozenError(
            f"{spec.name} season {season} is marked complete and cannot be rewritten."
        )
    if season != current_season and not allow_historical:
        raise StorageError(
            f"Refusing to write {spec.name} season {season} while the current season is "
            f"{current_season}. Historical writes are for backfill only (allow_historical=True). "
            "Completed seasons stay frozen once mark_season_complete has been called."
        )


def _rows_to_table(rows: Sequence[Mapping[str, object]], spec: Table, season: str) -> pa.Table:
    names = {column.name for column in spec.columns}
    normalized: list[dict[str, object]] = []
    for row in rows:
        extra = set(row) - names
        if extra:
            raise StorageError(
                f"unexpected columns for {spec.name}: {sorted(extra)}. See SCHEMA.md."
            )
        item: dict[str, object] = {}
        for column in spec.columns:
            if column.name in row:
                item[column.name] = row[column.name]
            elif column.nullable:
                item[column.name] = None
            else:
                raise StorageError(f"missing required column {column.name} for {spec.name}.")
        if item["season"] != season:
            raise StorageError(
                f"{spec.name} row season {item['season']!r} does not match partition {season!r}."
            )
        normalized.append(item)
    return pa.Table.from_pylist(normalized, schema=spec.arrow_schema())


def _replace_partition(
    settings: Settings,
    directory: Path,
    path: Path,
    incoming: pa.Table,
) -> int:
    _commit_table(settings, directory, path, incoming, replace_directory=True)
    return incoming.num_rows


def _merge_new_keys(
    settings: Settings,
    directory: Path,
    path: Path,
    incoming: pa.Table,
    spec: Table,
) -> tuple[int, int]:
    if incoming.num_rows == 0:
        return 0, 0
    _reject_duplicate_keys(incoming, spec)
    existing = _read_partition(path, spec)
    if existing is None:
        _commit_table(settings, directory, path, incoming, replace_directory=False)
        return incoming.num_rows, 0
    have = {_key_at(existing, index, spec.key) for index in range(existing.num_rows)}
    keep = [index for index in range(incoming.num_rows) if _key_at(incoming, index, spec.key) not in have]
    skipped = incoming.num_rows - len(keep)
    if not keep:
        return 0, skipped
    added = incoming.take(pa.array(keep, type=pa.int64()))
    combined = pa.concat_tables([existing, added], promote_options="none")
    _commit_table(settings, directory, path, combined, replace_directory=False)
    return len(keep), skipped


def _upsert_keys(
    settings: Settings,
    directory: Path,
    path: Path,
    incoming: pa.Table,
    spec: Table,
) -> tuple[int, int]:
    if incoming.num_rows == 0:
        return 0, 0
    _reject_duplicate_keys(incoming, spec)
    existing = _read_partition(path, spec)
    if existing is None:
        _commit_table(settings, directory, path, incoming, replace_directory=False)
        return incoming.num_rows, 0
    merged: dict[tuple[object, ...], int] = {
        _key_at(existing, index, spec.key): index for index in range(existing.num_rows)
    }
    incoming_indexes: list[int] = []
    for index in range(incoming.num_rows):
        key = _key_at(incoming, index, spec.key)
        merged[key] = -1 - len(incoming_indexes)
        incoming_indexes.append(index)
    existing_rows = []
    for index in range(existing.num_rows):
        key = _key_at(existing, index, spec.key)
        pointer = merged[key]
        if pointer >= 0:
            existing_rows.append(index)
    pieces: list[pa.Table] = []
    if existing_rows:
        pieces.append(existing.take(pa.array(existing_rows, type=pa.int64())))
    pieces.append(incoming.take(pa.array(incoming_indexes, type=pa.int64())))
    combined = pa.concat_tables(pieces, promote_options="none")
    _commit_table(settings, directory, path, combined, replace_directory=False)
    return incoming.num_rows, 0


def _reject_duplicate_keys(table: pa.Table, spec: Table) -> None:
    seen: set[tuple[object, ...]] = set()
    for index in range(table.num_rows):
        key = _key_at(table, index, spec.key)
        if key in seen:
            raise StorageError(f"duplicate key {key!r} in {spec.name} batch.")
        seen.add(key)


def _key_at(table: pa.Table, index: int, key: tuple[str, ...]) -> tuple[object, ...]:
    return tuple(table.column(name)[index].as_py() for name in key)


def _commit_table(
    settings: Settings,
    directory: Path,
    path: Path,
    table: pa.Table,
    *,
    replace_directory: bool,
) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    tmp = directory / f"{_DATA_FILE}.tmp"
    _write_parquet(table, tmp)
    if replace_directory:
        old_bytes = _partition_bytes(directory, exclude=tmp)
    elif path.exists():
        old_bytes = path.stat().st_size
    else:
        old_bytes = 0
    projected = directory_size(settings.data_dir) - old_bytes
    if projected > settings.max_bytes:
        tmp.unlink(missing_ok=True)
        _prune_empty(directory, settings.data_dir)
        raise StorageCapExceeded(
            (
                f"Storage cap exceeded: writing {path.parent.name} would make DATA_DIR "
                f"{format_bytes(projected)} ({projected} bytes), cap is "
                f"{format_bytes(settings.max_bytes)} ({settings.max_bytes} bytes), "
                f"path {settings.data_dir}. The new file was discarded."
            ),
            used=projected,
            cap=settings.max_bytes,
            data_dir=settings.data_dir,
        )
    os.replace(tmp, path)
    if replace_directory:
        for child in list(directory.iterdir()):
            if child == path or child.is_symlink() or not child.is_file():
                continue
            child.unlink()


def _prune_empty(directory: Path, stop: Path) -> None:
    current = directory
    boundary = stop.resolve()
    while current.exists() and current.resolve() != boundary:
        if any(current.iterdir()):
            return
        current.rmdir()
        current = current.parent


def _partition_bytes(directory: Path, *, exclude: Path) -> int:
    total = 0
    for child in directory.iterdir():
        if child == exclude or child.is_symlink() or not child.is_file():
            continue
        total += child.stat().st_size
    return total


def _write_parquet(table: pa.Table, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    text = str(dest)
    if "'" in text or "\n" in text:
        raise StorageError(f"refusing to write parquet to {dest}.")
    with duckdb.connect(database=":memory:") as connection:
        connection.register("batch", table)
        connection.execute(f"COPY batch TO '{text}' (FORMAT PARQUET, COMPRESSION ZSTD)")


def _read_partition(path: Path, spec: Table) -> pa.Table | None:
    if not path.is_file():
        return None
    text = str(path)
    if "'" in text or "\n" in text:
        raise StorageError(f"refusing to read parquet at {path}.")
    column_list = ", ".join(f'"{column.name}"' for column in spec.columns)
    with duckdb.connect(database=":memory:") as connection:
        arrow = connection.execute(
            f"SELECT {column_list} FROM read_parquet(?)",
            [text],
        ).to_arrow_table()
    return _align(arrow, spec.arrow_schema())


def _align(table: pa.Table, schema: pa.Schema) -> pa.Table:
    arrays = []
    for field in schema:
        arrays.append(table.column(field.name).cast(field.type, safe=False))
    return pa.Table.from_arrays(arrays, schema=schema)


def _season_sizes(table_dir: Path) -> list[SeasonSize]:
    rows: list[SeasonSize] = []
    loose = 0
    for child in table_dir.iterdir():
        if child.is_symlink():
            continue
        if child.is_dir() and child.name.startswith("season="):
            label = child.name.split("=", 1)[1]
            rows.append(SeasonSize(table_dir.name, label, directory_size(child)))
        elif child.is_file():
            loose += child.stat().st_size
        elif child.is_dir():
            loose += directory_size(child)
    if loose:
        rows.append(SeasonSize(table_dir.name, "(other)", loose))
    return rows


def _order_rows(rows: list[SeasonSize]) -> list[SeasonSize]:
    known = list(TABLES)
    def sort_key(row: SeasonSize) -> tuple[int, str, str]:
        if row.table in TABLES:
            group = known.index(row.table)
        elif row.table == _TMP_DIR:
            group = len(known) + 1
        elif row.table == "(root)":
            group = len(known) + 2
        else:
            group = len(known)
        return group, row.table, row.season
    return sorted(rows, key=sort_key)
