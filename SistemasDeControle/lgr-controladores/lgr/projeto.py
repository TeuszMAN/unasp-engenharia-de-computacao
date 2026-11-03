"""Projeto de controladores P, PI e PID pelo Lugar Geométrico das Raízes.

Todos os controladores são escritos na forma de polos e zeros, que é a forma
natural do LGR:

    P   : C(s) = K
    PI  : C(s) = K (s + zi) / s
    PID : C(s) = K (s + zi)(s + zd) / s

O ganho K é sempre o mesmo K do LGR de C(s)G(s)/K. Os zeros e o polo na origem
mudam a forma do lugar (condição de ângulo) e o K escolhe o ponto sobre ele
(condição de módulo). No fim, convertemos para a forma paralela
Kp + Ki/s + Kd·s, que é a usada na implementação.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

from .especificacoes import Requisitos, formatar_complexo
from .funcao_transferencia import FuncaoTransferencia
from .lugar_raizes import (
    angulo,
    deficiencia_angular,
    ganho_no_ponto,
    intersecoes_sigma,
    intersecoes_zeta,
)

FC = formatar_complexo


class ProjetoInviavel(Exception):
    """O requisito não pode ser atendido com este tipo de controlador."""


@dataclass
class Controlador:
    tipo: str
    K: float
    zeros: list[float] = field(default_factory=list)  # z em (s + z)
    integrador: bool = False
    polo_projetado: complex | None = None
    passos: list[str] = field(default_factory=list)

    # forma do controlador sem o ganho: é ela que, junto com G, define o LGR
    @property
    def forma(self) -> FuncaoTransferencia:
        num = np.poly1d([1.0])
        for z in self.zeros:
            num = num * np.poly1d([1.0, z])
        den = np.poly1d([1.0, 0.0]) if self.integrador else np.poly1d([1.0])
        return FuncaoTransferencia(num, den)

    @property
    def ft(self) -> FuncaoTransferencia:
        return self.K * self.forma

    @property
    def ganhos_paralelos(self) -> tuple[float, float, float]:
        """(Kp, Ki, Kd) de Kp + Ki/s + Kd·s."""
        K, z = self.K, self.zeros
        if self.tipo == "P":
            return K, 0.0, 0.0
        if self.tipo == "PI":
            return K, K * z[0], 0.0
        # K (s + z1)(s + z2)/s = K s + K (z1 + z2) + K z1 z2 / s
        return K * (z[0] + z[1]), K * z[0] * z[1], K

    def descrever(self) -> str:
        kp, ki, kd = self.ganhos_paralelos
        fatores = "".join(f"(s + {z:.5g})" for z in self.zeros)
        if self.integrador:
            zpk = f"{self.K:.5g} {fatores} / s"
        else:
            zpk = f"{self.K:.5g}"
        partes = [f"Kp = {kp:.5g}"]
        if self.tipo in ("PI", "PID"):
            partes.append(f"Ki = {ki:.5g}")
        if self.tipo == "PID":
            partes.append(f"Kd = {kd:.5g}")
        return f"C(s) = {zpk}\nForma paralela: " + ", ".join(partes)


# -- utilidades -----------------------------------------------------------------
def _escolher(candidatos: list[tuple[complex, float]], alvo: complex | None):
    if alvo is not None:
        return min(candidatos, key=lambda c: abs(c[0] - alvo))
    return candidatos[0]  # menor K: o primeiro cruzamento conforme K cresce


def _listar(candidatos) -> str:
    return "; ".join(f"s = {FC(s, pm=True)} (K = {K:.5g})" for s, K in candidatos)


def _zero_pelo_angulo(sd: complex, phi: float, papel: str) -> float:
    """Posição -z de um zero real que contribui com o ângulo phi (graus) em sd.

    O vetor de -z até sd = -σ + jωd tem ângulo atan2(ωd, z - σ) = phi,
    logo z = σ + ωd / tan(phi). Um zero real só contribui com ângulos entre
    0° e 180° num ponto do semiplano superior.
    """
    if not 0 < phi < 180:
        raise ProjetoInviavel(
            f"O {papel} precisaria contribuir com {phi:.2f}°, mas um zero real só "
            "contribui com algo entre 0° e 180°. Relaxe os requisitos de tempo ou use "
            "um controlador com mais zeros."
        )
    sigma, wd = -sd.real, sd.imag
    z = sigma + wd / math.tan(math.radians(phi))
    if z <= 0:
        raise ProjetoInviavel(
            f"O {papel} ficaria em s = {-z:.4g}, no semiplano direito (ou na origem). "
            "Um zero instável no controlador não é aceitável: relaxe os requisitos."
        )
    return z


def _ganho_exato(L: FuncaoTransferencia, sd: complex) -> float:
    erro = deficiencia_angular(L, sd)
    if abs(erro) > 1e-6:
        raise RuntimeError(f"sd não ficou no LGR (erro de ângulo {erro:.3g}°).")
    return ganho_no_ponto(L, sd)


def _requisito_ponto(req: Requisitos, tipo: str) -> complex:
    sd = req.polo
    if sd is None:
        raise ProjetoInviavel(
            f"O {tipo} posiciona o polo num ponto exato: informe dois requisitos "
            "(por exemplo sobressinal e tempo de acomodação)."
        )
    return sd


# -- P --------------------------------------------------------------------------
def projetar_p(G: FuncaoTransferencia, req: Requisitos) -> Controlador:
    """Controlador proporcional: só escolhe o ponto sobre o LGR original.

    Como o LGR de K·G(s) não muda com K, o P tem um grau de liberdade: dá para
    atender ζ (ponto onde o LGR cruza a reta de ζ) ou σ (onde cruza a vertical),
    mas em geral não os dois ao mesmo tempo.
    """
    passos = []
    alvo = req.polo
    if req.zeta is not None:
        cand = intersecoes_zeta(G, req.zeta)
        reta = f"reta de ζ = {req.zeta:.4f}"
    elif req.sigma is not None:
        cand = intersecoes_sigma(G, req.sigma)
        reta = f"reta vertical Re(s) = {-req.sigma:.4g}"
    else:
        raise ProjetoInviavel("O P precisa de ζ (ou sobressinal) ou de ts.")
    passos.append(
        f"O LGR de G(s) é fixo; o P só escolhe K. Buscamos onde o LGR corta a {reta}, "
        "isto é, os pontos dessa reta com ∠G(s) = -180°."
    )
    if not cand:
        raise ProjetoInviavel(
            f"O LGR de G(s) não cruza a {reta}: nenhum ganho proporcional atende o "
            "requisito. É preciso mudar o LGR com zeros e polos (PI, PID)."
        )
    passos.append("Cruzamentos encontrados: " + _listar(cand))
    s, K = _escolher(cand, alvo)
    if len(cand) > 1:
        criterio = "o mais próximo do polo desejado" if alvo is not None else "o de menor K"
        passos.append(f"Escolhido {criterio}.")
    passos.append(f"Condição de módulo: K = 1/|G(s)| em s = {FC(s, pm=True)} → K = {K:.5g}")
    if alvo is not None and abs(s - alvo) > 1e-6 * abs(alvo):
        passos.append(
            f"O polo desejado {FC(alvo, pm=True)} tem deficiência angular de "
            f"{deficiencia_angular(G, alvo):.2f}° no LGR de G: o P não chega até ele. "
            f"Com o P, ts ≈ 4/{-s.real:.4g} = {4 / -s.real:.4g} s."
        )
    return Controlador("P", K, [], False, s, passos)


# -- PI -------------------------------------------------------------------------
def projetar_pi(
    G: FuncaoTransferencia, req: Requisitos, metodo: str = "auto", zero: float | None = None
) -> Controlador:
    """Controlador PI: C(s) = K (s + z)/s.

    metodo="angulo": coloca o polo de malha fechada exatamente no polo desejado.
        O polo na origem e o zero precisam, juntos, cobrir a deficiência
        angular de G no ponto; a posição do zero sai da condição de ângulo.
    metodo="ideal": compensação integral ideal. Parte do projeto P e põe o zero
        bem perto da origem, onde polo e zero quase se cancelam no ponto
        dominante: o transitório quase não muda e o erro ao degrau zera.
    metodo="auto": "angulo" se houver dois requisitos, senão "ideal".
    """
    if metodo == "auto":
        metodo = "angulo" if req.polo is not None and zero is None else "ideal"
    if metodo == "angulo":
        return _pi_angulo(G, req)
    if metodo == "ideal":
        return _pi_ideal(G, req, zero)
    raise ValueError("metodo deve ser 'auto', 'angulo' ou 'ideal'.")


def _pi_angulo(G, req) -> Controlador:
    sd = _requisito_ponto(req, "PI pela condição de ângulo")
    ang_g = angulo(G, sd)
    ang_int = math.degrees(np.angle(sd))
    phi = (-180 - ang_g + ang_int) % 360
    passos = [
        f"Polo desejado sd = {FC(sd, pm=True)}.",
        f"∠G(sd) = {ang_g:.2f}°. O integrador (polo na origem) soma -∠sd = {-ang_int:.2f}°.",
        f"O zero precisa fechar -180°: φz = -180° - ({ang_g:.2f}°) + {ang_int:.2f}° = {phi:.2f}° (mod 360°).",
    ]
    z = _zero_pelo_angulo(sd, phi, "zero do PI")
    passos.append(f"Zero em s = -z com z = σ + ωd/tan(φz) = {z:.5g}.")
    c = Controlador("PI", 1.0, [z], True, sd, passos)
    K = _ganho_exato(c.forma * G, sd)
    c.K = K
    passos.append(f"Condição de módulo em sd: K = 1/|(sd + z)G(sd)/sd| = {K:.5g}")
    return c


def _pi_ideal(G, req, zero) -> Controlador:
    p = projetar_p(G, req)
    sp = p.polo_projetado
    z = zero if zero is not None else abs(sp.real) / 10
    passos = [
        f"Ponto de partida: projeto P, polo em {FC(sp, pm=True)} com K = {p.K:.5g}.",
        f"Zero do PI em s = -{z:.4g}, perto da origem"
        + (" (10% de |Re(s)| do polo dominante)." if zero is None else "."),
        "Vistos do polo dominante, o polo na origem e o zero quase coincidem: "
        f"somam {math.degrees(np.angle(sp + z)) - math.degrees(np.angle(sp)):.2f}° e o LGR "
        "quase não se move nessa região.",
    ]
    c = Controlador("PI", 1.0, [z], True, None, passos)
    L = c.forma * G
    if req.zeta is not None:
        cand = intersecoes_zeta(L, req.zeta)
        reta = "reta de ζ"
    else:
        cand = intersecoes_sigma(L, req.sigma)
        reta = "reta vertical de σ"
    if not cand:
        raise ProjetoInviavel(f"Com o PI, o LGR deixou de cruzar a {reta}; aproxime o zero da origem.")
    s, K = _escolher(cand, sp)
    c.K, c.polo_projetado = K, s
    passos.append(
        f"Novo cruzamento com a {reta}: s = {FC(s, pm=True)}, K = {K:.5g} "
        f"(antes {FC(sp, pm=True)}, K = {p.K:.5g})."
    )
    passos.append(
        f"Surge um polo lento perto de -{z:.4g}, quase cancelado pelo zero: ele gera uma "
        "cauda lenta até o erro zerar. Com o zero mais perto da origem, a cauda fica menor "
        "e mais lenta."
    )
    return c


# -- PID ------------------------------------------------------------------------
def projetar_pid(
    G: FuncaoTransferencia, req: Requisitos, zero_pi: float | None = None
) -> Controlador:
    """Controlador PID: C(s) = K (s + zi)(s + zd)/s = PI × PD.

    1. Escolhemos o zero da parte integral (zi) perto da origem, para que o
       par polo na origem / zero quase não mexa no ângulo no ponto desejado.
    2. O zero da parte derivativa (zd) cobre a deficiência angular restante
       e faz o LGR passar exatamente pelo polo desejado.
    3. A condição de módulo dá K.
    """
    sd = _requisito_ponto(req, "PID")
    zi = zero_pi if zero_pi is not None else abs(sd.real) / 10
    ang_g = angulo(G, sd)
    ang_int = math.degrees(np.angle(sd))
    ang_zi = math.degrees(np.angle(sd + zi))
    phi = (-180 - ang_g + ang_int - ang_zi) % 360
    passos = [
        f"Polo desejado sd = {FC(sd, pm=True)}.",
        f"∠G(sd) = {ang_g:.2f}° → deficiência angular de G: {deficiencia_angular(G, sd):.2f}°.",
        f"Parte PI: zero em -{zi:.4g}"
        + (" (10% de |Re(sd)|)" if zero_pi is None else "")
        + f"; junto com o integrador soma {ang_zi - ang_int:.2f}° em sd.",
        f"Parte PD: o zero precisa contribuir φd = -180° - ({ang_g:.2f}°) + {ang_int:.2f}° "
        f"- {ang_zi:.2f}° = {phi:.2f}° (mod 360°).",
    ]
    zd = _zero_pelo_angulo(sd, phi, "zero do PD")
    passos.append(f"Zero do PD em s = -zd com zd = σ + ωd/tan(φd) = {zd:.5g}.")
    c = Controlador("PID", 1.0, [zi, zd], True, sd, passos)
    K = _ganho_exato(c.forma * G, sd)
    c.K = K
    passos.append(f"Condição de módulo em sd: K = {K:.5g}")
    return c


def projetar(tipo: str, G, req, **opcoes) -> Controlador:
    tipo = tipo.upper()
    if tipo == "P":
        return projetar_p(G, req)
    if tipo == "PI":
        return projetar_pi(G, req, opcoes.get("metodo_pi", "auto"), opcoes.get("zero_pi"))
    if tipo == "PID":
        return projetar_pid(G, req, opcoes.get("zero_pi"))
    raise ValueError(f"Tipo de controlador desconhecido: {tipo}")
