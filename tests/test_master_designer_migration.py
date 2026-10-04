from pathlib import Path


MIGRATION = Path(__file__).resolve().parents[1] / "scripts" / "migrate_master_designer_production.py"


def test_production_migration_is_explicitly_gated_and_non_destructive():
    source = MIGRATION.read_text(encoding="utf-8")
    assert "--apply" in source
    assert "RENTAGO_APPROVE_MASTER_DESIGNER_MIGRATION" in source
    assert "DROP " not in source.upper()
    assert "TRUNCATE " not in source.upper()
    assert "DELETE " not in source.upper()
    assert "UPDATE " not in source.upper()
    assert "MERGE " not in source.upper()
    assert "business data" in source.lower()


def test_production_migration_seeds_by_existing_metadata_keys():
    source = MIGRATION.read_text(encoding="utf-8")
    assert "seed_metadata(conn, MASTERS)" in source
    assert "Never patch a partially matching Production object" in source


def test_production_migration_checks_existing_schema_mismatch():
    source = MIGRATION.read_text(encoding="utf-8")
    assert "_verify_existing_object" in source
    assert "type_mismatch" in source
    assert "missing_constraints" in source
