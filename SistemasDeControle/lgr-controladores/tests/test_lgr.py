"""Testes com exemplos clássicos de livro (Ogata e Nise)."""

import math
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from lgr import (  # noqa: E402
    FuncaoTransferencia,
    ProjetoInviavel,
    Requisitos,
    deficiencia_angular,
    erro_regime,
    projetar_p,
    projetar_pi,
    projetar_pid,
    regras,
    sobressinal_de_zeta,
    verificar,
    zeta_de_sobressinal,
)
from lgr.lugar_raizes import raizes_malha_fechada  # noqa: E402

G_OGATA = FuncaoTransferencia.de_polos_zeros([], [0, -1, -2])  # 1/(s(s+1)(s+2))
G_NISE_91 = FuncaoTransferencia.de_polos_zeros([], [-1, -2, -10])
G_NISE_95 = FuncaoTransferencia.de_polos_zeros([-8], [-3, -6, -10])


def tem_raiz(L, K, s, tol=1e-6):
    return np.min(np.abs(raizes_malha_fechada(L, K) - s)) < tol * max(1, abs(s))


def test_conversao_sobressinal_zeta():
    assert zeta_de_sobressinal(16.3) == pytest.approx(0.5, abs=1e-3)
    assert zeta_de_sobressinal(20) == pytest.approx(0.456, abs=1e-3)
    for z in (0.1, 0.4, 0.7, 0.9):
        assert zeta_de_sobressinal(sobressinal_de_zeta(z)) == pytest.approx(z)


def test_polo_desejado():
    req = Requisitos.de(zeta=0.5, ts=4)  # σ = 1, ωn = 2
    assert req.polo == pytest.approx(complex(-1, math.sqrt(3)))
    req = Requisitos.de(ts=2, tp=math.pi)
    assert req.polo == pytest.approx(complex(-2, 1))
    with pytest.raises(ValueError):
        Requisitos.de(sobressinal=10, ts=1, tp=1)


def test_regras_ogata():
    r = regras(G_OGATA)
    assert r.centroide == pytest.approx(-1)
    assert sorted(r.angulos_assintotas) == pytest.approx([60, 180, 300])
    assert r.segmentos_eixo_real == [(-math.inf, -2), (-1, 0)]
    (s, K), = r.separacao
    assert s.real == pytest.approx(-0.4226, abs=1e-4)
    assert K == pytest.approx(0.3849, abs=1e-4)
    (w, K), = r.cruzamentos_jw
    assert w == pytest.approx(math.sqrt(2))
    assert K == pytest.approx(6)
    assert "0 < K < 6" in r.estabilidade


def test_angulo_partida():
    G = FuncaoTransferencia.de_polos_zeros([], [complex(-1, 2), complex(-1, -2), -4])
    (p, a), = regras(G).angulos_partida
    assert a == pytest.approx(180 - 90 - math.degrees(math.atan2(2, 3)))


def test_p_ogata():
    c = projetar_p(G_OGATA, Requisitos.de(zeta=0.5))
    assert c.K == pytest.approx(1.0383, abs=2e-3)
    assert c.polo_projetado == pytest.approx(complex(-0.3337, 0.5780), abs=1e-3)


def test_p_nise_9_1():
    c = projetar_p(G_NISE_91, Requisitos.de(zeta=0.174))
    assert c.K == pytest.approx(164.6, abs=0.2)
    assert c.polo_projetado == pytest.approx(complex(-0.694, 3.926), abs=2e-3)


def test_p_inviavel_quando_lgr_nao_cruza_reta():
    G = FuncaoTransferencia.de_polos_zeros([], [complex(-1, 2), complex(-1, -2), -4])
    with pytest.raises(ProjetoInviavel):
        projetar_p(G, Requisitos.de(zeta=0.5))


@pytest.mark.parametrize("G, req", [
    (G_OGATA, Requisitos.de(sobressinal=10, ts=12)),
    (G_NISE_91, Requisitos.de(sobressinal=20, ts=4)),
])
def test_pi_angulo_posiciona_polo(G, req):
    c = projetar_pi(G, req, metodo="angulo")
    sd = req.polo
    L = c.forma * G
    assert abs(deficiencia_angular(L, sd)) < 1e-6
    assert tem_raiz(L, c.K, sd)
    kp, ki, kd = c.ganhos_paralelos
    assert ki == pytest.approx(c.K * c.zeros[0]) and kd == 0


def test_pi_ideal_zera_erro_ao_degrau():
    req = Requisitos.de(zeta=0.174)
    p = projetar_p(G_NISE_91, req)
    c = projetar_pi(G_NISE_91, req, metodo="ideal")
    assert erro_regime(p.ft * G_NISE_91).degrau == pytest.approx(0.108, abs=1e-3)
    assert erro_regime(c.ft * G_NISE_91).degrau == 0
    # o polo dominante quase não se move
    assert abs(c.polo_projetado - p.polo_projetado) < 0.05 * abs(p.polo_projetado)
    v = verificar(c.ft, G_NISE_91, c.polo_projetado)
    assert v.estavel and v.metricas.valor_final == pytest.approx(1)


def test_pid_nise_9_5():
    req = Requisitos.de(sobressinal=20, tp=0.198)
    c = projetar_pid(G_NISE_95, req)
    sd = req.polo
    assert sd == pytest.approx(complex(-8.13, 15.87), abs=0.01)
    assert tem_raiz(c.forma * G_NISE_95, c.K, sd)
    kp, ki, kd = c.ganhos_paralelos
    z1, z2 = c.zeros
    assert (kp, ki, kd) == pytest.approx((c.K * (z1 + z2), c.K * z1 * z2, c.K))
    v = verificar(c.ft, G_NISE_95, sd)
    assert v.estavel
    assert v.erro.degrau == 0
    assert v.metricas.tempo_pico == pytest.approx(0.198, rel=0.15)


def test_pi_rejeita_zero_no_semiplano_direito():
    # requisito de tempo lento demais para a planta: o zero iria para o semiplano direito
    with pytest.raises(ProjetoInviavel):
        projetar_pi(G_OGATA, Requisitos.de(sobressinal=16.3, ts=6), metodo="angulo")


def test_erro_regime_tipos():
    assert erro_regime(G_NISE_91).tipo == 0
    e = erro_regime(G_OGATA)
    assert e.tipo == 1 and e.Kv == pytest.approx(0.5)
    G2 = FuncaoTransferencia([1, 1], [1, 0, 0])
    assert erro_regime(G2).tipo == 2
