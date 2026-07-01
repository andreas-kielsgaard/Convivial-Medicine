from __future__ import annotations

from pathlib import Path
from typing import Annotated, NoReturn, cast

import typer

from convivial_medicine import __version__
from convivial_medicine.adapters.openalex.errors import OpenAlexHTTPStatusError
from convivial_medicine.adapters.openalex.persistence import persist_openalex_work_result
from convivial_medicine.adapters.openalex.work import (
    OpenAlexWorkAdapterResult,
    OpenAlexWorkIdentifierType,
    build_openalex_work_request,
    process_openalex_work_response_bytes,
    run_openalex_work,
)
from convivial_medicine.adapters.pmc.bioc import (
    PmcBioCAdapterResult,
    build_bioc_request,
    process_bioc_response_bytes,
    run_bioc,
)
from convivial_medicine.adapters.pmc.errors import PmcHTTPStatusError
from convivial_medicine.adapters.pmc.idconv import (
    PMC_IDCONV_ENDPOINT,
    PmcIdConverterAdapterResult,
    build_idconv_params,
    process_idconv_response_bytes,
    run_idconv,
)
from convivial_medicine.adapters.pmc.persistence import (
    persist_pmc_bioc_result,
    persist_pmc_idconv_result,
)
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
def fetch_pmc_bioc(
    identifier: Annotated[
        str | None,
        typer.Option("--id", help="Single PubMed ID or PMC ID to fetch through PMC BioC."),
    ] = None,
    id_type: Annotated[
        str | None,
        typer.Option(
            "--id-type",
            help="Identifier type. Use pmid or pmcid; omitted values are inferred.",
        ),
    ] = None,
    artifact_root: Annotated[
        Path,
        typer.Option("--artifact-root", help="Local content-addressed artifact root."),
    ] = DEFAULT_ARTIFACT_ROOT,
    live: Annotated[
        bool,
        typer.Option("--live", help="Make a live PMC BioC network call."),
    ] = False,
    fixture: Annotated[
        Path | None,
        typer.Option(
            "--fixture",
            help="Read saved PMC BioC response bytes instead of calling the network.",
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
    """Fetch PMC BioC full text where available."""
    if live and fixture is not None:
        typer.echo("Use either --live or --fixture, not both.", err=True)
        raise typer.Exit(code=2)

    if not live and fixture is None:
        typer.echo(
            "No PMC BioC fetch run. Pass --id ID with --fixture PATH "
            "to replay bytes or --live to call PMC BioC."
        )
        return

    if identifier is None or not identifier.strip():
        typer.echo("--id must include one PMID or PMCID.", err=True)
        raise typer.Exit(code=2)

    try:
        request = build_bioc_request(identifier, id_type=id_type)
    except ValueError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=2) from exc

    settings = get_settings()
    artifact_store = LocalArtifactStore(artifact_root)

    if persist_db:
        try:
            check_database_connection(settings)
        except DatabaseConnectionError as exc:
            typer.echo(f"database_persistence: failed ({exc})", err=True)
            raise typer.Exit(code=1) from exc

    if fixture is not None:
        result = process_bioc_response_bytes(
            raw_bytes=fixture.read_bytes(),
            artifact_store=artifact_store,
            request=request,
            http_status=200,
            content_type="application/json",
        )
        _persist_pmc_bioc_if_requested(
            persist_db=persist_db,
            result=result,
            settings=settings,
        )
        _print_pmc_bioc_summary(result, db_persisted=persist_db)
        return

    try:
        result = run_bioc(
            identifier=request.requested_id,
            id_type=request.requested_id_type,
            artifact_store=artifact_store,
        )
    except PmcHTTPStatusError as exc:
        _exit_pmc_http_status_error(exc)
    _persist_pmc_bioc_if_requested(
        persist_db=persist_db,
        result=result,
        settings=settings,
    )
    _print_pmc_bioc_summary(result, db_persisted=persist_db)


def _persist_pmc_bioc_if_requested(
    *,
    persist_db: bool,
    result: PmcBioCAdapterResult,
    settings: Settings,
) -> None:
    if not persist_db:
        return

    engine = make_engine(settings)
    try:
        session_factory = make_session_factory(engine=engine)
        with session_factory.begin() as session:
            persist_pmc_bioc_result(session, result=result)
    finally:
        engine.dispose()


def _print_pmc_bioc_summary(
    result: PmcBioCAdapterResult,
    *,
    db_persisted: bool,
) -> None:
    parsed = result.parsed
    typer.echo(f"document_detected: {parsed.document_detected}")
    typer.echo(f"document_count: {parsed.document_count}")
    typer.echo(f"passage_count: {parsed.passage_count}")
    typer.echo(f"raw_payload_hash: {parsed.raw_payload_hash}")
    typer.echo(f"manifest_hash: {parsed.source_snapshot_manifest_hash}")
    typer.echo(f"db_persisted: {db_persisted}")


@enrich_app.command("pmc-idconv")
def enrich_pmc_idconv(
    pmids: Annotated[
        str | None,
        typer.Option("--pmids", help="Comma-separated PubMed IDs to convert."),
    ] = None,
    artifact_root: Annotated[
        Path,
        typer.Option("--artifact-root", help="Local content-addressed artifact root."),
    ] = DEFAULT_ARTIFACT_ROOT,
    live: Annotated[
        bool,
        typer.Option("--live", help="Make a live PMC ID Converter network call."),
    ] = False,
    fixture: Annotated[
        Path | None,
        typer.Option(
            "--fixture",
            help="Read saved PMC ID Converter response bytes instead of calling the network.",
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
    """Convert identifiers through PMC ID Converter."""
    if live and fixture is not None:
        typer.echo("Use either --live or --fixture, not both.", err=True)
        raise typer.Exit(code=2)

    if not live and fixture is None:
        typer.echo(
            "No PMC ID Converter enrichment run. Pass --pmids IDS with --fixture PATH "
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
        result = process_idconv_response_bytes(
            raw_bytes=fixture.read_bytes(),
            artifact_store=artifact_store,
            endpoint=PMC_IDCONV_ENDPOINT,
            request_params=build_idconv_params(requested_pmids),
            requested_pmids=requested_pmids,
            http_status=200,
            content_type="application/json",
        )
        _persist_pmc_idconv_if_requested(
            persist_db=persist_db,
            result=result,
            settings=settings,
        )
        _print_pmc_idconv_summary(result, db_persisted=persist_db)
        return

    if not settings.ncbi_email:
        typer.echo("NCBI_EMAIL is required for --live PMC ID Converter calls.", err=True)
        raise typer.Exit(code=1)

    try:
        result = run_idconv(
            pmids=requested_pmids,
            artifact_store=artifact_store,
            settings=settings,
        )
    except PmcHTTPStatusError as exc:
        _exit_pmc_http_status_error(exc)
    _persist_pmc_idconv_if_requested(
        persist_db=persist_db,
        result=result,
        settings=settings,
    )
    _print_pmc_idconv_summary(result, db_persisted=persist_db)


def _persist_pmc_idconv_if_requested(
    *,
    persist_db: bool,
    result: PmcIdConverterAdapterResult,
    settings: Settings,
) -> None:
    if not persist_db:
        return

    engine = make_engine(settings)
    try:
        session_factory = make_session_factory(engine=engine)
        with session_factory.begin() as session:
            persist_pmc_idconv_result(session, result=result)
    finally:
        engine.dispose()


def _print_pmc_idconv_summary(
    result: PmcIdConverterAdapterResult,
    *,
    db_persisted: bool,
) -> None:
    parsed = result.parsed
    missing_pmids = ",".join(parsed.missing_pmids) if parsed.missing_pmids else "none"
    typer.echo(f"records_returned: {parsed.records_returned}")
    typer.echo(f"pmcids_returned: {parsed.pmcids_returned}")
    typer.echo(f"missing_pmids: {missing_pmids}")
    typer.echo(f"raw_payload_hash: {parsed.raw_payload_hash}")
    typer.echo(f"manifest_hash: {parsed.source_snapshot_manifest_hash}")
    typer.echo(f"db_persisted: {db_persisted}")


def _exit_pmc_http_status_error(exc: PmcHTTPStatusError) -> NoReturn:
    typer.echo(
        (
            f"PMC {exc.operation} failed with HTTP {exc.http_status}. "
            f"Raw response artifact was preserved: "
            f"raw_payload_hash={exc.raw_payload_hash}; "
            f"manifest_hash={exc.source_snapshot_manifest_hash}; "
            f"raw_artifact_uri={exc.raw_artifact_uri}."
        ),
        err=True,
    )
    raise typer.Exit(code=1) from exc


@enrich_app.command("openalex")
def enrich_openalex(
    doi: Annotated[
        str | None,
        typer.Option("--doi", help="Known DOI to enrich through OpenAlex."),
    ] = None,
    pmid: Annotated[
        str | None,
        typer.Option("--pmid", help="Known PubMed ID to enrich through OpenAlex."),
    ] = None,
    openalex_id: Annotated[
        str | None,
        typer.Option("--openalex-id", help="Known OpenAlex work ID, such as W2741809807."),
    ] = None,
    artifact_root: Annotated[
        Path,
        typer.Option("--artifact-root", help="Local content-addressed artifact root."),
    ] = DEFAULT_ARTIFACT_ROOT,
    live: Annotated[
        bool,
        typer.Option("--live", help="Make a live OpenAlex singleton work call."),
    ] = False,
    fixture: Annotated[
        Path | None,
        typer.Option(
            "--fixture",
            help="Read saved OpenAlex work response bytes instead of calling the network.",
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
    """Enrich a selected record through an OpenAlex singleton lookup."""
    if live and fixture is not None:
        typer.echo("Use either --live or --fixture, not both.", err=True)
        raise typer.Exit(code=2)

    if not live and fixture is None:
        typer.echo(
            "No OpenAlex enrichment run. Pass one of --doi, --pmid, or --openalex-id "
            "with --fixture PATH to replay bytes or --live to call OpenAlex."
        )
        return

    try:
        identifier, id_type = _single_openalex_identifier(
            doi=doi,
            pmid=pmid,
            openalex_id=openalex_id,
        )
    except ValueError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=2) from exc

    settings = get_settings()
    artifact_store = LocalArtifactStore(artifact_root)
    request = build_openalex_work_request(
        identifier,
        id_type=id_type,
        settings=settings,
    )

    if persist_db:
        try:
            check_database_connection(settings)
        except DatabaseConnectionError as exc:
            typer.echo(f"database_persistence: failed ({exc})", err=True)
            raise typer.Exit(code=1) from exc

    if fixture is not None:
        result = process_openalex_work_response_bytes(
            raw_bytes=fixture.read_bytes(),
            artifact_store=artifact_store,
            request=request,
            http_status=200,
            content_type="application/json",
        )
        _persist_openalex_work_if_requested(
            persist_db=persist_db,
            result=result,
            settings=settings,
        )
        _print_openalex_work_summary(result, db_persisted=persist_db)
        return

    if not settings.openalex_api_key:
        typer.echo("OPENALEX_API_KEY is required for --live OpenAlex calls.", err=True)
        raise typer.Exit(code=1)

    try:
        result = run_openalex_work(
            identifier=identifier,
            id_type=id_type,
            artifact_store=artifact_store,
            settings=settings,
        )
    except OpenAlexHTTPStatusError as exc:
        _exit_openalex_http_status_error(exc)
    _persist_openalex_work_if_requested(
        persist_db=persist_db,
        result=result,
        settings=settings,
    )
    _print_openalex_work_summary(result, db_persisted=persist_db)


def _single_openalex_identifier(
    *,
    doi: str | None,
    pmid: str | None,
    openalex_id: str | None,
) -> tuple[str, OpenAlexWorkIdentifierType]:
    provided = tuple(
        (identifier.strip(), id_type)
        for identifier, id_type in (
            (doi, "doi"),
            (pmid, "pmid"),
            (openalex_id, "openalex_id"),
        )
        if identifier is not None and identifier.strip()
    )
    if len(provided) != 1:
        raise ValueError("Pass exactly one of --doi, --pmid, or --openalex-id.")
    identifier, id_type = provided[0]
    return identifier, cast(OpenAlexWorkIdentifierType, id_type)


def _persist_openalex_work_if_requested(
    *,
    persist_db: bool,
    result: OpenAlexWorkAdapterResult,
    settings: Settings,
) -> None:
    if not persist_db:
        return

    engine = make_engine(settings)
    try:
        session_factory = make_session_factory(engine=engine)
        with session_factory.begin() as session:
            persist_openalex_work_result(session, result=result)
    finally:
        engine.dispose()


def _print_openalex_work_summary(
    result: OpenAlexWorkAdapterResult,
    *,
    db_persisted: bool,
) -> None:
    parsed = result.parsed
    typer.echo(f"openalex_id: {parsed.openalex_id or 'missing'}")
    typer.echo(f"doi: {parsed.doi or 'missing'}")
    typer.echo(f"pmid: {parsed.pmid or 'missing'}")
    typer.echo(f"publication_year: {parsed.publication_year or 'missing'}")
    typer.echo(f"cited_by_count: {parsed.cited_by_count or 'missing'}")
    typer.echo(f"is_retracted: {parsed.is_retracted}")
    typer.echo(f"raw_payload_hash: {parsed.raw_payload_hash}")
    typer.echo(f"manifest_hash: {parsed.source_snapshot_manifest_hash}")
    typer.echo(f"db_persisted: {db_persisted}")


def _exit_openalex_http_status_error(exc: OpenAlexHTTPStatusError) -> NoReturn:
    typer.echo(
        (
            f"OpenAlex {exc.operation} failed with HTTP {exc.http_status}. "
            f"Raw response artifact was preserved: "
            f"raw_payload_hash={exc.raw_payload_hash}; "
            f"manifest_hash={exc.source_snapshot_manifest_hash}; "
            f"raw_artifact_uri={exc.raw_artifact_uri}."
        ),
        err=True,
    )
    raise typer.Exit(code=1) from exc


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
