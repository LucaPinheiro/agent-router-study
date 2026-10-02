# 03 · Estratégias de roteamento e estado da arte

> Versão final. As configurações estão congeladas na tag `prereg-v1`; o esforço de ajuste de
> cada uma está em [tuning-effort.md](../docs/tuning-effort.md). As referências vêm da auditoria
> de estado da arte (2026-09-30). "Não verificado" indica afirmação que não conseguimos confirmar
> em fonte pública. Cada seção termina com o resultado no test-v2 (capítulo [05](05-resultados-roteamento.md)).

Todas as estratégias implementam o mesmo contrato: recebem a mensagem, o histórico curto e a
lista de opções, e devolvem uma escolha, uma confiança e os candidatos ranqueados. Vale para os
dois estágios, skill e tool. As opções vêm sempre do catálogo MCP, então nenhuma estratégia tem
informação privilegiada.

## 1. Regras (regex)

- **Como funciona:** padrões com peso por opção, organizados por vocabulário de intenção
  (verbos, substantivos, variantes coloquiais), com supressores para os pares confundíveis. A
  confiança é heurística e depois calibrada.
- **Estado da arte:** regras funcionam como a primeira camada, de alta precisão, antes de algo
  aprendido (o padrão de Rasa e do *semantic-router*). O valor delas é a **cobertura com
  precisão fixa**, não a acurácia geral. Por isso a reportamos também como classificador
  seletivo (curva risco × cobertura).
- **Cuidado metodológico:** as regras foram escritas lendo os erros do split de dev. O número
  no dev é otimista, e só o test-v2 mede de verdade. Reportamos a distância entre dev e teste.
- **No test-v2:** 52,7% de acurácia conjunta, contra 84,8% no dev (−32,1 pp [−37,5; −26,9]).
  Nenhum ponto de operação com risco ≤ 5%. O superajuste ao dev é o maior efeito do estudo.

## 2. Busca léxica (BM25)

- **Como funciona:** BM25L (a variante da biblioteca `rank_bm25`) sobre descrição e exemplos de
  cada opção, com histórico curto na consulta. A confiança é a margem entre os dois primeiros,
  calibrada.
- **Achado:** com um documento por opção (3 a 9 documentos), o IDF do Okapi zera termos
  frequentes como "devolver". A variante BM25L contorna isso. Stemming em português **piorou**
  (junta "pedido"/"pedir", "troca"/"trocar"), e reportamos isso como resultado negativo.
- **Estado da arte:** indexar cada exemplo como um documento, pontuando a opção pelo melhor
  exemplo ou pela soma dos k melhores. Isso elimina o problema do IDF. Também são padrão a
  expansão de documentos com paráfrases geradas a partir do catálogo (o ganho principal no
  ToolRet) e n-gramas de caracteres para português informal. Entram como variantes avaliadas no
  dev.
- **Configuração final** (946 configurações avaliadas no dev): índice por exemplo do catálogo
  (soma dos 4 melhores), n-gramas de caracteres 3–5, expansão determinística com os exemplos do
  catálogo. Com esse índice o IDF do Okapi deixa de degenerar.
- **No test-v2:** 49,0% conjunta (dev 55,7%; gap −6,7 pp), o pior roteador.

## 3. Busca semântica (embeddings)

- **Modelo:** `qwen3-embedding-8b` (Q8, local via Ollama), com instrução na consulta e sem
  instrução nos documentos. No MTEB-BR (2026) ele é o **2º melhor modelo aberto em português
  brasileiro** (0,670). Não verificamos quanto a quantização Q8 custa em qualidade.
- **Agregação:** máximo por exemplo, centroide ou votação entre os k vizinhos mais próximos,
  escolhida por validação cruzada. Confiança por softmax com temperatura, calibrada.
- **Configuração final:** similaridade com o centroide, instrução de tarefa na consulta, as
  duas últimas mensagens do histórico na consulta.
- **Ablação:** `qwen3-embedding:0.6b` e `bge-m3`.
- **No test-v2:** 73,6% conjunta (as duas ablações: 64,5%); p50 de 427 ms. Supera o regex em
  +20,9 pp [15,2; 26,6] (S4).

## 4. Fusão (híbrido)

- **RRF** (*reciprocal rank fusion*) com 2 ranqueadores e 3 a 9 opções fica praticamente fixo:
  qualquer valor de k dá o mesmo ranking. Registramos isso como resultado nulo esperado.
- **Estado da arte:** combinação convexa das confianças calibradas (peso por validação cruzada)
  e um empilhador logístico pequeno sobre as confianças de regex, BM25 e embedding, mais a
  concordância entre eles.
- **Configuração final (E11):** combinação convexa de regex e classificador com α = 0,5. O BM25
  não somou nada à fusão, e o empilhador logístico ficou abaixo da combinação convexa no dev.
  Todo o ganho da fusão no dev (+6 pp aninhado) vinha do regex.
- **No test-v2:** 72,8% conjunta, abaixo do classificador sozinho (74,8%): o ganho do regex no dev
  não se transferiu.

## 5. Classificador treinado

A família que um revisor sênior espera ao lado de regex, BM25 e embeddings. Todos são treinados
só nos exemplos do catálogo (e expansões geradas a partir dele), com seleção por validação
cruzada no dev:

- TF-IDF com regressão logística ("regras aprendidas");
- sonda linear sobre os vetores congelados do embedder;
- SetFit ou equivalente.

É também o análogo aberto mais próximo de um modelo de decisão como o Jev: custo de API zero e
confiança calibrada. O fine-tune completo de um encoder multilíngue (por exemplo, mmBERT) fica
como trabalho futuro.

- **Resultado no dev:** TF-IDF com regressão logística foi fraco (39% aninhado). A sonda linear
  sobre os vetores do `qwen3-embedding-8b` empatou com o roteador de embedding e virou o E10.
  SetFit não foi avaliado.
- **No test-v2:** 74,8% conjunta, o melhor roteador local abaixo de 2 s de p95 (p50 419 ms).

## 6. LLMs como roteadores

- **Modelos:**
  - Claude Sonnet 5 e Claude Haiku 4.5, via Bedrock;
  - Qwen3-8B local, via Ollama, com o modo de raciocínio desligado.

  O raciocínio interno é desligado explicitamente em todos, porque com saída estruturada o
  Sonnet 5 raciocina por padrão, e isso muda custo, latência e o orçamento de saída.
- **Saída:** estruturada, restrita às opções válidas por enum, com a confiança pedida como
  probabilidade de acerto.
- **Variantes de prompt P0–P6** (capítulo [04](04-prompts.md)): guia de desambiguação,
  exemplos do catálogo, regras de escopo, justificativa curta, idioma e formato da saída.
- **Confiança:** autorrelatada e depois calibrada por mapa isotônico do dev quando isso reduziu o
  ECE na validação cruzada. A literatura recente mostra que a confiança verbalizada é mal
  calibrada e recomenda logprobs ou calibração explícita.
- **Prompt:** P0 para os quatro modelos, nas duas trilhas (capítulo [04](04-prompts.md)).
- **No test-v2:** Sonnet 84,1%, Haiku 84,5%, Qwen3-8B local 79,9%. A equivalência com o Sonnet
  (±3 pp) não foi estabelecida para nenhum (S2). O Qwen3-32B (E5b) foi retirado antes do
  pré-registro, por latência.
- **Trabalho futuro:** exemplos dinâmicos (os k exemplos do catálogo mais parecidos com a
  mensagem) e autoconsistência. A seleção dinâmica quebra o prefixo estático em cache, e esse
  é justamente o trade-off de contexto que o estudo discute.

## 7. Jev (TypeSafe)

- **O que é:** um modelo de decisão, com a mensagem "System One" do fornecedor, que recebe
  estado e perguntas tipadas e devolve probabilidades por opção. O fornecedor declara até 200×
  mais velocidade e 400× menos custo que LLMs comparáveis. Não há benchmark independente
  publicado (não verificado).
- **O que medimos de fato:** `typesafe/jev-router` via OpenRouter. Nos nossos testes, a chamada
  foi atendida por outros modelos (por exemplo, `openai/gpt-6-luna`), ou seja, ele se comporta
  como um meta-roteador. Nós o usamos como classificador via prompt, sem a pergunta tipada
  nativa. Em todo o estudo ele aparece como **"jev-router via OpenRouter"**, e as conclusões
  valem para esse produto, não para a API nativa do Jev.
- **Reportamos também:** a mistura de modelos que efetivamente atenderam, e a acurácia por
  modelo atendido. No E4, `deepseek/deepseek-v4.1-flash` atendeu 50,9% das chamadas de skill e
  `openai/gpt-6-luna` 41,8% (capítulo [09](09-erros.md)).
- **No test-v2:** 84,7% conjunta [81,0; 88,2] a US$ 0,82 por mil casos, p95 de 6,9 s. Tem a
  maior acurácia pontual e custa ~6× menos que o Sonnet; a equivalência com o Sonnet passa pela
  regra do IC, mas não depois de Holm.

## 8. Cascatas

- **Como funcionam:** o primeiro passo com confiança calibrada acima do seu limiar decide
  (E7: regex → Jev; E8: regex → Sonnet; E9: regex → Jev → Sonnet).
- **Relação com a literatura:**
  - FrugalGPT é o mais próximo: uma cascata entre estratégias, com um avaliador decidindo
    quando passar ao próximo nível;
  - RouteLLM e AutoMix escolhem entre LLMs;
  - trabalhos de 2025–26 usam calibração isotônica e *conformal risk control* para escolher
    limiares com garantia de erro.
- **O que aplicamos:**
  - limiares por *cross-fitting* em 5 partes, com a regra "máxima acurácia com custo ≤ 0,5 ×
    Sonnet" declarada antes;
  - fronteira de Pareto completa como sensibilidade;
  - como referências: o roteador oráculo, o adiamento aleatório com as mesmas taxas e o
    "sempre LLM".
- **No test-v2:** E9 81,8% e E7 79,9%; a não inferioridade ao Sonnet não foi demonstrada (H1, H2).
  E12 (híbrido → Jev → Sonnet, exploratório) chegou a 83,0% (capítulo [06](06-cascatas.md)).

## 9. Por que não descoberta progressiva de tools no MCP

A ferramenta de busca de tools da Anthropic (`tool_search` com BM25 ou regex, e carregamento
adiado) mostra grandes ganhos com **50 ou mais tools**. Com menos de ~10, o próprio fornecedor
diz que o benefício é pequeno. Nosso catálogo tem 9 tools por estágio, então está no regime
errado para essa técnica. Ela fica como extensão natural do estudo para catálogos grandes.

## Fontes

- MTEB-BR: https://arxiv.org/html/2607.04581v2
- semantic-router: https://docs.aurelio.ai/semantic-router/user-guide/components/routers
- Jev: https://www.width.ai/post/what-is-jev-ai-typesafe · https://www.langchain.com/blog/building-a-harness-with-jev
- Cascatas e calibração:
  - https://arxiv.org/pdf/2605.18796
  - https://arxiv.org/pdf/2604.23577
  - https://arxiv.org/pdf/2607.25018
  - https://arxiv.org/html/2601.07206v1
- Confiança verbalizada: https://arxiv.org/pdf/2412.14737 · https://arxiv.org/pdf/2410.06707
- Exemplos dinâmicos: https://arxiv.org/pdf/2409.01466
- ToolRet: https://aclanthology.org/2025.findings-acl.1258/
- Tool search: https://www.anthropic.com/engineering/advanced-tool-use
- SetFit: https://arxiv.org/pdf/2209.11055 · mmBERT: https://huggingface.co/jhu-clsp/mmBERT-base
- Classificação seletiva: https://proceedings.neurips.cc/paper_files/paper/2024/file/047c84ec50bd8ea29349b996fc64af4b-Paper-Conference.pdf
