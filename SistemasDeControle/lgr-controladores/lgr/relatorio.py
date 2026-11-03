"""Relatório em texto do projeto: o passo a passo de cada controlador."""

from __future__ import annotations

import math

from .analise import erro_regime, previsao_segunda_ordem, verificar
from .especificacoes import Requisitos, formatar_complexo
from .funcao_transferencia import FuncaoTransferencia
from .lugar_raizes import regras
from .projeto import ProjetoInviavel, projetar

FC = formatar_complexo


def _titulo(texto: str) -> str:
    return f"\n{texto}\n{'=' * len(texto)}"


def _num(x: float, unidade: str = "") -> str:
    return "—" if x is None or not math.isfinite(x) else f"{x:.4g}{unidade}"


def projetar_e_relatar(G: FuncaoTransferencia, req: Requisitos, tipos=("P", "PI", "PID"),
                       mostrar_regras: bool = True, **opcoes):
    """Projeta os controladores pedidos. Devolve (texto, resultados).

    Cada resultado é {"controlador": Controlador, "verificacao": Verificacao};
    os inviáveis ficam só no texto, com o motivo.
    """
    out = [_titulo("Planta"), "G(s) =", str(G)]
    out.append(_titulo("Requisitos"))
    out.append(req.descrever() or "(nenhum)")
    if mostrar_regras:
        out.append(_titulo("Regras do LGR de G(s)"))
        out.append(regras(G).texto())
        out.append("Erro em regime só com ganho: " + erro_regime(G).texto())

    resultados = []
    for tipo in tipos:
        out.append(_titulo(f"Controlador {tipo}"))
        try:
            c = projetar(tipo, G, req, **opcoes)
        except ProjetoInviavel as e:
            out.append(f"Inviável: {e}")
            continue
        out += [f"{i}. {p}" for i, p in enumerate(c.passos, 1)]
        out.append("")
        out.append(c.descrever())
        v = verificar(c.ft, G, c.polo_projetado)
        out.append("Polos de malha fechada: " + ", ".join(FC(p) for p in sorted(v.polos, key=lambda z: (z.real, z.imag))))
        if v.estavel and v.metricas is not None:
            m = v.metricas
            if c.polo_projetado is not None:
                mp, ts, tp = previsao_segunda_ordem(c.polo_projetado)
                out.append(f"Previsto (2ª ordem): Mp = {mp:.2f} %, ts = {ts:.4g} s, tp = {tp:.4g} s")
            out.append(
                f"Simulado:            Mp = {_num(m.sobressinal, ' %')}, ts = {_num(m.tempo_acomodacao, ' s')}, "
                f"tp = {_num(m.tempo_pico, ' s')}, tr = {_num(m.tempo_subida, ' s')}, y(∞) = {m.valor_final:.4g}"
            )
        out.append("Erro em regime: " + v.erro.texto())
        for a in v.avisos:
            out.append(f"Atenção: {a}")
        resultados.append({"controlador": c, "verificacao": v})
    return "\n".join(out), resultados
