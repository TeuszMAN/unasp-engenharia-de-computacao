###############################################################################
# Batalha Naval em MIPS32
# Projeto de Arquitetura de Computadores, Engenharia de Computacao (UNASP)
#
# Simulador: MARS 4.5
# Bitmap Display: unidade 16 x 16, area 512 x 256, base 0x10040000 (heap)
#
# Estado atual: esqueleto. Os procedimentos abaixo ainda nao foram
# implementados; os comentarios descrevem o que cada um deve fazer.
###############################################################################

        .data

        .text
        .globl main

main:
        # Fluxo previsto:
        #   1. posicionar_navios (computador)
        #   2. desenhar_tabuleiro
        #   3. repetir: ler_coordenada, atirar, desenhar_tabuleiro,
        #      verificar_vitoria, ate o fim do jogo
        #   4. encerrar com a syscall 10

###############################################################################
# posicionar_navios
# Posiciona aleatoriamente a frota do computador. Para cada navio, sorteia
# linha, coluna e orientacao com a syscall 42 e chama validar_posicao; repete
# o sorteio ate encontrar uma posicao valida e entao grava o navio.
###############################################################################
posicionar_navios:

###############################################################################
# validar_posicao
# Verifica se um navio com dada linha, coluna, orientacao e tamanho cabe no
# tabuleiro e nao se sobrepoe a outro navio. Retorna 1 se valida, 0 se nao.
###############################################################################
validar_posicao:

###############################################################################
# ler_coordenada
# Le uma coordenada digitada pelo jogador (ex.: "B7") e converte os
# caracteres ASCII em linha (letra - 'A') e coluna (digito - '0').
# Retorna indicacao de erro se a entrada for invalida.
###############################################################################
ler_coordenada:

###############################################################################
# atirar
# Registra um tiro na posicao (linha, coluna) do tabuleiro alvo. Retorna se
# foi agua, acerto ou tiro repetido.
###############################################################################
atirar:

###############################################################################
# desenhar_tabuleiro
# Percorre as 100 casas de um tabuleiro e pinta cada uma no Bitmap Display
# com a cor correspondente ao seu estado (agua, erro, acerto, navio).
###############################################################################
desenhar_tabuleiro:

###############################################################################
# verificar_vitoria
# Verifica se todos os navios de um tabuleiro foram afundados.
# Retorna 1 se o jogo terminou, 0 caso contrario.
###############################################################################
verificar_vitoria:
