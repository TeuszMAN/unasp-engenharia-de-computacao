"""Verificação do projeto: malha fechada, resposta ao degrau e erro em regime.

O projeto pelo LGR supõe que o par de polos escolhido domina a resposta. Aqui
simulamos a malha fechada completa para conferir essa hipótese.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
from scipy import signal

from .especificacoes import formatar_complexo, sobressinal_de_zeta
from .funcao_transferencia import FuncaoTransferencia

FC = formatar_complexo


@dataclass
class Metricas:
    sobressinal: float
    tempo_pico: float
    tempo_acomodacao: float
    tempo_subida: float
    valor_final: float


@dataclass
class ErroRegime:
    tipo: int
    Kp: float
    Kv: float
    Ka: float

    @property
    def degrau(self) -> float:
        return 1 / (1 + self.Kp) if math.isfinite(self.Kp) else 0.0

    @property
    def rampa(self) -> float:
        return math.inf if self.Kv == 0 else (0.0 if math.isinf(self.Kv) else 1 / self.Kv)

    def texto(self) -> str:
        def f(x):
            return "∞" if math.isinf(x) else f"{x:.4g}"
        return (
            f"Tipo {self.tipo}: Kp = {f(self.Kp)}, Kv = {f(self.Kv)}, Ka = {f(self.Ka)}; "
            f"erro ao degrau = {f(self.degrau)}, erro à rampa = {f(self.rampa)}"
        )


def erro_regime(L: FuncaoTransferencia) -> ErroRegime:
    """Constantes de erro estático de L(s) = C(s)G(s) com realimentação unitária."""
    escala = max(1.0, float(np.abs(np.concatenate([L.polos, L.zeros])).max(initial=1.0)))
    tol = 1e-7 * escala
    polos0 = int(np.sum(np.abs(L.polos) < tol))
    zeros0 = int(np.sum(np.abs(L.zeros) < tol))
    num, den = L.num, L.den
    s = np.poly1d([1.0, 0.0])
    for _ in range(min(polos0, zeros0)):
        num, den = np.polydiv(num, s)[0], np.polydiv(den, s)[0]
    tipo = polos0 - zeros0
    if tipo < 0:
        return ErroRegime(0, 0.0, 0.0, 0.0)
    for _ in range(tipo):
        den = np.polydiv(den, s)[0]
    k0 = float(np.real(num(0) / den(0)))
    inf = math.inf
    Kp = k0 if tipo == 0 else inf
    Kv = 0.0 if tipo == 0 else (k0 if tipo == 1 else inf)
    Ka = 0.0 if tipo <= 1 else (k0 if tipo == 2 else inf)
    return ErroRegime(tipo, Kp, Kv, Ka)


def resposta_degrau(T: FuncaoTransferencia, t: np.ndarray) -> np.ndarray:
    sis = signal.lti(np.real(T.num.coeffs), np.real(T.den.coeffs))
    _, y = signal.step(sis, T=t)
    return y


def horizonte(T: FuncaoTransferencia, polo_dominante: complex | None) -> tuple[float, float]:
    """(tempo para o gráfico, tempo para as métricas)."""
    p = T.polos
    p = p[p.real < 0]
    sig_dom = abs(polo_dominante.real) if polo_dominante is not None else (
        abs(p.real).min() if len(p) else 1.0)
    t_graf = 2.0 * 4 / sig_dom
    sig_lento = abs(p.real).min() if len(p) else sig_dom
    t_met = min(max(t_graf, 1.5 * 4 / sig_lento), 400 * t_graf)
    return t_graf, t_met


def metricas(t: np.ndarray, y: np.ndarray, y_final: float) -> Metricas:
    if not np.all(np.isfinite(y)) or y_final == 0:
        return Metricas(math.nan, math.nan, math.nan, math.nan, y_final)
    yn = y / y_final
    i_pico = int(np.argmax(yn))
    mp = max(0.0, (yn[i_pico] - 1) * 100)
    tp = float(t[i_pico]) if mp > 0.01 else math.nan  # sem sobressinal não há pico
    fora = np.nonzero(np.abs(yn - 1) > 0.02)[0]
    if len(fora) == 0:
        ts = 0.0
    elif fora[-1] + 1 < len(t):
        ts = float(t[fora[-1] + 1])
    else:
        ts = math.nan
    t10 = np.nonzero(yn >= 0.1)[0]
    t90 = np.nonzero(yn >= 0.9)[0]
    tr = float(t[t90[0]] - t[t10[0]]) if len(t10) and len(t90) else math.nan
    return Metricas(mp, tp, ts, tr, y_final)


def _quase_cancela(z: complex, p: complex, sd: complex) -> bool:
    """Polo e zero tão próximos (perto deles ou na escala do polo dominante) que se anulam."""
    return abs(z - p) < max(0.1 * abs(p), 0.02 * abs(sd))


@dataclass
class Verificacao:
    T: FuncaoTransferencia
    polos: np.ndarray
    zeros: np.ndarray
    estavel: bool
    metricas: Metricas | None
    erro: ErroRegime
    avisos: list[str]
    t: np.ndarray
    y: np.ndarray


def verificar(C: FuncaoTransferencia, G: FuncaoTransferencia,
              polo_projetado: complex | None) -> Verificacao:
    L = C * G
    T = L.realimentar()
    polos, zeros = T.polos, T.zeros
    escala = max(1.0, float(np.abs(polos).max(initial=1.0)))
    est = bool(np.all(polos.real < -1e-9 * escala))
    erro = erro_regime(L)
    avisos = []
    if not est:
        avisos.append("Malha fechada instável.")
        t = np.linspace(0, 10, 500)
        return Verificacao(T, polos, zeros, False, None, erro, avisos, t, np.full_like(t, np.nan))

    t_graf, t_met = horizonte(T, polo_projetado)
    # resolução de ~4000 pontos na janela do gráfico, até 200 mil no total
    n = min(200_000, max(4000, int(4000 * t_met / t_graf)))
    t = np.linspace(0, t_met, n)
    y = resposta_degrau(T, t)
    m = metricas(t, y, T.ganho_dc)

    if polo_projetado is not None:
        sd = polo_projetado
        for p in polos:
            if abs(p - sd) < 1e-4 * abs(sd) or abs(p - sd.conjugate()) < 1e-4 * abs(sd):
                continue
            razao = p.real / sd.real
            perto = [z for z in zeros if _quase_cancela(z, p, sd)]
            if perto:
                if razao < 1:
                    efeito = ("deixa uma cauda lenta, que é a que leva o erro a zero; um zero "
                              "integral mais perto da origem (--zero-pi) diminui a cauda, mas a "
                              "deixa mais lenta")
                else:
                    efeito = "efeito pequeno na resposta"
                avisos.append(f"Polo {FC(p)} quase cancelado pelo zero {FC(perto[0])}: {efeito}.")
            elif razao < 1:
                avisos.append(
                    f"Polo {FC(p)} é mais lento que o polo projetado (parte real {razao:.2f}× a "
                    "dele) e não está cancelado por um zero: é ele que domina a resposta."
                )
            elif razao < 5:
                avisos.append(
                    f"Polo {FC(p)} tem parte real só {razao:.2f}× a do polo projetado (a regra "
                    "prática pede ~5×): a aproximação de 2ª ordem fica menos precisa."
                )
        for z in zeros:
            if abs(z.real) < 5 * abs(sd.real) and not any(_quase_cancela(z, p, sd) for p in polos):
                avisos.append(
                    f"Zero de malha fechada em {FC(z)}, perto da região dominante e sem polo "
                    "que o cancele: muda o sobressinal previsto (em geral, aumenta)."
                )
    return Verificacao(T, polos, zeros, est, m, erro, avisos, t, y)


def previsao_segunda_ordem(s: complex) -> tuple[float, float, float]:
    """(sobressinal %, ts, tp) previstos para um par de polos dominantes em s."""
    wn = abs(s)
    zeta = -s.real / wn
    return sobressinal_de_zeta(zeta), 4 / -s.real, math.pi / abs(s.imag) if s.imag else math.inf
