# Métricas e estatísticas

Todo número publicado é calculado offline por `study rescore` (o scorer compartilhado
`src/routing_study/eval/scorers.py`) e renderizado por `study report` /
`scripts/analysis/study_report.py`. Esta página define cada métrica e cada teste. A unidade de
análise é o caso. As repetições têm a média calculada por caso antes de qualquer teste ou intervalo
de diferença.

## Tratamento de erros: intenção de tratar (ITT)

Uma linha é uma linha de erro quando uma destas condições vale:
- um estágio de roteamento falhou: nenhum passo consultado aceitou, e um passo lançou exceção (`usage.error`) ou
  devolveu uma resposta impossível de parsear (`usage.parse_fail`);
- o caso quebrou e não deixou registro de turno.

Linhas de erro contam como ERRADAS em todo score de corretude, e permanecem no denominador. Isso
vale em todo lugar: `tune_router.py` (avaliação e seleção), `simulate`, calibração da cascata,
`study report` e `study_report.py`. Uma falha nunca é pontuada como abstenção. Cada rodada
reporta sua taxa de erro como uma coluna separada.

A interseção dos ids de caso sem erro em todas as rodadas listadas é mostrada só como uma
tabela rotulada SENSITIVITY. Taxas de um desfecho ruim (`args_invented`) e `entity_grounded`
não se aplicam a uma linha de erro.

## Scores de roteamento (routing-only e e2e)

| score | definição |
|---|---|
| `skill_correct` | a skill escolhida está em `acceptable_skills`. |
| `tool_correct` | routing-only: a tool top-1 do roteador. e2e: a primeira chamada de negócio do executor, ou a tool de uma clarificação creditada. |
| `joint_correct` | skill e tool estão ambas corretas. Esta é a métrica primária de roteamento. |
| `joint_first_label` | joint contra apenas a PRIMEIRA skill e tool listadas. Análise de sensibilidade estrita para multi-rótulo (metodologia M4). |
| `abstain_correct` | acurácia de escalonamento ou abstenção. Abster-se é correto sse o gold permite; agir é correto sse o gold não espera abstenção. |

Regra de fora de escopo: se o gold é `__abstain__`, escalar como única ação conta como
abstenção. `__global__` + `escalate_to_human` é pontuado da mesma forma em todo consumidor.

## Scores e2e

`e2e_success`: a skill está correta, e uma destas condições vale:
- a primeira chamada de negócio usou uma tool aceitável, teve args válidos e foi concluída;
- uma chamada aceitável posterior completou com args válidos (e nenhuma chamada anterior completou uma ação).

Uma chamada é "concluída" quando completou, quando foi uma recusa NOT_ELIGIBLE no pedido a que o usuário
se referia, ou quando levou a uma clarificação "qual pedido?" correta.

O sucesso é dividido em três partes disjuntas que somam `e2e_success` (F6):

| parte | significado |
|---|---|
| `first_call_success` | a primeira chamada de negócio resolveu. |
| `clarification_credited` | uma pergunta de clarificação foi creditada. Ou nenhuma chamada foi feita e a resposta pediu o que o próximo passo precisava, ou a tool respondeu "qual pedido?" e a resposta ofereceu as opções. |
| `recovered_credited` | uma chamada aceitável posterior atingiu o objetivo depois de uma primeira tentativa errada ou falha. |

Outros scores e2e:

| score | definição |
|---|---|
| `e2e_strict` | `e2e_success`, e a chamada que decidiu o desfecho não inventou nenhum fato obrigatório. |
| `args_valid` | os args são válidos pelo schema, os args gold batem, e qualquer `order_id` que a chamada passou é um que o usuário escreveu (quando o usuário escreveu algum). A última checagem vale mesmo quando o gold omite `order_id` (F5). |
| `args_invented` | um argumento obrigatório de texto livre não é sustentado nem pelos args gold nem pelas palavras do usuário (pelo menos 50% de sobreposição de tokens; uma data ISO precisa de uma pista de data). |
| `entity_grounded` | todo id, valor e data na resposta final aparece na evidência: o perfil, os resultados das tools ou os turnos do usuário. Checa apenas entidades. Linhas pontuadas antes do F6 carregam o nome antigo `grounded`, que o report lê como alias. |

### Heurísticas de clarificação (F5)

Uma clarificação "qual pedido?" só é creditada quando todas estas condições valem:
- o usuário não nomeou nenhum pedido e o cliente tem pelo menos dois;
- a resposta contém uma frase interrogativa (um segmento terminado em `?`);
- a resposta oferece pelo menos dois ids de pedido;
- a resposta não afirma que uma ação já foi feita, como "pronto", "sucesso",
  "já cancelei" ou "foi cancelado".

Uma clarificação de campo ausente só é creditada quando ambas valem:
- o campo está ausente: os args gold não o cobrem, um valor de enum não está nas palavras
  do usuário, e a pista lexical do campo está ausente dos turnos do usuário (as pistas estão listadas abaixo);
- uma frase interrogativa da resposta nomeia o campo. A palavra-chave precisa iniciar uma palavra dentro de um
  segmento terminado em `?`, de modo que uma palavra-chave solta em outro lugar não conta.

Pistas que marcam um campo de texto livre como já fornecido (turnos do usuário sem acento, em casefold):

| campo | pista |
|---|---|
| `defect_description` | defeito, quebr-, parou, não liga/funciona/carrega, rasg-, manch-, trinc-, … |
| `reason` | porque, pois, motivo, por causa, desisti, arrepend-, não quero/gostei/serviu, errad-, … |
| `new_variant` | tamanho, número, cor, modelo, voltagem, PP/P/M/G/GG, um tamanho de 2 dígitos, um nome de cor |
| campos de endereço | rua/R., avenida/av, alameda, travessa, rodovia, CEP ou um código postal `00000-000` |
| `new_date` | uma pista de data: `dd/mm`, ISO, "dia N", dia da semana, mês, amanhã, hoje, … |

Skill nativa (E0): é a primeira skill que o agente carrega, ou a skill da primeira
tool vinculada a skill que ele chama. Uma tool global chamada antes disso não decide a skill; a
skill é `__global__` só quando nenhuma skill chegou a ser carregada.

Essas heurísticas são lexicais e deliberadamente conservadoras. A auditoria humana planejada de 60
transcrições e2e (metodologia M5) reporta a concordância scorer-vs-humano.

## Métricas secundárias (`eval/metrics.py`)

| métrica | definição |
|---|---|
| recall@1/2/3 | uma tool aceitável está no ranking top-k de tools do roteador (sua escolha primeiro, depois os candidatos gravados), com a skill correta. Golds fora de escopo aceitam `escalate_to_human`. Linhas de erro contam 0. |
| precisão / recall de abstenção | absteve-se = uma abstenção roteada, uma abstenção do host ou escalonamento como única ação. Precisão é a fração das abstenções cujo gold permite abster-se. Recall é a fração de abstenções entre os golds que a esperam (só abstenção ou escalonamento aceitáveis). Os roteadores LLM rodam com `allow_abstain: false`; regex e BM25 podem se abster. |
| risk-coverage, AURC, coverage@5% risk | linhas ordenadas por confiança = min(skill, tool) da decisão gravada. Linhas de erro têm confiança 0 e contam como erradas. Empates entram juntos. AURC é o risco médio sobre as coberturas 1/n..1. Coverage@5% é a maior cobertura cujo risco é ≤ 5%. |
| Brier, ECE | por nível, sobre as decisões tomadas (abstenções e linhas de erro de fora): confiança de skill vs `skill_correct`, e confiança de tool vs `tool_correct` nas linhas com skill correta. O ECE usa 10 bins adaptativos (de massa igual), e o report imprime as contagens dos bins. |
| baselines triviais | pontuados pelo scorer compartilhado nos casos das rodadas listadas. `always_escalate` = `__global__` + `escalate_to_human`. `majority` = a skill de primeiro rótulo mais comum no dev, depois a tool mais comum dentro dela. `uniform` = o score esperado de uma escolha uniformemente aleatória sobre as opções de cada estágio, com as globais oferecidas em todo estágio de tool, como no host. |

## Estatística (`eval/stats.py`)

- **IC marginal**: um bootstrap por cluster sobre os ids de caso. Todas as reps de um caso se movem juntas. Ele
  usa 10,000 reamostragens, seed 20260930, e intervalos de percentil.
- **IC de Δ pareado** (`paired_delta`): médias por caso sobre as reps, depois Δ = mean(run − reference)
  sobre os casos compartilhados. Os ids de caso são reamostrados 10k vezes com seed 20260930.
- **Testes no nível do caso**:
  - McNemar exato sobre as maiorias por caso (média > 0.5 é correto; empate conta como não
    correto);
  - um teste de permutação sign-flip da diferença média por caso, exato até 20 casos
    não nulos, senão Monte Carlo (10k, com seed).
- **Tipos de contraste**:

  | tipo | hipótese | teste |
  |---|---|---|
  | `two_sided` | Δ ≠ 0 | sign-flip, bicaudal |
  | `greater` | Δ > 0 | sign-flip, unicaudal |
  | `non_inferiority` (margem m) | Δ > −m | sign-flip sobre Δ + m, unicaudal. Veredito: limite inferior do IC pareado bicaudal de 95% (= unicaudal 97.5%) > −m |
  | `equivalence` (TOST, margem m) | \|Δ\| < m | p = máximo dos dois testes sign-flip unicaudais deslocados. Veredito por inclusão do IC pareado de 90%: dentro de ±m → equivalente; inteiramente fora → não equivalente; senão inconclusivo |

- **Holm**: step-down de Holm dentro de cada família nomeada (ex.: H1–H3, S1, S2). p ajustado < 0.05
  significa rejeitar.
- O McNemar no nível da rep (`stats.mcnemar` sobre pares (case, rep)) é anticonservador. Ele é mantido
  só para auditoria.

Os contrastes e as famílias são explícitos, nunca uma referência fixa no código:
- `study report --contrast run:reference[:family[:kind[:margin]]]`, ou o bloco `contrasts:` do
  manifest da rodada;
- `--reference X` = toda rodada vs X, bicaudal, numa única família.

## Colunas de custo

| coluna | definição |
|---|---|
| `$study/case` | o custo ORIGINAL de toda decisão consultada (independente de cache). |
| `$paid total` | o que foi cobrado pela rodada: roteamento consultado e shadow (`shadow_billed_usd`; igual à cobrança consultada fora do modo shadow), mais o executor. Cache hits são grátis. |
| `$list/case` | preço de tabela sem desconto de prompt cache. Exige `rescore --prices`. Usa os tokens gravados de cada passo, e os tokens do executor no e2e. Um modelo sem preço de tabela (pricing −1 no OpenRouter, ex.: o meta-roteador Jev) mostra `n/a`. |
