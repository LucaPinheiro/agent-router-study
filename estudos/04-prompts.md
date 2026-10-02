# 04 · Engenharia de prompt: trilhas A e B

> Fontes: [docs/prompt-apex.md](../docs/prompt-apex.md) (busca no dev),
> `config/prompt_selection.yaml` (seleção congelada) e
> [secondary.md, S1](../docs/results/final/secondary.md) (registro no teste).
> Tudo que é de dev foi medido em 151 casos, validação cruzada de 5 partes estratificada.

## 1. Desenho

Cada roteador do tipo LLM (Sonnet 5 = E5, Haiku 4.5 = E6, Qwen3-8B local = E6b, Jev = E4) teria
dois prompts:

- **Trilha A, canônica:** o mesmo prompt para os quatro, escolhido pela média entre modelos. Com o
  prompt fixo, a diferença entre roteadores é do modelo.
- **Trilha B, otimizada:** o melhor prompt de cada modelo. A diferença B − A mede quanto a
  engenharia de prompt rende por modelo (hipótese S1).

A variante é uma composição de modificadores sobre a base P0:

| Token | O que muda |
|---|---|
| P0 | Base: regras → opções (id, descrição, até 5 exemplos do catálogo) → skill carregada / histórico / mensagem; saída estruturada com `enum`; confiança = "probabilidade de a escolha estar certa" |
| P1 | Guia de desambiguação com as cláusulas "NÃO USE PARA" do catálogo |
| P2k1/P2k2 | k exemplos do catálogo por opção como demonstrações resolvidas |
| P3 | Regras de escopo explícitas (o que é `__global__`, preferir a tool específica) |
| P4 | Campo `rationale` (≤ 15 palavras) antes da decisão |
| P5 | Instruções em pt-BR |
| P6 / P6c | Estágio de tool: ranking top-3 com escore / ranking compacto só de ids |

Os exemplos vêm só do catálogo MCP, nunca do dataset.

## 2. Procedimento de seleção (dev)

1. Rodada 1 num subconjunto estratificado de 60 casos com P0 e cada modificador isolado.
2. Poda: uma variante sai quando a diferença pareada para a líder do subconjunto fica abaixo de
   −1 erro-padrão. P0 nunca sai.
3. Rodada 2 combina os sobreviventes (só o Jev teve mais de um).
4. Sobreviventes e candidatos canônicos (P0, P0+P4, P0+P5) vão ao dev completo.
5. **Regra de um erro-padrão:** entre as variantes a até 1 EP da melhor, fica a com menos
   modificadores, depois a mais barata, depois P0. A estimativa honesta é por CV aninhada.

## 3. Resultado: P0 em todas as trilhas, para todos os modelos

| Modelo | Canônica | Otimizada | CV aninhada (otimizada), dev | Escolhas nas 5 partes externas | Melhor bruto no dev (não escolhido) |
|---|---|---|---|---|---|
| Sonnet 5 | P0 | P0 | 77,5 ± 9,8 | P0 ×5 | P0+P4 80,2 (5 ganhos / 1 perda vs P0) |
| Haiku 4.5 | P0 | P0 | 81,5 ± 3,8 | P0+P4, P0 ×4 | P0+P4 83,5 (3/2) |
| Jev | P0 | P0 | 78,2 ± 9,4 | P0 ×5 | P0+P5 80,9 (8/4); P0+P6c 80,9 (6/2) |
| Qwen3-8B | P0 | P0 | 81,5 ± 3,2 | P0 ×4, P0+P4 | P0+P4 84,2 (8/5) |

Fonte: [secondary.md S1](../docs/results/final/secondary.md) e [prompt-apex.md](../docs/prompt-apex.md).
Na canônica, a média da CV entre os quatro modelos foi P0 80,2 e P0+P4 81,2; a regra manteve P0.

**Consequência para o teste (S1, confirmatório e degenerado por construção):** como a trilha B é
idêntica byte a byte à A, Δ ≡ 0 e **nenhum teste S1 foi rodado no test-v2**. O achado é que *o
procedimento pré-declarado não encontrou ajuste de prompt que valesse a pena* em 151 casos. O
maior ganho bruto no dev foi +2,7 pp (Sonnet com P4), vindo de 6 casos discordantes (5 a 1;
teste de sinal exato p ≈ 0,22). Isso não é evidência de ganho.

**Resultado nulo, dito claramente:** engenharia de prompt não rendeu ganho mensurável neste
estudo. Isso vale para este tamanho de dev e este espaço de variantes. Diferenças de 1–3 pp
podem existir e não seriam detectáveis aqui.

## 4. Variante de custo do Jev: P0+P6c (exploratório)

O ranking compacto (P6c) corta tokens de saída. No dev, o Jev com P0+P6c custou US$ 0,60/1k
contra 0,93 com P0, com p50 de 4,0 s contra 5,0 s
([prompt-apex.md](../docs/prompt-apex.md)). No test-v2 ele rodou uma vez como variante
exploratória (`x-e4-jev-p6c-routing-r1`, 1 repetição):

| Run | Conjunta % [IC 95%] | US$/1k observado [IC 95%] | Erros |
|---|---|---|---|
| E4 Jev P0 (3 reps) | 84,7 [81,0; 88,2] | 0,818 [0,739; 0,900] | 2 (0,2%) |
| E4 Jev P0+P6c (1 rep) **[X]** | 84,2 [80,2; 88,0] | 0,611 [0,533; 0,692] | 1 (0,3%) |

Fonte: [estimation.md §A](../docs/results/final/estimation.md). Os ICs se sobrepõem quase por
inteiro. Não há teste pareado pré-registrado para esse contraste. A leitura possível é que o
P6c custa ~25% menos sem queda visível de acurácia, como hipótese para um próximo estudo.

## 5. Economia de contexto do prompt

Medido no dev, por chamada de roteamento ([prompt-apex.md](../docs/prompt-apex.md), tabela
"Output format and context economics"):

| Modelo | Variante | Tokens de prompt (fixo / variável) | Cache leitura / escrita | Tokens de saída | US$/1k |
|---|---|---|---|---|---|
| Sonnet 5 | P0 | 2229 (2119 / 111) | 1746 / 209 | 157 | 5,97 |
| Haiku 4.5 | P0 | 1917 (1826 / 92) | 0 / 0 | 148 | 5,32 |
| Jev | P0 | 1157 (1107 / 50) | 784 / 31 | 225 | 0,93 |
| Jev | P0+P6c | 1043 (997 / 46) | 676 / 40 | 118 | 0,60 |

- **Os tokens de saída dominam a conta:** o P6c corta pela metade a saída do Jev.
- **Cache assimétrico:** o prefixo do Sonnet é lido do cache (~78–82% do prompt), o do Haiku
  nunca chega ao mínimo de 4.096 tokens do Bedrock. Esse é o motivo de o Haiku não sair mais
  barato que o Sonnet no teste (capítulo [08](08-economia.md)).
- P4 (justificativa) custa +7–8% e +9–14% de p50 pelos seus +0,7 a +2,7 pp no dev.

## 6. Ameaças específicas

- O dev tem 151 casos: os EPs das variantes ficaram entre 2,2 e 6,2 pp. A seleção é instável.
- Haiku P6 sobreviveu ao subconjunto mas não foi ao dev completo (orçamento Bedrock esgotado).
- Qwen P0+P5 travou 6,5 h por um deadlock do cliente e foi abortado; já estava podado na rodada 1.
- Jev não é determinístico: cada variante no dev é uma amostra.
