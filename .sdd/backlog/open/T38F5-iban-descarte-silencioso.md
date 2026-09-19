# T38-F5 · extraer_iban descarta IBANs malformados sin dejar candidato
assignee: W1
priority: p2
severidad: p2

## Hallazgo
`extraer_iban` hace `if len(iban) != 24: continue` — un IBAN con dígitos de
menos/más NO genera candidato alguno. Eso es un VETO en la extracción (§2:
todos los candidatos se conservan; vetar es cosa de las reglas) y además
asimétrico: un IBAN de 24 caracteres con mod-97 roto SÍ genera candidato
(conf 0.75), uno de 23 no genera nada.

## Reproducción (verificado hoy)
`extraer_iban("IBAN: ES55 3159 0012 3487 6512 340")` → [] (23 chars).
## Propuesta
Candidato con conf _CONF_MALA (0.4) y el motivo de longitud en el valor o en
el extractor — la señal llega a revisión en vez de perderse. ~3 líneas.

## Evaluación (W4, T39 — 2026-09-19): DIFERIDO al supervisor, NO implementado
Hallazgo válido (verificado: el veto `len != 24` viola §2 y es asimétrico con
el mod-97-roto que sí deja candidato a 0.75). Pero la implementación propuesta
CAMBIA DECISIONES en la dirección peor:
- Hoy: IBAN de 23 chars → sin candidato → IBAN_MATCHES_MASTER UNKNOWN → ESCALAR.
- Con candidato conf 0.4 y proveedor cruzable: `_match_all` no matchea ⇒ FAIL
  ⇒ NO_PAGAR definitivo desde una truncación de OCR (duda razonable que un
  humano SÍ puede resolver = §6 dice ESCALAR, no NO_PAGAR).
Es la clase de cambio de política NO_PAGAR/ESCALAR reservada al supervisor con
el usuario (ADR), como F1/F2. Recomendación para ese ADR: conservar el
candidato (fin del veto, §2) Y a la vez blindar en el motor que un candidato
único de baja confianza (< umbral) ante match-exacto deje UNKNOWN en vez de
FAIL — ambas cosas juntas, nunca el candidato solo.
