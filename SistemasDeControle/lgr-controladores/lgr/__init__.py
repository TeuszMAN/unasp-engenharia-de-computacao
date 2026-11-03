"""Projeto de controladores P, PI e PID pelo Lugar Geométrico das Raízes."""

from .especificacoes import Requisitos, sobressinal_de_zeta, zeta_de_sobressinal
from .funcao_transferencia import FuncaoTransferencia
from .lugar_raizes import (
    angulo,
    deficiencia_angular,
    ganho_no_ponto,
    intersecoes_sigma,
    intersecoes_zeta,
    regras,
)
from .projeto import (
    Controlador,
    ProjetoInviavel,
    projetar,
    projetar_p,
    projetar_pi,
    projetar_pid,
)
from .analise import erro_regime, verificar
from .relatorio import projetar_e_relatar

__all__ = [
    "Requisitos", "sobressinal_de_zeta", "zeta_de_sobressinal", "FuncaoTransferencia",
    "angulo", "deficiencia_angular", "ganho_no_ponto", "intersecoes_sigma", "intersecoes_zeta",
    "regras", "Controlador", "ProjetoInviavel", "projetar", "projetar_p", "projetar_pi",
    "projetar_pid", "erro_regime", "verificar", "projetar_e_relatar",
]
