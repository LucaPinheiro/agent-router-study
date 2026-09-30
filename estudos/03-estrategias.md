# 03 · Estratégias de roteamento e estado da arte

> Rascunho. As configurações finais de cada estratégia são congeladas no pré-registro. As
> referências vêm da auditoria de estado da arte (`.omc/reviews/sota-final.md`, 2026-09-30).
> "Não verificado" indica afirmação que não conseguimos confirmar em fonte pública.

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

## 3. Busca semântica (embeddings)

- **Modelo:** `qwen3-embedding-8b` (Q8, local via Ollama), com instrução na consulta e sem
  instrução nos documentos. No MTEB-BR (2026) ele é o **2º melhor modelo aberto em português
  brasileiro** (0,670). Não verificamos quanto a quantização Q8 custa em qualidade.
- **Agregação:** máximo por exemplo, centroide ou votação entre os k vizinhos mais próximos,
  escolhida por validação cruzada. Confiança por softmax com temperatura, calibrada.
- **Ablação:** 1–2 embedders alternativos (menores ou comuns como padrão) como pontos de custo e
  latência.

## 4. Fusão (híbrido)

- **RRF** (*reciprocal rank fusion*) com 2 ranqueadores e 3 a 9 opções fica praticamente fixo:
  qualquer valor de k dá o mesmo ranking. Registramos isso como resultado nulo esperado.
- **Estado da arte:** combinação convexa das confianças calibradas (peso por validação cruzada)
  e um empilhador logístico pequeno sobre as confianças de regex, BM25 e embedding, mais a
  concordância entre eles.

## 5. Classificador treinado

A família que um revisor sênior espera ao lado de regex, BM25 e embeddings. Todos são treinados
só nos exemplos do catálogo (e expansões geradas a partir dele), com seleção por validação
cruzada no dev:

- TF-IDF com regressão logística ("regras aprendidas");
- sonda linear sobre os vetores congelados do embedder;
- SetFit ou equivalente.

É também o análogo aberto mais próximo de um modelo de decisão como o Jev: milissegundos, custo
de API zero, confiança calibrada. O fine-tune completo de um encoder multilíngue (por exemplo,
mmBERT) fica como trabalho futuro.

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
- **Confiança:** autorrelatada e depois calibrada. A literatura recente mostra que a confiança
  verbalizada é mal calibrada e recomenda logprobs ou calibração explícita. No Qwen local
  testamos também a confiança por logprob.
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
  modelo atendido.

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
  - limiares por validação cruzada, com calibração e escolha em partes diferentes dos dados;
  - fronteira de Pareto completa;
  - ponto de operação com risco controlado;
  - como referências no gráfico: o roteador oráculo, a abstenção aleatória com a mesma
    cobertura e o "sempre LLM".

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
