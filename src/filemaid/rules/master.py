"""Datos maestros (proveedores, pedidos) + su hash para el snapshot de config.

Se cargan de CSV/YAML/Excel al arrancar. `sha256` queda grabado en cada
decisión: se sabe qué maestro estaba activo en el momento de decidir.
"""

from __future__ import annotations

import csv
import hashlib
from dataclasses import dataclass, field
from pathlib import Path

from filemaid.parse.normalizers import normalize_iban, normalize_nif, parse_amount


@dataclass(slots=True)
class Proveedor:
    nif: str
    nombre: str
    iban: str


@dataclass(slots=True)
class Pedido:
    numero: str
    nif_proveedor: str
    importe: float
    estado: str  # PENDIENTE | SERVIDO | ...
    pagado: bool = False


@dataclass(slots=True)
class MasterData:
    proveedores: dict[str, Proveedor] = field(default_factory=dict)  # por NIF
    pedidos: dict[str, Pedido] = field(default_factory=dict)  # por número

    @property
    def sha256(self) -> str:
        h = hashlib.sha256()
        for nif in sorted(self.proveedores):
            p = self.proveedores[nif]
            h.update(f"proveedor|{p.nif}|{p.nombre}|{p.iban}\n".encode())
        for num in sorted(self.pedidos):
            q = self.pedidos[num]
            h.update(
                f"pedido|{q.numero}|{q.nif_proveedor}|{q.importe}|{q.estado}|{q.pagado}\n".encode()
            )
        return h.hexdigest()


def load_master(dir_path: Path) -> MasterData:
    """Carga proveedores.csv y pedidos.csv del directorio maestro."""
    master = MasterData()
    prov_path = dir_path / "proveedores.csv"
    if prov_path.exists():
        with prov_path.open(encoding="utf-8-sig") as f:
            for row in csv.DictReader(f):
                raw_iban = row["iban"].strip()
                p = Proveedor(
                    nif=normalize_nif(row["nif"]),
                    nombre=row["nombre"].strip(),
                    iban=normalize_iban(raw_iban),
                )
                master.proveedores[p.nif] = p
    ped_path = dir_path / "pedidos.csv"
    if ped_path.exists():
        with ped_path.open(encoding="utf-8-sig") as f:
            for row in csv.DictReader(f):
                raw_imp = row["importe"].strip()
                parsed_imp = parse_amount(raw_imp)
                importe = parsed_imp if parsed_imp is not None else float(raw_imp.replace(",", "."))
                q = Pedido(
                    numero=row["numero"].strip().upper(),
                    nif_proveedor=normalize_nif(row["nif_proveedor"]),
                    importe=importe,
                    estado=row["estado"].strip().upper(),
                    pagado=row.get("pagado", "no").strip().lower()
                    in {"si", "sí", "yes", "true", "1"},
                )
                master.pedidos[q.numero] = q
    return master
