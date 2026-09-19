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
