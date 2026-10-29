# Como contribuir

## Fluxo de trabalho

1. Escolha uma tarefa na tabela "Divisão de tarefas" do README e coloque seu nome como responsável.
2. Crie uma branch a partir da `main` com o nome da tarefa, por exemplo `ler-coordenada` ou `bitboard-atirar`.
3. Faça commits pequenos, cada um com uma mudança coerente.
4. Antes de integrar, monte e execute o programa no MARS para confirmar que não houve erro de montagem nem regressão.
5. Integre na `main` (merge ou pull request) e atualize o status da tarefa no README.

## Mensagens de commit

- Em português, no imperativo, com uma primeira linha curta que diga o que mudou: `Implementa conversao de coordenada ASCII`.
- Se necessário, deixe uma linha em branco e explique o motivo da mudança.

## O que não commitar

- Arquivos de configuração local de editor ou do sistema (`.vscode/`, `.idea/`, `Thumbs.db`, `.DS_Store`).
- O executável do MARS (`.jar`).
- Arquivos temporários ou de saída.
