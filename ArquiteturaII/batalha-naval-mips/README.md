# Batalha Naval em MIPS32

Projeto da disciplina de Arquitetura de Computadores (Engenharia de Computação, UNASP).

## Descrição

Implementação do jogo Batalha Naval em assembly MIPS32, executada no simulador MARS. O jogador enfrenta o computador em turnos: a cada jogada, digita uma coordenada (por exemplo, `B7`) e o programa informa se o tiro acertou água ou um navio. Não há laço de jogo em tempo real; o programa avança somente quando recebe uma entrada.

Os tabuleiros são desenhados no Bitmap Display do MARS. Os navios do computador são posicionados aleatoriamente com a syscall 42, respeitando os limites do tabuleiro e sem sobreposição.

O jogo serve de pretexto para exercitar, em um programa completo, conceitos que costumam aparecer de forma isolada nas listas de exercícios: acesso a matrizes em memória, operações bit a bit, entrada e saída, chamadas de procedimento e uso da pilha.

## Objetivos de aprendizado

- Calcular endereços de elementos de matrizes armazenadas em memória linear.
- Usar operações lógicas e deslocamentos para manipular conjuntos de bits.
- Converter texto ASCII em valores numéricos e tratar entradas inválidas.
- Escrever em um dispositivo de saída mapeado em memória (Bitmap Display).
- Estruturar o programa em procedimentos que obedecem à convenção de chamada do MIPS.
- Medir o custo de diferentes representações de dados pelo número de instruções executadas.

## Conceitos de arquitetura abordados

**Matrizes em memória.** O tabuleiro de 10 x 10 casas é armazenado em ordem de linha. O endereço da casa (linha, coluna) é `base + (linha * 10 + coluna) * tamanho`, em que `tamanho` é 1 para a matriz de bytes.

**Operações bit a bit (bitboard).** Na segunda representação, cada linha do tabuleiro ocupa uma palavra de 32 bits, usando os 10 bits menos significativos (bit `c` corresponde à coluna `c`). Um tabuleiro inteiro cabe em 10 palavras. Com `sllv`, `and` e `or` é possível testar um tiro, registrar um acerto e verificar se um navio afundou comparando a máscara do navio com a máscara de tiros (`(navio AND tiros) == navio`).

**Entrada e saída.** A coordenada é lida como texto (syscall 8) e convertida em índices: `linha = letra - 'A'` e `coluna = digito - '0'`. Opcionalmente, a leitura pode usar o teclado mapeado em memória do MARS (registrador de controle em `0xFFFF0000` e de dados em `0xFFFF0004`), por varredura do bit de pronto.

**Bitmap Display.** Cada casa do tabuleiro corresponde a uma unidade do display. Escrever uma cor (palavra `0x00RRGGBB`) no endereço certo do buffer de vídeo pinta a casa.

**Números aleatórios.** A syscall 42 devolve um inteiro em `[0, limite)`. É usada para sortear linha, coluna e orientação de cada navio do computador, com validação de limites e de sobreposição antes de gravar.

**Procedimentos e pilha.** Cada rotina do jogo é um procedimento chamado com `jal`. Procedimentos que chamam outros, ou que usam registradores `$s`, salvam `$ra` e os `$s` na pilha (`$sp`) e os restauram antes de `jr $ra`.

## Escopo por níveis

1. **Mínimo.** Jogador contra computador. Navios do computador posicionados aleatoriamente. O jogador atira digitando coordenadas. Tabuleiro exibido no Bitmap Display (água, acerto, erro). Fim de jogo quando todos os navios forem afundados.
2. **Diferencial.** O tabuleiro implementado de duas formas, matriz de bytes e bitboard, com as mesmas operações (posicionar, atirar, verificar vitória). O número de instruções executadas em cada versão é medido com a ferramenta Instruction Counter do MARS, para uma mesma sequência de jogadas, e os resultados são registrados em tabela no relatório.
3. **Opcional.** O computador também atira no tabuleiro do jogador, com estratégia simples: tiros aleatórios até acertar e, depois de um acerto, tiros nas casas vizinhas.

## Regras do jogo adotadas

- Tabuleiro de 10 x 10. Linhas identificadas pelas letras `A` a `J` e colunas pelos dígitos `0` a `9`. A coordenada `B7` indica linha 1, coluna 7.
- Frota sugerida: um navio de 5 casas, um de 4, dois de 3 e um de 2, posicionados na horizontal ou na vertical, sem sobreposição. O grupo pode alterar a frota, desde que registre a decisão aqui.
- Tiro repetido ou coordenada inválida não consome a vez; o programa pede nova entrada.

## Como executar no MARS

Requisitos: Java instalado e o MARS 4.5 (`Mars4_5.jar`).

1. Abra o MARS e carregue `src/main.asm` (File > Open).
2. Abra o Bitmap Display em Tools > Bitmap Display e ajuste:

   | Parâmetro | Valor |
   |---|---|
   | Unit Width in Pixels | 16 |
   | Unit Height in Pixels | 16 |
   | Display Width in Pixels | 512 |
   | Display Height in Pixels | 256 |
   | Base address for display | 0x10040000 (heap) |

   Com essa configuração, o display tem 32 x 16 unidades e o buffer de vídeo ocupa 2048 bytes a partir de `0x10040000`. O pixel (x, y) fica em `0x10040000 + (y * 32 + x) * 4`. O programa não deve usar `sbrk` (syscall 9), pois a região do heap está reservada ao display.

3. Clique em "Connect to MIPS" no Bitmap Display.
4. Para medir instruções, abra também Tools > Instruction Counter e clique em "Connect to MIPS".
5. Monte o programa (Run > Assemble, ou F3).
6. Execute (Run > Go, ou F5) e digite as coordenadas no painel Run I/O.

Disposição prevista no display (em unidades):

| Elemento | Posição |
|---|---|
| Tabuleiro do computador (alvo do jogador) | colunas 2 a 11, linhas 3 a 12 |
| Tabuleiro do jogador | colunas 20 a 29, linhas 3 a 12 |

Cores previstas (formato `0x00RRGGBB`):

| Estado da casa | Cor | Valor |
|---|---|---|
| Fundo | preto | `0x00000000` |
| Água não atingida | azul | `0x000066CC` |
| Erro (tiro na água) | branco | `0x00FFFFFF` |
| Acerto | vermelho | `0x00FF0000` |
| Navio do jogador | cinza | `0x00808080` |

## Estrutura de pastas

```
batalha-naval-mips/
├── README.md            descrição do projeto e instruções
├── CONTRIBUTING.md      fluxo de trabalho do grupo
├── src/
│   └── main.asm         programa principal (esqueleto)
├── docs/
│   ├── relatorio.md     relatório do trabalho (esqueleto)
│   └── referencias.md   referências bibliográficas
└── tests/
    └── README.md        casos de teste manuais
```

## Convenções do grupo

- Código e comentários em português, sem acentos nos rótulos e nomes de variáveis.
- Rótulos de procedimentos em minúsculas com sublinhado (`ler_coordenada`). Rótulos internos recebem o nome do procedimento como prefixo (`ler_coordenada_invalida`).
- Todo procedimento tem um comentário de cabeçalho com: finalidade, argumentos (`$a0` a `$a3`), retorno (`$v0`, `$v1`) e registradores alterados.
- Argumentos em `$a0` a `$a3`, retorno em `$v0` e `$v1`. Registradores `$s0` a `$s7` e `$ra` são preservados por quem é chamado; `$t0` a `$t9` podem ser alterados livremente.
- Constantes (tamanho do tabuleiro, cores, endereços) definidas com `.eqv` no início do arquivo, sem números soltos no código.
- Mudanças nas regras do jogo ou na configuração do display são registradas neste README.

## Divisão de tarefas

| Tarefa | Responsável | Status |
|---|---|---|
| | | |
| | | |
| | | |
| | | |
| | | |
