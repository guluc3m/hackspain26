#import "lib.typ": *

#show: conf.with(
  event: [MAISA · HACKSPAIN 2026],
  challenge: "500 Sombras de Alberto",
  title: [ALBERTITOS PLAN],
  subtitle: [Arquitectura, decisiones de diseño y trade-offs del sistema de decisión de facturas],
  place: [ETSIT UPM · MADRID],
  date: [Entrega · dom 20 sep 2026 · 11:00],
  chips: ([FACTURA], [DECISIÓN], [TRAZA]),
  logo: "img/gul-logo.svg",
  team: [guluc3m],
  teamId: none,
  repo: "https://github.com/guluc3m/hackspain26",
  authors: (
    (name: "Luis Daniel Casais Mezquida", email: "luisdaniel.casais@alumnos.uc3m.es"),
    (name: "Albert Giurgiu", email: "fedesito@posteo.es"),
    (name: "Jorge Adrian Saghin Dudulea", email: "zanajorgesaghin@gmail.com"),
    (name: "Henry Díaz Bordón", email: "henrydiazbordon@gmail.com"),
  ),
)

#include "architecture.typ"
#include "architecture-rules.typ"
#include "implementation.typ"
#include "adrs-tradeoffs.typ"
