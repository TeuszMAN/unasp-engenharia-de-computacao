"""Gráficos do LGR e da resposta ao degrau (matplotlib)."""

from __future__ import annotations

import math

import numpy as np

from .analise import horizonte, resposta_degrau
from .especificacoes import Requisitos
from .funcao_transferencia import FuncaoTransferencia
from .lugar_raizes import calcular_ramos, raizes_malha_fechada, regras

# Uma cor por controlador, sempre na mesma ordem (P, PI, PID)
CORES = {"G": "#52514e", "P": "#2a78d6", "PI": "#eb6834", "PID": "#1baf7a"}
TINTA = "#0b0b0b"
TINTA_2 = "#52514e"
GRADE = "#d8d7d2"


def _estilo(ax):
    ax.grid(True, color=GRADE, linewidth=0.6)
    for lado in ("top", "right"):
        ax.spines[lado].set_visible(False)
    for lado in ("left", "bottom"):
        ax.spines[lado].set_color(TINTA_2)
    ax.tick_params(colors=TINTA_2, labelsize=8)


def _limites(pontos: list[complex], raio: float | None = None):
    p = np.array([complex(x) for x in pontos if np.isfinite(x)])
    if raio is not None:
        p = p[np.abs(p) <= raio]
    xr = [p.real.min(), p.real.max(), 0.0]
    yr = [abs(p.imag).max(), 1e-9]
    x0, x1 = min(xr), max(xr)
    ymax = max(yr)
    larg = max(x1 - x0, ymax, 1.0)
    margem = 0.25 * larg
    x0, x1 = x0 - margem, x1 + margem
    ymax = max(ymax + margem, 0.6 * (x1 - x0) / 2)
    return (x0, x1), (-ymax, ymax)


def plot_lgr(ax, L: FuncaoTransferencia, K: float | None = None, req: Requisitos | None = None,
             cor: str = CORES["G"], titulo: str = "", polo_projetado: complex | None = None,
             anotar_regras: bool = False):
    """LGR de K·L(s), com polos de malha fechada no ganho K."""
    r = regras(L)
    extras = [k for _, k in r.separacao] + r.ganhos_criticos + ([K] if K else [])
    ganhos, R = calcular_ramos(L, extras)

    interesse = list(r.polos) + list(r.zeros) + [s for s, _ in r.separacao]
    interesse += [1j * w for w, _ in (r.cruzamentos_jw or [])]
    if r.centroide is not None and len(r.angulos_assintotas) > 1:
        interesse.append(r.centroide)  # com uma assíntota só (180°), o centróide não ajuda
    raizes_k = raizes_malha_fechada(L, K) if K else []
    interesse += list(raizes_k)
    if req is not None and req.polo is not None:
        interesse.append(req.polo)
    if polo_projetado is not None:
        interesse.append(polo_projetado)
    # Com um polo desejado, a janela fica em volta dele: polos e zeros muito
    # distantes achatariam a região dominante e são só citados no canto.
    alvos = [abs(x) for x in (polo_projetado, req.polo if req is not None else None)
             if x is not None]
    raio = 2.5 * max(alvos) if alvos else None
    xl, yl = _limites(interesse, raio)
    fora = [] if raio is None else [
        (nome, x) for nome, lista in (("polo", r.polos), ("zero", r.zeros))
        for x in lista if abs(x) > raio
    ]

    _estilo(ax)
    ax.axhline(0, color=TINTA_2, linewidth=0.8)
    ax.axvline(0, color=TINTA_2, linewidth=0.8)

    # assíntotas
    if r.centroide is not None and len(r.angulos_assintotas) > 0:
        comp = 3 * max(xl[1] - xl[0], yl[1] - yl[0])
        for a in r.angulos_assintotas:
            ar = math.radians(a)
            ax.plot([r.centroide, r.centroide + comp * math.cos(ar)],
                    [0, comp * math.sin(ar)], color=TINTA_2, linestyle=":", linewidth=0.8)

    # requisitos: reta de ζ e reta de σ
    if req is not None:
        comp = 3 * max(xl[1] - xl[0], yl[1] - yl[0])
        if req.zeta is not None:
            th = math.acos(req.zeta)
            for sinal in (1, -1):
                ax.plot([0, -comp * math.cos(th)], [0, sinal * comp * math.sin(th)],
                        color=TINTA_2, linestyle="--", linewidth=0.8)
        if req.sigma is not None:
            ax.axvline(-req.sigma, color=TINTA_2, linestyle="-.", linewidth=0.8)
        if req.polo is not None:
            for s in (req.polo, req.polo.conjugate()):
                ax.plot(s.real, s.imag, marker="*", markersize=12, color="white",
                        markeredgecolor=TINTA, markeredgewidth=1, zorder=5)

    for j in range(R.shape[1]):
        ax.plot(R[:, j].real, R[:, j].imag, color=cor, linewidth=1.6)

    ax.plot(r.polos.real, r.polos.imag, "x", color=TINTA, markersize=9, markeredgewidth=1.6)
    if len(r.zeros):
        ax.plot(r.zeros.real, r.zeros.imag, "o", markerfacecolor="white", markeredgecolor=TINTA,
                markersize=8, markeredgewidth=1.4)
    if K:
        ax.plot(np.real(raizes_k), np.imag(raizes_k), "s", color=cor, markersize=7,
                markeredgecolor="white", markeredgewidth=1.2, zorder=6)

    if anotar_regras:
        _anotar_regras(ax, r)
    ax.set_xlim(*xl)
    ax.set_ylim(*yl)
    if fora:
        from .especificacoes import formatar_complexo
        texto = "fora da janela: " + ", ".join(f"{n} em {formatar_complexo(x)}" for n, x in fora)
        ax.text(0.02, 0.02, texto, transform=ax.transAxes, fontsize=7.5, color=TINTA_2,
                ha="left", va="bottom")
    ax.set_xlabel("Re(s)", color=TINTA_2, fontsize=9)
    ax.set_ylabel("Im(s)", color=TINTA_2, fontsize=9)
    if titulo:
        ax.set_title(titulo, color=TINTA, fontsize=10, loc="left")


def _anotar_regras(ax, r):
    """Marca no gráfico os pontos calculados pelas regras de esboço."""
    estilo = dict(fontsize=8, color=TINTA, textcoords="offset points",
                  bbox=dict(boxstyle="round,pad=0.2", fc="white", ec="none", alpha=0.85))
    for s, K in r.separacao:
        ax.plot(s.real, s.imag, "D", color="white", markeredgecolor=TINTA, markersize=6, zorder=6)
        ax.annotate(f"separação\ns = {s.real:.3g}, K = {K:.3g}", (s.real, s.imag),
                    xytext=(-8, -26), ha="right", **estilo)
    for w, K in r.cruzamentos_jw or []:
        if w <= 0:
            continue
        ax.plot(0, w, "o", color=TINTA, markersize=5, zorder=6)
        ax.annotate(f"jω = j{w:.3g}\nK = {K:.3g} (limite)", (0, w), xytext=(8, -4),
                    ha="left", **estilo)
    if r.centroide is not None and len(r.angulos_assintotas) > 1:
        ax.plot(r.centroide, 0, "+", color=TINTA, markersize=9, zorder=6)
        ax.annotate(f"σa = {r.centroide:.3g}", (r.centroide, 0), xytext=(0, 8), ha="center",
                    **estilo)


def figura_projeto(G: FuncaoTransferencia, req: Requisitos, resultados: list[dict],
                   titulo: str | None = None):
    """Um LGR por controlador na linha de cima e as respostas ao degrau embaixo.

    Cada item de `resultados` tem: controlador (Controlador) e verificacao (Verificacao).
    """
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D

    n = max(1, len(resultados))
    fig = plt.figure(figsize=(4.6 * n, 8.4), layout="constrained")
    gs = fig.add_gridspec(2, n, height_ratios=[1.15, 1])

    for i, res in enumerate(resultados):
        c = res["controlador"]
        ax = fig.add_subplot(gs[0, i])
        plot_lgr(ax, c.forma * G, c.K, req, CORES[c.tipo], f"LGR com {c.tipo}  (K = {c.K:.4g})",
                 c.polo_projetado)

    ax = fig.add_subplot(gs[1, :])
    _estilo(ax)
    estaveis = [r for r in resultados if r["verificacao"].estavel]
    # janela comum: a do polo projetado, esticada até a acomodação mais lenta (máx. 5×)
    t_max = 0.0
    for res in estaveis:
        c, v = res["controlador"], res["verificacao"]
        t_graf, _ = horizonte(v.T, c.polo_projetado)
        ts = v.metricas.tempo_acomodacao
        t_max = max(t_max, t_graf, min(1.1 * ts, 5 * t_graf) if math.isfinite(ts) else 0)
    t = np.linspace(0, t_max or 10, 3000)
    for res in estaveis:
        c, v = res["controlador"], res["verificacao"]
        m = v.metricas
        rotulo = (f"{c.tipo}: Mp = {m.sobressinal:.1f} %, ts = {m.tempo_acomodacao:.3g} s, "
                  f"y(∞) = {m.valor_final:.3g}")
        ax.plot(t, resposta_degrau(v.T, t), color=CORES[c.tipo], linewidth=2, label=rotulo)
    ax.axhline(1.0, color=TINTA_2, linewidth=0.8, linestyle="--")
    if t_max:
        ax.set_xlim(0, t_max)
    ax.set_xlabel("t (s)", color=TINTA_2, fontsize=9)
    ax.set_ylabel("y(t)", color=TINTA_2, fontsize=9)
    ax.set_title("Resposta ao degrau unitário em malha fechada", color=TINTA, fontsize=10, loc="left")
    ax.legend(frameon=False, fontsize=8, loc="lower right", labelcolor=TINTA)

    legenda = [
        Line2D([], [], marker="x", linestyle="", color=TINTA, label="polo de malha aberta"),
        Line2D([], [], marker="o", linestyle="", markerfacecolor="white", markeredgecolor=TINTA,
               label="zero de malha aberta"),
        Line2D([], [], marker="s", linestyle="", color=TINTA_2, label="polos de malha fechada"),
        Line2D([], [], marker="*", linestyle="", markerfacecolor="white", markeredgecolor=TINTA,
               markersize=11, label="polo desejado"),
        Line2D([], [], linestyle="--", color=TINTA_2, label="ζ constante"),
        Line2D([], [], linestyle="-.", color=TINTA_2, label="σ = 4/ts"),
        Line2D([], [], linestyle=":", color=TINTA_2, label="assíntotas"),
    ]
    fig.legend(handles=legenda, loc="outside lower center", ncol=7 if n >= 3 else 4,
               frameon=False, fontsize=8)
    if titulo:
        fig.suptitle(titulo, fontsize=11, x=0.01, ha="left")
    return fig


def figura_lgr(G: FuncaoTransferencia, req: Requisitos | None = None, titulo: str = "LGR de G(s)"):
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(6.5, 5.5), layout="constrained")
    plot_lgr(ax, G, None, req, CORES["G"], "", anotar_regras=True)
    fig.suptitle(titulo, fontsize=11, x=0.01, ha="left")
    return fig
