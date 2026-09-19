# T40F1 · Higiene de secretos como test PERMANENTE (hoy solo ritual T7)
assignee: W5
priority: p1
severidad: p2 (riesgo de entrega: una key en el histórico no tiene marcha atrás)

## Hallazgo
AGENTS.md §13 exige grep de secretos antes de cada commit, pero es un ritual
manual que vive en la cabeza del que commita. Un solo olvido mete una credencial
en el histórico público. Un requisito «no negociable» debe ser verificable
automáticamente, no recordado.

## Propuesta
`tests/test_higiene_secretos.py`: escanea los ficheros que viajan en un commit
(`git ls-files --cached --others --exclude-standard`), salta binarios y FALLA
ante patrones de SEÑAL ALTA (formas reales de credencial):
- `sk-` + ≥16 alfanuméricos (claves estilo OpenAI/DeepSeek);
- `apiKey` asignada a un valor de ≥8 caracteres;
- AWS `AKIA`+16; GitHub `ghp_`/`github_pat_`; Slack `xox*-`;
- cabecera de clave privada embebida.
Sin allowlist inicial: la doctrina y los tickets mencionan los patrones a secas
(`apiKey`, `sk-[A-Za-z0-9]` literales), que NO casan con formas reales de clave.
Además el test verifica el detector contra un payload SIMULADO construido en
runtime (nunca una key real en el fuente).

## Coste/riesgo/beneficio
~90 líneas de test, cero líneas en src/. Riesgo bajo (falso positivo → allowlist
documentada con su porqué). Beneficio: el requisito no negociable pasa a ser un
test que corre en cada pytest.

## Criterio de aceptación
- El test pasa hoy (0 hallazgos en el repo) y detecta un secreto plantado
  (self-test del detector con payload simulado en runtime).
- pytest + ruff verdes; grep del §13 sigue vacío.
