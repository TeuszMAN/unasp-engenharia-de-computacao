# Teoria: projeto pelo Lugar Geométrico das Raízes

Guia de estudo que acompanha o código. Cada seção aponta a função que faz a conta, para dar para ler a teoria e conferir no programa.

Notação: malha com realimentação unitária, planta `G(s)`, controlador `C(s)`. O produto `C(s)G(s)` é escrito como `K·L(s)`, em que `K` é o ganho que varre o LGR e `L(s) = N(s)/D(s)` guarda os polos e zeros.

```
 r ──►(+)──► C(s) ──► G(s) ──┬──► y
       ▲ -                   │
       └─────────────────────┘
```

## 1. O que é o LGR

A malha fechada vale `T(s) = K·L(s) / (1 + K·L(s))`, então os polos de malha fechada são as raízes de

```
1 + K·L(s) = 0    ⇔    D(s) + K·N(s) = 0
```

O LGR é o desenho dessas raízes no plano s quando `K` vai de 0 a ∞. Ele mostra, de uma vez, todos os comportamentos que se obtém mudando só o ganho.

Reescrevendo `K·L(s) = -1`, que é um número real negativo, saem as duas condições que definem o lugar:

| Condição | Fórmula | Para que serve | No código |
|---|---|---|---|
| Ângulo | `∠L(s) = ±180°·(2k+1)` | Diz **se** um ponto s pertence ao LGR | `angulo`, `deficiencia_angular` |
| Módulo | `K = 1/|L(s)|` | Dá **o ganho** que leva o polo até esse ponto | `ganho_no_ponto` |

O ângulo de `L(s)` é a soma dos ângulos dos vetores que vão de cada zero até s, menos a soma dos ângulos dos vetores que vão de cada polo até s. O módulo é o produto das distâncias aos zeros dividido pelo produto das distâncias aos polos.

Todo o projeto pelo LGR se resume a isto: **os polos e zeros do controlador mudam a forma do lugar (condição de ângulo) e o ganho escolhe o ponto sobre ele (condição de módulo).**

## 2. Regras de esboço

Saem das duas condições e permitem desenhar o LGR à mão. A função `regras(L)` calcula todas e `python exemplos.py 1` mostra o resultado para `1/(s(s+1)(s+2))`.

1. **Número de ramos**: igual ao número de polos `n`. Cada ramo começa num polo (K = 0) e termina num zero (K → ∞). Sobram `n - m` ramos que vão para o infinito.
2. **Simetria**: o LGR é simétrico em relação ao eixo real, porque os coeficientes são reais e as raízes complexas aparecem em pares conjugados.
3. **Eixo real**: um trecho do eixo real pertence ao LGR se tiver à direita um número ímpar de polos e zeros reais. Polos e zeros complexos não contam, porque os ângulos do par conjugado se anulam.
4. **Assíntotas**: os ramos que vão ao infinito seguem retas que partem de `σa = (Σpolos − Σzeros)/(n − m)` com ângulos `(2k+1)·180°/(n − m)`.
5. **Pontos de separação e de chegada**: onde dois ramos se encontram no eixo real e saem dele (ou entram). Com `K = −D(s)/N(s)`, são as raízes de `dK/ds = 0`, ou seja, `D'N − DN' = 0`, que dão `K > 0`.
6. **Cruzamento do eixo jω**: o ganho em que a malha fica no limite de estabilidade. Pelo critério de Routh-Hurwitz, ou substituindo `s = jω` em `D + KN = 0` e igualando parte real e imaginária a zero. O código faz a segunda forma.
7. **Ângulos de partida e chegada**: em um polo complexo `p`, aplicando a condição de ângulo a um ponto muito próximo dele: `θ = 180° + Σ∠(p − zeros) − Σ∠(p − outros polos)`. Para a chegada a um zero complexo, troca-se o papel de polos e zeros.

## 3. Dos requisitos ao polo desejado

O projeto supõe que a malha fechada terá um par de **polos dominantes** `s = −σ ± jωd`, e que o resto é rápido ou está cancelado. Para esse par, valem as fórmulas da resposta de 2ª ordem (`lgr/especificacoes.py`):

| Requisito | Fórmula | Lugar no plano s |
|---|---|---|
| Sobressinal `Mp` | `ζ = −ln(Mp/100) / √(π² + ln²(Mp/100))` | Semirreta a `θ = arccos ζ` do semieixo real negativo |
| Tempo de acomodação (2%) | `ts ≈ 4/σ` → `σ = 4/ts` | Reta vertical `Re(s) = −σ` |
| Tempo de pico | `tp = π/ωd` → `ωd = π/tp` | Reta horizontal `Im(s) = ωd` |
| Frequência natural | `ωn = |s|` | Círculo de raio `ωn` |

Dois requisitos fixam o **polo desejado** `sd` (`Requisitos.polo`). Um requisito só fixa uma reta, o que basta para o controlador P.

Lembretes que o programa verifica na simulação:

- `ts = 4/σ` já é uma aproximação; com polos extras ou zeros perto, ela piora.
- Um terceiro polo é desprezível se a parte real dele for umas 5 vezes a de `sd`.
- Um polo quase em cima de um zero (quase cancelamento) tem resíduo pequeno: afeta pouco a forma da resposta, mas se for lento deixa uma "cauda" lenta.

## 4. Controlador P

`C(s) = K`. O LGR de `K·G(s)` é o próprio LGR da planta, e o ganho só escolhe o ponto. Há **um grau de liberdade**: dá para atender ζ ou ts, mas, em geral, não os dois.

Procedimento (`projetar_p`):

1. Traçar a reta do requisito (ζ constante ou σ constante).
2. Achar onde o LGR cruza a reta, isto é, os pontos da reta com `∠G(s) = −180°`.
3. `K = 1/|G(s)|` nesse ponto.

O programa faz o passo 2 de forma exata: em `s = origem + t·direção`, a condição "`D(s)/N(s)` é real" vira um polinômio real em `t` (`intersecoes_reta`).

Se o LGR não cruza a reta, nenhum ganho atende o requisito, e é preciso mudar a forma do lugar com polos e zeros.

O erro em regime depende do tipo do sistema: para planta tipo 0, o P deixa erro ao degrau `1/(1 + Kp)`, com `Kp = K·G(0)`.

## 5. Controlador PI

`C(s) = Kp + Ki/s = K (s + z)/s`, com `Kp = K` e `Ki = K·z`.

O polo na origem aumenta o tipo do sistema em 1 e **zera o erro ao degrau**. O preço é um ângulo negativo a mais (`−∠s`) no ponto dominante, que o zero precisa compensar. Há dois jeitos clássicos de posicionar o zero:

### 5.1 Compensação integral ideal (`--metodo-pi ideal`)

Não se mexe no transitório:

1. Projeta-se o P para o ζ desejado.
2. Põe-se o zero bem perto da origem (o padrão é 10% de `|Re|` do polo dominante).
3. Vistos de longe, do polo dominante, o polo na origem e o zero quase coincidem. Os ângulos dos dois praticamente se anulam e o LGR quase não se move ali.
4. Recalcula-se o cruzamento com a reta de ζ e o ganho.

Surge um polo lento perto do zero, quase cancelado por ele. É esse polo que faz a resposta "subir devagar" até o valor final depois do transitório: o erro vai a zero, mas leva tempo (exemplo 3).

### 5.2 Pela condição de ângulo (`--metodo-pi angulo`)

Com dois requisitos, o polo de malha fechada vai exatamente para `sd`:

1. Calcula-se `∠G(sd)` e soma-se a contribuição do integrador, `−∠sd`.
2. O que falta para −180° é o ângulo que o zero precisa dar: `φz = −180° − ∠G(sd) + ∠sd`.
3. Um zero real em `−z` vê `sd = −σ + jωd` com ângulo `atan2(ωd, z − σ)`. Daí `z = σ + ωd/tan φz`.
4. `K` pela condição de módulo em `sd`.

O PI só funciona se `0° < φz < 180°` e `z > 0`. Como o integrador sempre tira ângulo, o PI sozinho raramente acelera a resposta: quando o ângulo necessário não cabe num zero do semiplano esquerdo, o programa avisa que o projeto é inviável e diz por quê (exemplo 5).

## 6. Controlador PID

`C(s) = Kp + Ki/s + Kd·s = K (s + zi)(s + zd)/s`, com

```
Kd = K,   Kp = K (zi + zd),   Ki = K·zi·zd
```

É um PI vezes um PD. O PD (`s + zd`) soma ângulo positivo e puxa o LGR para a esquerda, o que acelera a resposta. O PI (`(s + zi)/s`) zera o erro em regime.

Procedimento (`projetar_pid`):

1. Polo desejado `sd` a partir de dois requisitos.
2. Zero integral `zi` perto da origem (padrão: 10% de `|Re(sd)|`, ou `--zero-pi`), para que o par integrador e zero quase não mude o ângulo em `sd`.
3. Ângulo que falta: `φd = −180° − ∠G(sd) + ∠sd − ∠(sd + zi)`.
4. `zd = σ + ωd/tan φd`.
5. `K` pela condição de módulo em `sd`.

No livro do Nise o PD é projetado antes e o zero do PI é acrescentado depois, o que desloca um pouco o polo. Aqui o zero do PI entra já no cálculo do ângulo, e o polo cai exatamente em `sd`. A diferença é pequena (no exemplo 5, `zd = 50,0` aqui e `55,9` no livro, com o zero do PI em `−0,81` contra `−0,5`).

## 7. Verificação

O projeto pelo LGR é feito com a aproximação de 2ª ordem, então todo projeto precisa ser simulado. O programa (`lgr/analise.py`) mostra:

- os polos de malha fechada e se algum deles atrapalha a dominância;
- o previsto pela 2ª ordem contra o simulado: sobressinal, ts, tp e tempo de subida;
- as constantes de erro `Kp`, `Kv`, `Ka` e os erros ao degrau e à rampa.

Se o simulado ficar longe do previsto, as saídas mais comuns são aproximar o zero do PI da origem, pedir requisitos menos agressivos ou mudar o tipo de controlador.

## 8. Roteiro sugerido

1. `python exemplos.py 1`: refaça as regras de esboço à mão e confira com a saída.
2. `python exemplos.py 2`: ajuste de ganho. Mude ζ e veja o ponto andar sobre o mesmo lugar.
3. `python exemplos.py 3`: PI ideal. Teste `--zero-pi` maiores no `projetar.py` e veja o transitório começar a mudar.
4. `python exemplos.py 4`: PI pela condição de ângulo. Diminua ts até o projeto ficar inviável e entenda o motivo.
5. `python exemplos.py 5`: PID. Compare com o P e confira o tp simulado.
6. Use `projetar.py` com as plantas das listas de exercícios e confira as contas feitas à mão.

## Referências

- NISE, N. S. *Engenharia de Sistemas de Controle*. LTC. Capítulos 8 (LGR) e 9 (projeto pelo LGR).
- OGATA, K. *Engenharia de Controle Moderno*. Pearson. Capítulos 6 (análise e projeto pelo LGR) e 8 (controladores PID).
