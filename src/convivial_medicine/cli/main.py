from __future__ import annotations

import typer

from convivial_medicine import __version__
from convivial_medicine.config import get_settings

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
def doctor() -> None:
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
    typer.echo("status: ok")


@query_app.command("pubmed")
def query_pubmed() -> None:
    """Prepare a PubMed membership query."""
    _not_implemented("corpus query pubmed")


@build_app.command("seed")
def build_seed() -> None:
    """Build a named seed corpus."""
    _not_implemented("corpus build seed")


@fetch_app.command("pubmed-summary")
def fetch_pubmed_summary() -> None:
    """Fetch PubMed summary data for selected records."""
    _not_implemented("corpus fetch pubmed-summary")


@fetch_app.command("pubmed-records")
def fetch_pubmed_records() -> None:
    """Fetch PubMed record data for selected records."""
    _not_implemented("corpus fetch pubmed-records")


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
