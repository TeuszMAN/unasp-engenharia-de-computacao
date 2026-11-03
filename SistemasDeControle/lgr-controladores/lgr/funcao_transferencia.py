"""Função de transferência racional N(s)/D(s), com polinômios do numpy.

Os coeficientes seguem a convenção do MATLAB e do Octave: potências
decrescentes de s. Assim [1, 3, 2] é s² + 3s + 2.
"""

from __future__ import annotations

import numpy as np


def _limpar(p: np.poly1d) -> np.poly1d:
    """Descarta parte imaginária residual (vinda de raízes conjugadas)."""
    c = np.atleast_1d(np.asarray(p.coeffs))
    if np.iscomplexobj(c) and np.allclose(c.imag, 0, atol=1e-9 * max(1.0, np.abs(c).max())):
        c = c.real
    return np.poly1d(c)


def formatar_polinomio(p: np.poly1d, var: str = "s") -> str:
    c = np.atleast_1d(p.coeffs)
    n = len(c) - 1
    termos = []
    for i, a in enumerate(c):
        a = float(np.real(a))
        if abs(a) < 1e-12:
            continue
        g = n - i
        mag = abs(a)
        if g == 0:
            corpo = f"{mag:.5g}"
        else:
            coef = "" if abs(mag - 1) < 1e-12 else f"{mag:.5g} "
            corpo = coef + (var if g == 1 else f"{var}^{g}")
        sinal = "-" if a < 0 else "+"
        termos.append((sinal, corpo))
    if not termos:
        return "0"
    texto = ("-" if termos[0][0] == "-" else "") + termos[0][1]
    for sinal, corpo in termos[1:]:
        texto += f" {sinal} {corpo}"
    return texto


class FuncaoTransferencia:
    def __init__(self, num, den):
        self.num = _limpar(np.poly1d(num))
        self.den = _limpar(np.poly1d(den))
        if not np.any(self.den.coeffs):
            raise ValueError("O denominador não pode ser nulo.")

    @classmethod
    def de_polos_zeros(cls, zeros=(), polos=(), ganho=1.0) -> "FuncaoTransferencia":
        num = ganho * np.poly1d(np.poly(list(zeros)) if len(zeros) else [1.0])
        den = np.poly1d(np.poly(list(polos)) if len(polos) else [1.0])
        return cls(num, den)

    # -- avaliação e álgebra -------------------------------------------------
    def __call__(self, s):
        return self.num(s) / self.den(s)

    def __mul__(self, outro):
        if isinstance(outro, FuncaoTransferencia):
            return FuncaoTransferencia(self.num * outro.num, self.den * outro.den)
        return FuncaoTransferencia(outro * self.num, self.den)

    __rmul__ = __mul__

    def realimentar(self) -> "FuncaoTransferencia":
        """Malha fechada com realimentação unitária: L/(1+L) = N/(D+N)."""
        return FuncaoTransferencia(self.num, self.den + self.num)

    # -- características ------------------------------------------------------
    @property
    def polos(self) -> np.ndarray:
        return np.roots(self.den.coeffs)

    @property
    def zeros(self) -> np.ndarray:
        return np.roots(self.num.coeffs)

    @property
    def ganho_dc(self) -> float:
        return complex(self(0)).real

    def __str__(self) -> str:
        n = formatar_polinomio(self.num)
        d = formatar_polinomio(self.den)
        largura = max(len(n), len(d))
        return f"{n:^{largura}}\n{'-' * largura}\n{d:^{largura}}"
