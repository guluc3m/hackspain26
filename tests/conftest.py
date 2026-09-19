"""Fixtures compartidas de tests."""

from __future__ import annotations

from pathlib import Path

FIXTURES = Path(__file__).parent / "fixtures"


def fixture_path(*parts: str) -> Path:
    return FIXTURES.joinpath(*parts)


def lote1_estado_real_presente() -> bool:
    """T40F4: ¿existe el estado runtime REAL del lote 1 en este worktree?

    Varios tests de defensa/UI/presentación verifican contra el store real
    del lote 1 (`.sdd/lote1/…`, gitignored). En un worktree recién clonado
    ese estado no existe: los tests se saltan con motivo honesto en vez de
    dar un rojo falso de entorno. DONDE el estado existe (máquina de la
    defensa) corren COMPLETOS — ningún assert se relaja.
    """
    ledger = Path(".sdd/lote1/ledger/ledger.jsonl")
    return ledger.is_file() and ledger.stat().st_size > 0