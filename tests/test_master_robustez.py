"""T38-F7 · load_master robusto ante el lote 2: importe como TEXTO y
pedidos duplicados (primera gana + aviso, nunca sobrescritura silenciosa)."""

from __future__ import annotations

import openpyxl

from albertitos.rules import load_master


def _wb_pedidos(filas: list[tuple]) -> openpyxl.Workbook:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Pedidos_2026"
    ws.append(["id", "proveedor_id", "nif", "importe", "estado", "fecha"])
    for fila in filas:
        ws.append(list(fila))
    return wb


def _guardar(tmp_path, wb: openpyxl.Workbook):
    path = tmp_path / "maestro.xlsx"
    wb.save(path)
    return path


def test_importe_como_texto_espanol(tmp_path):
    path = _guardar(tmp_path, _wb_pedidos(
        [("PO-2026-0222", "P001", "B46102331", "1.234,56", "PENDIENTE",
          "2026-01-20")],
    ))
    m = load_master(path)
    assert m.pedidos["PO-2026-0222"].importe == 1234.56
    assert not any("pedido_importe" in a for a in m.avisos)


def test_importe_como_texto_anglosajon(tmp_path):
    # Tras el fix T38-F3, "1,234" (coma de miles anglosajona) SÍ se resuelve
    # y el fallback de load_master lo carga sin avisos.
    path = _guardar(tmp_path, _wb_pedidos(
        [("PO-2026-0222", "P001", "B46102331", "1,234", "PENDIENTE",
          "2026-01-20")],
    ))
    m = load_master(path)
    assert m.pedidos["PO-2026-0222"].importe == 1234.0
    assert not any("pedido_importe" in a for a in m.avisos)


def test_importe_ilegible_deja_aviso_y_no_crash(tmp_path):
    path = _guardar(tmp_path, _wb_pedidos(
        [("PO-2026-0222", "P001", "B46102331", "n/d", "PENDIENTE",
          "2026-01-20")],
    ))
    m = load_master(path)
    assert m.pedidos["PO-2026-0222"].importe == 0.0
    assert "pedido_importe_ilegible:PO-2026-0222" in m.avisos


def test_importe_vacio_deja_aviso(tmp_path):
    path = _guardar(tmp_path, _wb_pedidos(
        [("PO-2026-0222", "P001", "B46102331", None, "PENDIENTE",
          "2026-01-20")],
    ))
    m = load_master(path)
    assert m.pedidos["PO-2026-0222"].importe == 0.0
    assert "pedido_importe_vacio:PO-2026-0222" in m.avisos


def test_pedido_duplicado_primera_gana_con_aviso(tmp_path):
    path = _guardar(tmp_path, _wb_pedidos(
        [("PO-2026-0222", "P001", "B46102331", 100.0, "PENDIENTE",
          "2026-01-20"),
         ("PO-2026-0222", "P002", "B96233419", 999.0, "PAGADO",
          "2026-02-01")],
    ))
    m = load_master(path)
    p = m.pedidos["PO-2026-0222"]
    assert p.proveedor_id == "P001" and p.importe == 100.0
    assert "pedidos_deduplicados:PO-2026-0222" in m.avisos
