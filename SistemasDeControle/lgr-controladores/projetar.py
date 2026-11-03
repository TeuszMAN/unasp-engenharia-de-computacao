"""Linha de comando: projeta P, PI e PID pelo LGR para uma planta G(s).

Exemplos:
    python projetar.py --den 1 9 18 0 --sobressinal 16 --ts 2
    python projetar.py --polos 0 -3 -6 --sobressinal 16 --controlador p
    python projetar.py --num 1 8 --den 1 19 108 180 --zeta 0.456 --ts 1.5 --salvar saidas/pid.png
"""

from __future__ import annotations

import argparse
import re
import sys

from lgr import FuncaoTransferencia, Requisitos, projetar_e_relatar


_COMPLEXO_NEGATIVO = re.compile(r"^-[\d.]+(e-?\d+)?[+-][\d.]*(e-?\d+)?[ij]$")


def _complexos(valores):
    return [complex(v.strip().replace("i", "j")) for v in valores]


def _proteger_complexos(argv):
    """O argparse confunde '-1+2j' com uma opção; um espaço na frente evita isso."""
    return [" " + a if _COMPLEXO_NEGATIVO.match(a) else a for a in argv]


def montar_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Projeto de controladores P, PI e PID pelo Lugar Geométrico das Raízes "
                    "(realimentação unitária).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Coeficientes em potências decrescentes de s: --den 1 3 2 é s² + 3s + 2.\n"
               "Números negativos funcionam direto: --polos 0 -3 -6.",
    )
    planta = p.add_argument_group("planta G(s)")
    planta.add_argument("--num", nargs="+", type=float, help="coeficientes do numerador (padrão: 1)")
    planta.add_argument("--den", nargs="+", type=float, help="coeficientes do denominador")
    planta.add_argument("--polos", nargs="+", help="polos (aceita complexos, ex.: -1+2j)")
    planta.add_argument("--zeros", nargs="+", default=[], help="zeros")
    planta.add_argument("--ganho", type=float, default=1.0, help="ganho com --polos/--zeros")

    req = p.add_argument_group("requisitos (no máximo dois)")
    req.add_argument("--sobressinal", "--mp", type=float, help="sobressinal máximo em %%")
    req.add_argument("--zeta", type=float, help="coeficiente de amortecimento ζ")
    req.add_argument("--ts", type=float, help="tempo de acomodação (2%%) em s")
    req.add_argument("--tp", type=float, help="tempo de pico em s")
    req.add_argument("--wn", type=float, help="frequência natural em rad/s")

    proj = p.add_argument_group("projeto")
    proj.add_argument("--controlador", "-c", choices=["p", "pi", "pid", "todos"], default="todos")
    proj.add_argument("--metodo-pi", choices=["auto", "angulo", "ideal"], default="auto",
                      help="angulo: polo exato no ponto desejado; ideal: zero perto da origem "
                           "a partir do projeto P (padrão auto)")
    proj.add_argument("--zero-pi", type=float,
                      help="posição z do zero integral (s + z); padrão 10%% de |Re| do polo")

    saida = p.add_argument_group("saída")
    saida.add_argument("--sem-regras", action="store_true", help="não imprimir as regras do LGR")
    saida.add_argument("--salvar", help="salvar a figura neste arquivo (png, pdf, svg)")
    saida.add_argument("--sem-janela", action="store_true", help="não abrir a janela do gráfico")
    return p


def main(argv=None) -> int:
    args = montar_parser().parse_args(_proteger_complexos(sys.argv[1:] if argv is None else argv))

    if (args.num or args.den) and (args.polos or args.zeros):
        print("Use --num/--den ou --polos/--zeros/--ganho, sem misturar as duas formas.",
              file=sys.stderr)
        return 2
    if args.den is not None:
        G = FuncaoTransferencia(args.num or [1.0], args.den)
    elif args.polos is not None:
        G = FuncaoTransferencia.de_polos_zeros(_complexos(args.zeros), _complexos(args.polos), args.ganho)
    else:
        print("Informe a planta com --den (e --num) ou com --polos (e --zeros).", file=sys.stderr)
        return 2

    try:
        req = Requisitos.de(sobressinal=args.sobressinal, ts=args.ts, tp=args.tp,
                            zeta=args.zeta, wn=args.wn)
    except ValueError as e:
        print(f"Requisitos inválidos: {e}", file=sys.stderr)
        return 2

    tipos = ("P", "PI", "PID") if args.controlador == "todos" else (args.controlador.upper(),)
    texto, resultados = projetar_e_relatar(G, req, tipos, mostrar_regras=not args.sem_regras,
                                           metodo_pi=args.metodo_pi, zero_pi=args.zero_pi)
    print(texto)

    if not resultados or (args.sem_janela and not args.salvar):
        return 0 if resultados else 1

    import matplotlib
    if args.sem_janela:
        matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from lgr.graficos import figura_projeto

    fig = figura_projeto(G, req, resultados)
    if args.salvar:
        fig.savefig(args.salvar, dpi=150)
        print(f"\nFigura salva em {args.salvar}")
    if not args.sem_janela:
        plt.show()
    return 0


if __name__ == "__main__":
    sys.exit(main())
