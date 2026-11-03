"""Requisitos de resposta transitória convertidos em polos desejados.

Tudo parte da aproximação de segunda ordem: se a malha fechada tiver um par
de polos dominantes s = -σ ± jωd, com σ = ζωn e ωd = ωn·√(1-ζ²), então

    sobressinal  Mp = 100·exp(-ζπ/√(1-ζ²))   [%]
    acomodação   ts ≈ 4/σ                    (critério de 2%)
    pico         tp = π/ωd

Cada requisito vira uma reta no plano s:
    Mp ou ζ  -> semirreta saindo da origem (ζ constante)
    ts       -> reta vertical Re(s) = -σ
    tp       -> reta horizontal Im(s) = ωd
    ωn       -> círculo de raio ωn
O polo desejado é o cruzamento de duas delas.
"""

from __future__ import annotations

import math
from dataclasses import dataclass


def zeta_de_sobressinal(sobressinal: float) -> float:
    """ζ que produz o sobressinal dado (em %), num sistema de 2ª ordem."""
    if not 0 < sobressinal < 100:
        raise ValueError("O sobressinal deve estar entre 0 e 100 %.")
    ln = math.log(sobressinal / 100)
    return -ln / math.sqrt(math.pi**2 + ln**2)


def sobressinal_de_zeta(zeta: float) -> float:
    """Sobressinal (em %) de um sistema de 2ª ordem com amortecimento ζ."""
    if zeta >= 1:
        return 0.0
    if zeta <= 0:
        return 100.0
    return 100 * math.exp(-zeta * math.pi / math.sqrt(1 - zeta**2))


@dataclass
class Requisitos:
    """Requisitos de projeto, guardados como grandezas do plano s.

    zeta  : coeficiente de amortecimento (define a reta de ζ constante)
    sigma : parte real do polo, em módulo (σ = ζωn = 4/ts)
    wd    : frequência amortecida (ωd = π/tp)
    wn    : frequência natural
    """

    zeta: float | None = None
    sigma: float | None = None
    wd: float | None = None
    wn: float | None = None

    @classmethod
    def de(cls, sobressinal=None, ts=None, tp=None, zeta=None, wn=None) -> "Requisitos":
        if sobressinal is not None and zeta is not None:
            raise ValueError("Informe o sobressinal ou ζ, não os dois.")
        if sobressinal is not None:
            zeta = zeta_de_sobressinal(sobressinal)
        if zeta is not None and not 0 < zeta < 1:
            raise ValueError("ζ precisa estar entre 0 e 1 (polos complexos).")
        sigma = 4 / ts if ts is not None else None
        wd = math.pi / tp if tp is not None else None
        req = cls(zeta=zeta, sigma=sigma, wd=wd, wn=wn)
        if sum(v is not None for v in (zeta, sigma, wd, wn)) > 2:
            raise ValueError(
                "Informe no máximo dois requisitos: um polo no plano s tem só "
                "duas coordenadas."
            )
        if req.sigma is not None and req.wn is not None and req.wn <= req.sigma:
            raise ValueError("Com ts e ωn juntos, é preciso ωn > 4/ts.")
        return req

    @property
    def polo(self) -> complex | None:
        """Polo desejado no semiplano superior, ou None se faltar requisito."""
        z, sg, wd, wn = self.zeta, self.sigma, self.wd, self.wn
        if z is not None and sg is not None:
            wn = sg / z
        elif z is not None and wd is not None:
            wn = wd / math.sqrt(1 - z**2)
        elif z is not None and wn is not None:
            pass
        elif sg is not None and wd is not None:
            return complex(-sg, wd)
        elif sg is not None and wn is not None:
            return complex(-sg, math.sqrt(wn**2 - sg**2))
        elif wd is not None and wn is not None:
            if wn <= wd:
                return None
            return complex(-math.sqrt(wn**2 - wd**2), wd)
        else:
            return None
        return complex(-z * wn, wn * math.sqrt(1 - z**2))

    def descrever(self) -> str:
        linhas = []
        if self.zeta is not None:
            linhas.append(
                f"ζ = {self.zeta:.4f} (sobressinal {sobressinal_de_zeta(self.zeta):.2f} %), "
                f"reta a {math.degrees(math.acos(self.zeta)):.2f}° do semieixo real negativo"
            )
        if self.sigma is not None:
            linhas.append(f"σ = {self.sigma:.4g} (ts = 4/σ = {4 / self.sigma:.4g} s)")
        if self.wd is not None:
            linhas.append(f"ωd = {self.wd:.4g} rad/s (tp = π/ωd = {math.pi / self.wd:.4g} s)")
        if self.wn is not None:
            linhas.append(f"ωn = {self.wn:.4g} rad/s")
        sd = self.polo
        if sd is not None:
            wn = abs(sd)
            linhas.append(
                f"Polo desejado: s = {formatar_complexo(sd, pm=True)} "
                f"(ζ = {-sd.real / wn:.4f}, ωn = {wn:.4g} rad/s)"
            )
        return "\n".join(linhas)


def formatar_complexo(s: complex, pm: bool = False, dig: int = 4) -> str:
    """'-1.2 + j3.4'; com pm=True, '-1.2 ± j3.4' (o par conjugado)."""
    s = complex(s)
    if abs(s.imag) < 1e-9 * max(1.0, abs(s)):
        return f"{s.real:.{dig}g}"
    sinal = "±" if pm else ("+" if s.imag >= 0 else "-")
    return f"{s.real:.{dig}g} {sinal} j{abs(s.imag):.{dig}g}"
