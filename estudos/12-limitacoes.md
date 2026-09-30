# 12 · Ameaças à validade e limitações

> Rascunho. Os itens com **[resultado]** recebem os números depois do run confirmatório.

## Validade interna

1. **Exposição do test-v1.** Um run preliminar rodou no split de teste original, e os erros
   dele foram lidos antes da reotimização dos roteadores. As regras de regex e os exemplos do
   catálogo foram reescritos depois disso, atacando confusões que apareciam naquela leitura.
   - **Mitigação:** geramos o **test-v2** depois de todo o ajuste, e só ele é confirmatório. O
     test-v1 aparece só como replicação e diagnóstico.
   - **Diagnóstico:** comparamos a acurácia nos casos do test-v1 cujos pares de confusão
     apareceram na leitura com a acurácia nos demais. **[resultado]**
2. **Viés de escolha no dev (*winner's curse*).** Variantes de prompt, parâmetros e limiares
   foram escolhidos em 151 casos. A diferença entre as variantes finalistas costuma ficar abaixo
   do erro-padrão.
   - **Mitigação:** estimativa aninhada, regra de um erro-padrão e o registro completo da busca
     (quantas variantes cada modelo testou).
   - O único ganho não enviesado de prompt é a diferença entre a trilha otimizada e a canônica
     medida no teste. **[resultado]**
3. **Esforço de ajuste desigual.** O regex recebeu regras escritas à mão, o BM25 uma grade de
   324 pontos e os LLMs uma busca de prompts. Reportamos uma coluna de esforço (configurações
   avaliadas, passadas no dev e horas humanas), que também alimenta a pergunta 5.
4. **Heurísticas de pontuação do e2e.** O crédito por clarificação, por recuperação e o
   diagnóstico de argumentos inventados são heurísticas.
   - **Mitigação:** o e2e aparece decomposto, e a pontuação automática é conferida por uma
     auditoria de transcrições. **[resultado: concordância]**

## Validade de constructo

- **Rótulos múltiplos** em casos ambíguos são generosos: há em média ~2,4 tools aceitáveis por
  caso ambíguo no dev. Reportamos também a acurácia estrita (só o primeiro rótulo) e a acurácia
  nos casos de rótulo único.
- **"Abstenção"** inclui escalar para um humano. A métrica se chama "abstenção ou escalonamento"
  e vem acompanhada de precisão e revocação.
- **"Grounded"** verifica só entidades (IDs, valores, datas), por isso se chama *entity-grounded*.
- **Rótulos gerados por modelo:** a semente e os casos sintéticos vieram de modelos. A auditoria
  também é automática, feita por dois modelos de famílias diferentes do Claude, com κ reportado.
  Uma revisão humana das divergências fica disponível, mas é opcional. **[resultado: κ, taxa de
  correção]**

## Justiça entre estratégias

- **Jev** foi avaliado como classificador via prompt no `jev-router` do OpenRouter, que é um
  meta-roteador. Isso não mede a API tipada nativa, que é o diferencial declarado pelo
  fornecedor.
- **Temperatura:** o Sonnet 5 no Bedrock não aceita `temperature`, então amostra com o padrão
  do provedor. Haiku e Qwen rodam com temperatura 0. Reportamos a taxa de mudança de decisão
  entre repetições.
- **Cache de prompt assimétrico:** o prefixo do Haiku fica abaixo do mínimo de cache do Bedrock
  (4.096 tokens), e o do Sonnet é lido do cache. Por isso publicamos o custo em três regimes.
- **Local × API:** a latência local depende do hardware (Apple M5 Pro, 48 GB, Ollama 0.24,
  concorrência 1) e não é diretamente comparável com a latência de API em `sa-east-1`. As duas
  ficam em colunas separadas.
- **Ajuste com o catálogo fixo:** todas as estratégias usam o mesmo texto do MCP. Estratégias
  que dependem de exemplos (BM25, embeddings, classificador) são sensíveis à qualidade desses
  exemplos.

## Validade externa

- **Catálogo pequeno.** São 18 tools e 3 skills (9 opções por estágio). Nesse tamanho, o agente
  nativo (E0) tende a ser forte, e técnicas pensadas para catálogos grandes (busca de tools,
  carregamento adiado) não se aplicam. As conclusões **não** se estendem automaticamente a
  catálogos com centenas de tools.
- **Um domínio e um idioma:** pós-venda de e-commerce em português brasileiro, com dados
  sintéticos desenhados para expor fraquezas, e não para imitar tráfego real. As acurácias
  absolutas não são estimativas de produção.
- **Modelos datados.** Slugs, preços e comportamento são de setembro de 2026. O `jev-router` é
  um produto recém-lançado e não determinístico, e pode mudar.
- **Poder estatístico.** Com ~350 casos, a menor diferença detectável é de ~4,5–6 pontos. As
  análises por categoria (adversarial com n≈17) são só descritivas.

## Fora do escopo (trabalho futuro)

- Catálogo escalado (dezenas ou centenas de tools) e descoberta progressiva via MCP.
- Fine-tune completo de um encoder multilíngue como roteador.
- Exemplos dinâmicos e autoconsistência nos LLMs.
- Benchmarks públicos (CLINC150, MASSIVE, BFCL) para situar os números sintéticos.
- API nativa tipada do Jev.
- Confirmação pelo servidor antes de ações destrutivas (MRTR) no e2e.
