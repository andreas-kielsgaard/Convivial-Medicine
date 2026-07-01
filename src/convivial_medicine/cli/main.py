from __future__ import annotations

from pathlib import Path
from typing import Annotated, NoReturn

import typer

from convivial_medicine import __version__
from convivial_medicine.adapters.pubmed.efetch import (
    PUBMED_EFETCH_ENDPOINT,
    PubMedEFetchAdapterResult,
    build_efetch_params,
    process_efetch_response_bytes,
    run_efetch,
)
from convivial_medicine.adapters.pubmed.errors import PubMedHTTPStatusError
from convivial_medicine.adapters.pubmed.esearch import (
    PUBMED_ESEARCH_ENDPOINT,
    PubMedESearchAdapterResult,
    build_esearch_params,
    process_esearch_response_bytes,
    run_esearch,
)
from convivial_medicine.adapters.pubmed.esummary import (
    PUBMED_ESUMMARY_ENDPOINT,
    PubMedESummaryAdapterResult,
    build_esummary_params,
    process_esummary_response_bytes,
    run_esummary,
)
from convivial_medicine.adapters.pubmed.persistence import (
    persist_pubmed_efetch_result,
    persist_pubmed_esearch_result,
    persist_pubmed_esummary_result,
)
from convivial_medicine.config import Settings, get_settings
from convivial_medicine.domain.manifests import QueryManifest, load_query_manifest
from convivial_medicine.storage.artifacts import LocalArtifactStore
from convivial_medicine.storage.db import (
    DatabaseConnectionError,
    check_database_connection,
    make_engine,
    make_session_factory,
)

DEFAULT_QUERY_MANIFEST_PATH = Path("manifests/vitamin_D_ms_seed_v1.json")
DEFAULT_ARTIFACT_ROOT = Path(".artifacts")

app = typer.Typer(
    name="corpus",
    help="Convivial Medicine corpus constructor.",
    no_args_is_help=True,
)
query_app = typer.Typer(help="Prepare source membership queries.", no_args_is_help=True)
build_app = typer.Typer(help="Coordinate reproducible corpus builds.", no_args_is_help=True)
fetch_app = typer.Typer(
    help="Fetch source records through approved adapters.", no_args_is_help=True
)
enrich_app = typer.Typer(
    help="Enrich selected records without defining membership.", no_args_is_help=True
)
validate_app = typer.Typer(help="Validate build state and artifacts.", no_args_is_help=True)
export_app = typer.Typer(help="Export reproducible corpus slices.", no_args_is_help=True)
audit_app = typer.Typer(help="Audit corpus lineage and provenance.", no_args_is_help=True)


def _not_implemented(command: str) -> None:
    typer.echo(f"{command} is not implemented in this bootstrap branch.")


@app.command()
def doctor(
    check_db: bool = typer.Option(
        False,
        "--check-db",
        help="Attempt a live database connection.",
    ),
) -> None:
    """Print basic package and configuration checks."""
    settings = get_settings()
    typer.echo(f"package: convivial_medicine {__version__}")
    typer.echo(f"database_url: {'set' if settings.database_url else 'missing'}")
    typer.echo(f"object_store_endpoint: {'set' if settings.object_store_endpoint else 'missing'}")
    typer.echo(f"object_store_bucket: {'set' if settings.object_store_bucket else 'missing'}")
    typer.echo(
        f"object_store_access_key: {'set' if settings.object_store_access_key else 'missing'}"
    )
    typer.echo(
        f"object_store_secret_key: {'set' if settings.object_store_secret_key else 'missing'}"
    )
    typer.echo(f"ncbi_tool: {'set' if settings.ncbi_tool else 'missing'}")
    typer.echo(f"ncbi_email: {'set' if settings.ncbi_email else 'missing'}")
    if check_db:
        try:
            result = check_database_connection(settings)
        except DatabaseConnectionError as exc:
            typer.echo(f"database_connection: failed ({exc})")
            raise typer.Exit(code=1) from exc
        typer.echo(f"database_connection: ok ({result.dialect})")
    else:
        typer.echo("database_connection: skipped")
    typer.echo("status: ok")


@query_app.command("pubmed")
def query_pubmed(
    manifest: Annotated[
        Path,
        typer.Option("--manifest", help="Query manifest to execute or replay."),
    ] = DEFAULT_QUERY_MANIFEST_PATH,
    artifact_root: Annotated[
        Path,
        typer.Option("--artifact-root", help="Local content-addressed artifact root."),
    ] = DEFAULT_ARTIFACT_ROOT,
    live: Annotated[
        bool,
        typer.Option("--live", help="Make a live PubMed ESearch network call."),
    ] = False,
    fixture: Annotated[
        Path | None,
        typer.Option(
            "--fixture",
            help="Read saved PubMed ESearch response bytes instead of calling the network.",
        ),
    ] = None,
    persist_db: Annotated[
        bool,
        typer.Option(
            "--persist-db",
            help="Persist query, source snapshot, and snapshot manifest rows to Postgres.",
        ),
    ] = False,
) -> None:
    """Prepare a PubMed membership query."""
    if live and fixture is not None:
        typer.echo("Use either --live or --fixture, not both.", err=True)
        raise typer.Exit(code=2)

    if not live and fixture is None:
        typer.echo(
            "No PubMed query run. Pass --fixture PATH to replay bytes or --live to call NCBI."
        )
        return

    query_manifest = load_query_manifest(manifest)
    artifact_store = LocalArtifactStore(artifact_root)
    settings = get_settings()

    if persist_db:
        try:
            check_database_connection(settings)
        except DatabaseConnectionError as exc:
            typer.echo(f"database_persistence: failed ({exc})", err=True)
            raise typer.Exit(code=1) from exc

    if fixture is not None:
        result = process_esearch_response_bytes(
            raw_bytes=fixture.read_bytes(),
            artifact_store=artifact_store,
            endpoint=PUBMED_ESEARCH_ENDPOINT,
            request_params=build_esearch_params(query_manifest),
            http_status=200,
            content_type="application/json",
        )
        _persist_pubmed_esearch_if_requested(
            persist_db=persist_db,
            query_manifest=query_manifest,
            result=result,
            settings=settings,
        )
        _print_pubmed_esearch_summary(result, db_persisted=persist_db)
        return

    if not settings.ncbi_email:
        typer.echo("NCBI_EMAIL is required for --live PubMed ESearch calls.", err=True)
        raise typer.Exit(code=1)

    try:
        result = run_esearch(
            manifest=query_manifest,
            artifact_store=artifact_store,
            settings=settings,
        )
    except PubMedHTTPStatusError as exc:
        _exit_pubmed_http_status_error(exc)
    _persist_pubmed_esearch_if_requested(
        persist_db=persist_db,
        query_manifest=query_manifest,
        result=result,
        settings=settings,
    )
    _print_pubmed_esearch_summary(result, db_persisted=persist_db)


def _persist_pubmed_esearch_if_requested(
    *,
    persist_db: bool,
    query_manifest: QueryManifest,
    result: PubMedESearchAdapterResult,
    settings: Settings,
) -> None:
    if not persist_db:
        return

    engine = make_engine(settings)
    try:
        session_factory = make_session_factory(engine=engine)
        with session_factory.begin() as session:
            persist_pubmed_esearch_result(
                session,
                query_manifest=query_manifest,
                result=result,
            )
    finally:
        engine.dispose()


def _print_pubmed_esearch_summary(
    result: PubMedESearchAdapterResult,
    *,
    db_persisted: bool,
) -> None:
    parsed = result.parsed
    typer.echo(f"count: {parsed.count}")
    typer.echo(f"pmids_returned: {len(parsed.pmids)}")
    typer.echo(f"webenv_present: {parsed.webenv is not None}")
    typer.echo(f"query_key_present: {parsed.query_key is not None}")
    typer.echo(f"raw_payload_hash: {parsed.raw_payload_hash}")
    typer.echo(f"manifest_hash: {parsed.source_snapshot_manifest_hash}")
    typer.echo(f"db_persisted: {db_persisted}")


@build_app.command("seed")
def build_seed() -> None:
    """Build a named seed corpus."""
    _not_implemented("corpus build seed")


@fetch_app.command("pubmed-summary")
def fetch_pubmed_summary(
    pmids: Annotated[
        str | None,
        typer.Option("--pmids", help="Comma-separated PubMed IDs to summarize."),
    ] = None,
    artifact_root: Annotated[
        Path,
        typer.Option("--artifact-root", help="Local content-addressed artifact root."),
    ] = DEFAULT_ARTIFACT_ROOT,
    live: Annotated[
        bool,
        typer.Option("--live", help="Make a live PubMed ESummary network call."),
    ] = False,
    fixture: Annotated[
        Path | None,
        typer.Option(
            "--fixture",
            help="Read saved PubMed ESummary response bytes instead of calling the network.",
        ),
    ] = None,
    persist_db: Annotated[
        bool,
        typer.Option(
            "--persist-db",
            help="Persist source snapshot and snapshot manifest rows to Postgres.",
        ),
    ] = False,
) -> None:
    """Fetch PubMed summary data for selected records."""
    if live and fixture is not None:
        typer.echo("Use either --live or --fixture, not both.", err=True)
        raise typer.Exit(code=2)

    if not live and fixture is None:
        typer.echo(
            "No PubMed summary fetch run. Pass --pmids IDS with --fixture PATH "
            "to replay bytes or --live to call NCBI."
        )
        return

    requested_pmids = _parse_pmids_option(pmids)
    if not requested_pmids:
        typer.echo("--pmids must include at least one PMID.", err=True)
        raise typer.Exit(code=2)

    settings = get_settings()
    artifact_store = LocalArtifactStore(artifact_root)

    if persist_db:
        try:
            check_database_connection(settings)
        except DatabaseConnectionError as exc:
            typer.echo(f"database_persistence: failed ({exc})", err=True)
            raise typer.Exit(code=1) from exc

    if fixture is not None:
        result = process_esummary_response_bytes(
            raw_bytes=fixture.read_bytes(),
            artifact_store=artifact_store,
            endpoint=PUBMED_ESUMMARY_ENDPOINT,
            request_params=build_esummary_params(requested_pmids),
            requested_pmids=requested_pmids,
            http_status=200,
            content_type="application/json",
        )
        _persist_pubmed_esummary_if_requested(
            persist_db=persist_db,
            result=result,
            settings=settings,
        )
        _print_pubmed_esummary_summary(result, db_persisted=persist_db)
        return

    if not settings.ncbi_email:
        typer.echo("NCBI_EMAIL is required for --live PubMed ESummary calls.", err=True)
        raise typer.Exit(code=1)

    try:
        result = run_esummary(
            pmids=requested_pmids,
            artifact_store=artifact_store,
            settings=settings,
        )
    except PubMedHTTPStatusError as exc:
        _exit_pubmed_http_status_error(exc)
    _persist_pubmed_esummary_if_requested(
        persist_db=persist_db,
        result=result,
        settings=settings,
    )
    _print_pubmed_esummary_summary(result, db_persisted=persist_db)


def _parse_pmids_option(pmids: str | None) -> tuple[str, ...]:
    if pmids is None:
        return ()
    return tuple(pmid.strip() for pmid in pmids.split(",") if pmid.strip())


def _persist_pubmed_esummary_if_requested(
    *,
    persist_db: bool,
    result: PubMedESummaryAdapterResult,
    settings: Settings,
) -> None:
    if not persist_db:
        return

    engine = make_engine(settings)
    try:
        session_factory = make_session_factory(engine=engine)
        with session_factory.begin() as session:
            persist_pubmed_esummary_result(session, result=result)
    finally:
        engine.dispose()


def _print_pubmed_esummary_summary(
    result: PubMedESummaryAdapterResult,
    *,
    db_persisted: bool,
) -> None:
    parsed = result.parsed
    typer.echo(f"summaries_returned: {parsed.summaries_returned}")
    typer.echo(f"pmids_returned: {len(parsed.returned_pmids)}")
    typer.echo(f"raw_payload_hash: {parsed.raw_payload_hash}")
    typer.echo(f"manifest_hash: {parsed.source_snapshot_manifest_hash}")
    typer.echo(f"db_persisted: {db_persisted}")


@fetch_app.command("pubmed-records")
def fetch_pubmed_records(
    pmids: Annotated[
        str | None,
        typer.Option("--pmids", help="Comma-separated PubMed IDs to fetch."),
    ] = None,
    artifact_root: Annotated[
        Path,
        typer.Option("--artifact-root", help="Local content-addressed artifact root."),
    ] = DEFAULT_ARTIFACT_ROOT,
    live: Annotated[
        bool,
        typer.Option("--live", help="Make a live PubMed EFetch network call."),
    ] = False,
    fixture: Annotated[
        Path | None,
        typer.Option(
            "--fixture",
            help="Read saved PubMed EFetch response bytes instead of calling the network.",
        ),
    ] = None,
    persist_db: Annotated[
        bool,
        typer.Option(
            "--persist-db",
            help="Persist source snapshot and snapshot manifest rows to Postgres.",
        ),
    ] = False,
) -> None:
    """Fetch PubMed record data for selected records."""
    if live and fixture is not None:
        typer.echo("Use either --live or --fixture, not both.", err=True)
        raise typer.Exit(code=2)

    if not live and fixture is None:
        typer.echo(
            "No PubMed record fetch run. Pass --pmids IDS with --fixture PATH "
            "to replay bytes or --live to call NCBI."
        )
        return

    requested_pmids = _parse_pmids_option(pmids)
    if not requested_pmids:
        typer.echo("--pmids must include at least one PMID.", err=True)
        raise typer.Exit(code=2)

    settings = get_settings()
    artifact_store = LocalArtifactStore(artifact_root)

    if persist_db:
        try:
            check_database_connection(settings)
        except DatabaseConnectionError as exc:
            typer.echo(f"database_persistence: failed ({exc})", err=True)
            raise typer.Exit(code=1) from exc

    if fixture is not None:
        result = process_efetch_response_bytes(
            raw_bytes=fixture.read_bytes(),
            artifact_store=artifact_store,
            endpoint=PUBMED_EFETCH_ENDPOINT,
            request_params=build_efetch_params(requested_pmids),
            requested_pmids=requested_pmids,
            http_status=200,
            content_type="application/xml",
        )
        _persist_pubmed_efetch_if_requested(
            persist_db=persist_db,
            result=result,
            settings=settings,
        )
        _print_pubmed_efetch_summary(result, db_persisted=persist_db)
        return

    if not settings.ncbi_email:
        typer.echo("NCBI_EMAIL is required for --live PubMed EFetch calls.", err=True)
        raise typer.Exit(code=1)

    try:
        result = run_efetch(
            pmids=requested_pmids,
            artifact_store=artifact_store,
            settings=settings,
        )
    except PubMedHTTPStatusError as exc:
        _exit_pubmed_http_status_error(exc)
    _persist_pubmed_efetch_if_requested(
        persist_db=persist_db,
        result=result,
        settings=settings,
    )
    _print_pubmed_efetch_summary(result, db_persisted=persist_db)


def _persist_pubmed_efetch_if_requested(
    *,
    persist_db: bool,
    result: PubMedEFetchAdapterResult,
    settings: Settings,
) -> None:
    if not persist_db:
        return

    engine = make_engine(settings)
    try:
        session_factory = make_session_factory(engine=engine)
        with session_factory.begin() as session:
            persist_pubmed_efetch_result(session, result=result)
    finally:
        engine.dispose()


def _print_pubmed_efetch_summary(
    result: PubMedEFetchAdapterResult,
    *,
    db_persisted: bool,
) -> None:
    parsed = result.parsed
    typer.echo(f"records_returned: {parsed.records_returned}")
    typer.echo(f"pmids_returned: {len(parsed.returned_pmids)}")
    typer.echo(f"raw_payload_hash: {parsed.raw_payload_hash}")
    typer.echo(f"manifest_hash: {parsed.source_snapshot_manifest_hash}")
    typer.echo(f"db_persisted: {db_persisted}")


def _exit_pubmed_http_status_error(exc: PubMedHTTPStatusError) -> NoReturn:
    typer.echo(
        (
            f"PubMed {exc.operation} failed with HTTP {exc.http_status}. "
            f"Raw response artifact was preserved: "
            f"raw_payload_hash={exc.raw_payload_hash}; "
            f"manifest_hash={exc.source_snapshot_manifest_hash}; "
            f"raw_artifact_uri={exc.raw_artifact_uri}."
        ),
        err=True,
    )
    raise typer.Exit(code=1) from exc


@fetch_app.command("pmc-bioc")
def fetch_pmc_bioc() -> None:
    """Fetch PMC BioC full text where available."""
    _not_implemented("corpus fetch pmc-bioc")


@enrich_app.command("pmc-idconv")
def enrich_pmc_idconv() -> None:
    """Convert identifiers through PMC ID Converter."""
    _not_implemented("corpus enrich pmc-idconv")


@enrich_app.command("openalex")
def enrich_openalex() -> None:
    """Enrich a selected record through an OpenAlex singleton lookup."""
    _not_implemented("corpus enrich openalex")


@validate_app.command("build")
def validate_build() -> None:
    """Validate a corpus build."""
    _not_implemented("corpus validate build")


@export_app.command("slice")
def export_slice() -> None:
    """Export a deterministic corpus slice."""
    _not_implemented("corpus export slice")


@audit_app.command("lineage")
def audit_lineage() -> None:
    """Audit corpus lineage."""
    _not_implemented("corpus audit lineage")


app.add_typer(query_app, name="query")
app.add_typer(build_app, name="build")
app.add_typer(fetch_app, name="fetch")
app.add_typer(enrich_app, name="enrich")
app.add_typer(validate_app, name="validate")
app.add_typer(export_app, name="export")
app.add_typer(audit_app, name="audit")
