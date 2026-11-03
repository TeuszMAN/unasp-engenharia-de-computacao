"""Lugar Geométrico das Raízes (LGR) de uma malha com realimentação unitária.

A malha fechada de K·L(s), com L(s) = N(s)/D(s), tem equação característica

    1 + K·L(s) = 0   <=>   D(s) + K·N(s) = 0.

O LGR é o conjunto das raízes dessa equação quando K vai de 0 a infinito.
Um ponto s pertence ao LGR se, e só se, satisfaz:

    condição de ângulo:  ∠L(s) = ±180° (múltiplo ímpar de 180°)
    condição de módulo:  K = 1/|L(s)|

Este módulo usa só essas duas condições e as regras de esboço que saem delas.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np
from scipy.optimize import linear_sum_assignment

from .especificacoes import formatar_complexo
from .funcao_transferencia import FuncaoTransferencia

TOL = 1e-7


# -- as duas condições ---------------------------------------------------------
def angulo(L: FuncaoTransferencia, s: complex) -> float:
    """∠L(s) em graus, no intervalo (-360°, 0°]: ângulos dos zeros menos os dos polos."""
    a = math.degrees(np.angle(complex(L(s))))
    return a - 360 if a > 0 else a


def deficiencia_angular(L: FuncaoTransferencia, s: complex) -> float:
    """Quanto falta somar a ∠L(s) para chegar a -180°, em (-180°, 180°].

    Zero: s já está no LGR. Positivo: o compensador precisa somar ângulo
    (zeros fazem isso). Negativo: precisa subtrair (polos fazem isso).
    """
    d = (-180.0 - angulo(L, s)) % 360.0
    return d - 360 if d > 180 else d


def ganho_no_ponto(L: FuncaoTransferencia, s: complex) -> float:
    """Condição de módulo: K = 1/|L(s)|."""
    return 1.0 / abs(complex(L(s)))


def raizes_malha_fechada(L: FuncaoTransferencia, K: float) -> np.ndarray:
    return np.roots((L.den + K * L.num).coeffs)


def estavel(L: FuncaoTransferencia, K: float) -> bool:
    r = raizes_malha_fechada(L, K)
    return bool(np.all(r.real < -TOL * max(1.0, np.abs(r).max(initial=1.0))))


# -- interseção do LGR com uma reta ----------------------------------------------
def intersecoes_reta(
    L: FuncaoTransferencia, origem: complex, direcao: complex, t_min: float | None = 0.0
) -> list[tuple[complex, float]] | None:
    """Pontos do LGR (K > 0) sobre a reta s = origem + t·direcao.

    Em s(t), D(s) + K·N(s) = 0 com K real exige que D(s)/N(s) seja real, ou seja,
    Im[D(s(t))·conj(N(s(t)))] = 0. Para t real isso é um polinômio real em t,
    cujas raízes dão os candidatos; depois K = -D/N precisa ser positivo.
    É a condição de ângulo resolvida de forma exata sobre a reta.

    Devolve [(s, K), ...] ordenado por K, ou None se a reta inteira satisfizer a
    condição de ângulo (por exemplo, o eixo jω de 1/s²).
    """
    reta = np.poly1d([complex(direcao), complex(origem)])
    D = np.poly1d(L.den(reta))
    N = np.poly1d(L.num(reta))
    Nc = np.poly1d(np.conj(N.coeffs))
    h = np.imag((D * Nc).coeffs)
    escala = np.abs(h).max(initial=0.0)
    ref = np.abs((D * Nc).coeffs).max(initial=1.0)
    if escala <= 1e-10 * ref:
        return None
    h = np.trim_zeros(np.where(np.abs(h) < 1e-12 * escala, 0.0, h / escala), "f")
    if len(h) <= 1:
        return []

    pontos: list[tuple[complex, float]] = []
    for t in np.roots(h):
        if abs(t.imag) > 1e-6 * max(1.0, abs(t)):
            continue
        t = t.real
        if t_min is not None and t < t_min - 1e-9:
            continue
        s = complex(origem) + complex(direcao) * t
        n = complex(L.num(s))
        if abs(n) < 1e-12:
            continue
        K = -complex(L.den(s)) / n
        if K.real <= 1e-12 or abs(K.imag) > 1e-5 * abs(K):
            continue
        if any(abs(s - p) < 1e-7 * max(1.0, abs(s)) for p, _ in pontos):
            continue
        pontos.append((s, K.real))
    return sorted(pontos, key=lambda p: p[1])


def intersecoes_zeta(L: FuncaoTransferencia, zeta: float) -> list[tuple[complex, float]]:
    """Pontos do LGR na semirreta de ζ constante, no semiplano superior."""
    direcao = complex(-zeta, math.sqrt(1 - zeta**2))
    return intersecoes_reta(L, 0, direcao, t_min=1e-9) or []


def intersecoes_sigma(L: FuncaoTransferencia, sigma: float) -> list[tuple[complex, float]]:
    """Pontos do LGR na reta vertical Re(s) = -σ, com Im(s) > 0."""
    return intersecoes_reta(L, complex(-sigma, 0), 1j, t_min=1e-9) or []


# -- regras de esboço -------------------------------------------------------------
@dataclass
class RegrasLGR:
    polos: np.ndarray
    zeros: np.ndarray
    centroide: float | None
    angulos_assintotas: list[float]
    segmentos_eixo_real: list[tuple[float, float]]
    separacao: list[tuple[complex, float]]
    cruzamentos_jw: list[tuple[float, float]] | None
    angulos_partida: list[tuple[complex, float]]
    angulos_chegada: list[tuple[complex, float]]
    estabilidade: str
    ganhos_criticos: list[float] = field(default_factory=list)

    @property
    def ramos(self) -> int:
        return len(self.polos)

    def texto(self) -> str:
        fc = formatar_complexo
        n, m = len(self.polos), len(self.zeros)
        linhas = [
            f"1. Ramos: {self.ramos} (um por polo de malha aberta). Começam nos polos (K = 0) "
            f"e terminam nos zeros (K → ∞); {n - m} vão para o infinito.",
            "   Polos: " + ", ".join(fc(p) for p in _ordenar(self.polos)),
            "   Zeros: " + (", ".join(fc(z) for z in _ordenar(self.zeros)) or "nenhum (finito)"),
            "2. Simétrico em relação ao eixo real (coeficientes reais).",
        ]
        segs = []
        for a, b in self.segmentos_eixo_real:
            ini = "-∞" if math.isinf(a) else f"{a:.4g}"
            segs.append(f"[{ini}, {b:.4g}]")
        linhas.append(
            "3. Eixo real: pertence ao LGR à esquerda de um número ímpar de polos e zeros reais: "
            + (", ".join(segs) or "nenhum trecho")
        )
        if self.centroide is not None:
            angs = ", ".join(f"{a:.4g}°" for a in self.angulos_assintotas)
            linhas.append(
                f"4. Assíntotas: σa = (Σpolos - Σzeros)/(n - m) = {self.centroide:.4g}; "
                f"ângulos (2k+1)·180°/(n - m) = {angs}"
            )
        else:
            linhas.append("4. Assíntotas: nenhuma (n = m, todo ramo termina num zero finito).")
        if self.separacao:
            pts = ", ".join(f"s = {fc(s)} (K = {K:.4g})" for s, K in self.separacao)
            linhas.append(f"5. Pontos de separação/chegada (dK/ds = 0): {pts}")
        else:
            linhas.append("5. Pontos de separação/chegada: nenhum com K > 0.")
        if self.cruzamentos_jw is None:
            linhas.append("6. Eixo jω: o eixo inteiro satisfaz a condição de ângulo.")
        elif self.cruzamentos_jw:
            pts = ", ".join(f"ω = {w:.4g} rad/s (K = {K:.4g})" for w, K in self.cruzamentos_jw)
            linhas.append(f"6. Cruzamentos do eixo jω: {pts}")
        else:
            linhas.append("6. Cruzamentos do eixo jω: nenhum.")
        angulos = [f"{titulo}: " + ", ".join(f"{fc(p)} → {a:.4g}°" for p, a in lista)
                   for titulo, lista in (("partida dos polos complexos", self.angulos_partida),
                                         ("chegada aos zeros complexos", self.angulos_chegada))
                   if lista]
        linhas.append("7. Ângulos de " + ("; ".join(angulos) if angulos
                                           else "partida/chegada: não há polos nem zeros complexos."))
        linhas.append(f"8. Estabilidade em malha fechada: {self.estabilidade}")
        return "\n".join(linhas)


def _ordenar(v) -> list[complex]:
    return sorted((complex(x) for x in v), key=lambda z: (round(z.real, 9), z.imag))


def _segmentos_eixo_real(polos, zeros) -> list[tuple[float, float]]:
    reais = sorted(
        x.real for x in np.concatenate([polos, zeros]) if abs(x.imag) < 1e-9 * max(1, abs(x))
    )
    if not reais:
        return []
    criticos = sorted(set(round(x, 12) for x in reais))
    segmentos = []
    limites = [-math.inf] + criticos
    for a, b in zip(limites[:-1], limites[1:]):
        meio = b - 1 if math.isinf(a) else (a + b) / 2
        if sum(1 for x in reais if x > meio) % 2 == 1:
            if segmentos and segmentos[-1][1] == a:
                segmentos[-1] = (segmentos[-1][0], b)
            else:
                segmentos.append((a, b))
    return segmentos


def _angulos_partida_chegada(polos, zeros):
    """Ângulos com que os ramos saem de polos complexos e chegam a zeros complexos.

    Para um polo p de multiplicidade q: q·θ = 180° + Σ∠(p - zeros) - Σ∠(p - outros polos).
    Para um zero z de multiplicidade q: q·θ = 180° + Σ∠(z - polos) - Σ∠(z - outros zeros).
    É a condição de ângulo aplicada a um ponto muito perto de p (ou de z).
    Com q > 1, os outros ramos ficam a múltiplos de 360°/q deste.
    """
    def ang(v):
        return math.degrees(np.angle(v))

    def calcular(pontos, outros):
        res = []
        for p in pontos:
            tol = 1e-6 * max(1, abs(p))
            if p.imag <= tol or any(abs(r[0] - p) < tol for r in res):
                continue
            q = sum(1 for x in pontos if abs(x - p) < tol)
            mesmos = sum(ang(p - x) for x in pontos if abs(x - p) >= tol)
            theta = (180 + sum(ang(p - x) for x in outros) - mesmos) / q
            res.append((p, (theta + 180) % 360 - 180))
        return res

    polos = [complex(p) for p in polos]
    zeros = [complex(z) for z in zeros]
    return calcular(polos, zeros), calcular(zeros, polos)


def regras(L: FuncaoTransferencia) -> RegrasLGR:
    polos, zeros = L.polos, L.zeros
    n, m = len(polos), len(zeros)

    if n > m:
        centroide = float((np.sum(polos) - np.sum(zeros)).real / (n - m))
        angs = [((2 * k + 1) * 180 / (n - m)) % 360 for k in range(n - m)]
    else:
        centroide, angs = None, []

    # dK/ds = 0 com K = -D/N  <=>  D'N - DN' = 0
    eq = L.den.deriv() * L.num - L.den * L.num.deriv()
    separacao = []
    for s in np.roots(eq.coeffs) if eq.order > 0 else []:
        n_s = complex(L.num(s))
        if abs(n_s) < 1e-12:
            continue
        K = -complex(L.den(s)) / n_s
        if K.real > 1e-9 and abs(K.imag) <= 1e-5 * abs(K) and s.imag >= -1e-9:
            if abs(s.imag) < 1e-7 * max(1, abs(s)):
                s = complex(s.real, 0)
            separacao.append((complex(s), K.real))
    separacao.sort(key=lambda x: x[1])

    cruz = intersecoes_reta(L, 0, 1j, t_min=0.0)
    cruzamentos = None if cruz is None else [(p.imag, K) for p, K in cruz]

    partida, chegada = _angulos_partida_chegada(polos, zeros)

    criticos = sorted({round(K, 12) for _, K in (cruzamentos or [])})
    estab = _descrever_estabilidade(L, criticos)
    return RegrasLGR(polos, zeros, centroide, angs, _segmentos_eixo_real(polos, zeros),
                     separacao, cruzamentos, partida, chegada, estab, criticos)


def _descrever_estabilidade(L: FuncaoTransferencia, criticos: list[float]) -> str:
    if not criticos:
        return "estável para todo K > 0" if estavel(L, 1.0) else "instável para todo K > 0"
    limites = [0.0] + criticos + [math.inf]
    faixas = []
    for a, b in zip(limites[:-1], limites[1:]):
        teste = b / 2 if a == 0 else (2 * a if math.isinf(b) else math.sqrt(a * b))
        if estavel(L, teste):
            faixas.append(f"{a:.5g} < K" + ("" if math.isinf(b) else f" < {b:.5g}"))
    if not faixas:
        return "instável para todo K > 0"
    return "estável para " + " e para ".join(faixas)


# -- traçado dos ramos ------------------------------------------------------------
def ganho_referencia(L: FuncaoTransferencia) -> float:
    """Ordem de grandeza de K para a escala do problema."""
    pz = np.concatenate([L.polos, L.zeros])
    escala = max(1.0, float(np.abs(pz).max(initial=1.0)))
    return ganho_no_ponto(L, 1j * escala)


def calcular_ramos(L: FuncaoTransferencia, ganhos_extras=(), pontos: int = 2500):
    """Raízes de D + K·N para K de 0 até bem além da escala do problema.

    Devolve (K, R), com R[i, j] a raiz do ramo j no ganho K[i]. As raízes de
    cada K são casadas com as do K anterior pela menor distância, para que cada
    coluna seja um ramo contínuo.
    """
    kref = ganho_referencia(L)
    extras = [k for k in ganhos_extras if k and k > 0]
    kmax = max([kref * 1e4] + [10 * k for k in extras])
    ganhos = np.concatenate([[0.0], np.logspace(math.log10(kref) - 5, math.log10(kmax), pontos),
                             extras])
    ganhos = np.unique(ganhos)
    n = L.den.order
    R = np.full((len(ganhos), n), np.nan, dtype=complex)
    anterior = None
    for i, K in enumerate(ganhos):
        r = raizes_malha_fechada(L, K)
        r = np.concatenate([r, np.full(n - len(r), np.nan)]) if len(r) < n else r[:n]
        if anterior is not None:
            d = np.abs(anterior[:, None] - r[None, :])
            d = np.where(np.isnan(d), 1e300, d)
            _, col = linear_sum_assignment(d)
            r = r[col]
        R[i] = r
        anterior = r
    return ganhos, R
