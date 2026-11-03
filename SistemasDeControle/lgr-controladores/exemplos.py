"""Exemplos para estudar o projeto pelo LGR, em ordem de dificuldade.

    python exemplos.py            # roda todos, salva figuras e relatórios em saidas/
    python exemplos.py 3          # só o exemplo 3
    python exemplos.py --listar

As plantas vêm de exemplos clássicos dos livros do Ogata e do Nise, para que
dê para conferir os números com a resolução do livro.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

from lgr import FuncaoTransferencia, Requisitos, projetar_e_relatar  # noqa: E402
from lgr.graficos import figura_lgr, figura_projeto  # noqa: E402

SAIDAS = Path(__file__).resolve().parent / "saidas"

EXEMPLOS = [
    {
        "titulo": "Regras de esboço do LGR",
        "ideia": "Antes de projetar: onde ficam os ramos, assíntotas, separação e limite de estabilidade.",
        "G": FuncaoTransferencia.de_polos_zeros([], [0, -1, -2]),
        "req": Requisitos.de(zeta=0.5),
        "tipos": (),
    },
    {
        "titulo": "Controlador P: ajuste de ganho",
        "ideia": "O P só escolhe um ponto no LGR original. Aqui o LGR cruza a reta de ζ = 0,174.",
        "G": FuncaoTransferencia.de_polos_zeros([], [-1, -2, -10]),
        "req": Requisitos.de(zeta=0.174),
        "tipos": ("P",),
    },
    {
        "titulo": "PI como compensação integral ideal",
        "ideia": "Mesma planta e mesmo ζ: o zero perto da origem zera o erro ao degrau sem mudar o transitório.",
        "G": FuncaoTransferencia.de_polos_zeros([], [-1, -2, -10]),
        "req": Requisitos.de(zeta=0.174),
        "tipos": ("P", "PI"),
        "opcoes": {"metodo_pi": "ideal"},
    },
    {
        "titulo": "PI pela condição de ângulo",
        "ideia": "Com sobressinal e ts, o zero do PI é posto onde faz o LGR passar pelo polo desejado.",
        "G": FuncaoTransferencia.de_polos_zeros([], [-1, -2, -10]),
        "req": Requisitos.de(sobressinal=20, ts=4),
        "tipos": ("P", "PI"),
        "opcoes": {"metodo_pi": "angulo"},
    },
    {
        "titulo": "PID: transitório mais rápido e erro nulo",
        "ideia": "O P não alcança o tp pedido e o PI precisaria de um zero no semiplano direito; o PID resolve.",
        "G": FuncaoTransferencia.de_polos_zeros([-8], [-3, -6, -10]),
        "req": Requisitos.de(sobressinal=20, tp=0.198),
        "tipos": ("P", "PI", "PID"),
    },
]


def rodar(i: int) -> None:
    ex = EXEMPLOS[i - 1]
    cab = f"Exemplo {i}: {ex['titulo']}"
    texto, resultados = projetar_e_relatar(ex["G"], ex["req"], ex["tipos"], **ex.get("opcoes", {}))
    texto = f"{cab}\n{'#' * len(cab)}\n{ex['ideia']}\n{texto}\n"
    print(texto)
    SAIDAS.mkdir(exist_ok=True)
    (SAIDAS / f"exemplo{i}.txt").write_text(texto, encoding="utf-8")
    if resultados:
        fig = figura_projeto(ex["G"], ex["req"], resultados, cab)
    else:
        fig = figura_lgr(ex["G"], ex["req"], cab)
    fig.savefig(SAIDAS / f"exemplo{i}.png", dpi=130)
    print(f"-> {SAIDAS / f'exemplo{i}.png'}\n")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("numeros", nargs="*", type=int, help="exemplos a rodar (padrão: todos)")
    p.add_argument("--listar", action="store_true")
    args = p.parse_args()
    if args.listar:
        for i, ex in enumerate(EXEMPLOS, 1):
            print(f"{i}. {ex['titulo']}: {ex['ideia']}")
        return
    for i in args.numeros or range(1, len(EXEMPLOS) + 1):
        rodar(i)


if __name__ == "__main__":
    main()
