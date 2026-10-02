# Calibração dos limiares da cascata

`projeto.md`: *"Limiares são por estratégia e por estágio, e vêm da calibração no split de
desenvolvimento, nunca de chute."* Esta é a ferramenta que os produz.

```bash
uv run study rescore results/<shadow-dev-run>.jsonl --out results/rescored
uv run python scripts/analysis/calibrate_cascades.py results/rescored/<shadow-dev-run>.jsonl \
    [--config config/experiments/e9_regex_jev_llm.yaml ...] [--budget 0.0008] \
    [--folds 5] [--seed 0] [--grid 0.50 0.99 0.01] [--min-support 5] \
    [--out-dir results/calibration]
```

- **Entrada:** uma rodada shadow (`--routing-mode shadow`) *reavaliada* (rescored) no split **dev**; o
  script recusa qualquer outro split. Uma linha shadow guarda a decisão de toda estratégia nos dois
  estágios, então qualquer cascata pode ser reexecutada offline para qualquer limiar. Nenhuma chamada de API é feita.
- **Cascatas:** E7, E8 e E9 por padrão; `--config` substitui a lista (qualquer cascata cujas
  estratégias foram gravadas na rodada shadow). Ajustado: o `min_confidence` de todo passo, exceto
  o último, por estágio (o último passo mantém sua regra configurada, normalmente "aceitar qualquer escolha").
- **Saída** (`--out-dir`): `calibration.md` (relatório), `thresholds.yaml` (um snippet `routing:`
  por experimento e método, **não** aplicado em `config/experiments`: copie o
  bloco escolhido à mão) e `pareto.csv` (fronteira acurácia-vs-custo por experimento, para gráficos).

## Métodos

**(a) Orçamento / Pareto.** Toda combinação do grid (padrão 0.50..0.99, passo 0.01, por
passo ajustado: 50 combinações para E7/E8, 50² × 50 = 125 000 para E9) é reexecutada. Escolha: máxima
acurácia joint sujeita a custo de roteamento/caso ≤ `--budget` (sem orçamento: máxima acurácia joint); empates vão
para o menor custo, depois para os limiares mais altos. O relatório e o `pareto.csv` também listam a
fronteira não dominada inteira (custo ↑, acurácia ↑), de modo que um orçamento diferente pode ser lido nela.

**(b) Regra de precisão** (fácil de explicar). Passo a passo, na ordem do pipeline: aceite um passo
barato no **menor** limiar do grid em que sua precisão nos casos que ele aceita (entre os
casos que chegam a ele) seja ≥ a precisão geral do próximo passo (sobre todo caso de ajuste em que o próximo
passo escolheu), com pelo menos `--min-support` casos aceitos. Se nenhum limiar se qualificar, o passo
é marcado como `never`: ele deve ser removido (o snippet YAML o deixa de fora). A precisão é
`skill_can_be_correct` para o estágio de skill e a corretude joint dada a skill gravada para
o estágio de tool (decisões de tool só são pontuáveis quando a skill gravada poderia estar certa).

## Mantendo a escolha honesta

- **Mesmo scorer, mesmo simulador.** A pontuação usa as funções compartilhadas de `eval/scorers.py`
  (`routing_scores`, `skill_can_be_correct`, `routing_failure`), com as regras de
  `eval/simulate.simulate_rows`: linhas de erro excluídas, uma skill errada pontua 0, um estágio de tool
  que não pode ser reexecutado (a skill simulada difere da gravada) conta 0 (limite
  inferior, `unavail`), custo sobre as linhas cobertas. O grid é avaliado por um caminho vetorizado
  (`eval/calibrate.py`) por velocidade, e **todo ponto reportado** (configurado, (a), (b), todo
  ponto de Pareto e as combinações aleatórias de `--checks`) é rodado de novo por `simulate_rows` e precisa bater
  exatamente, senão o script falha.
- **Denominador fixo.** Uma linha que é linha de erro em *algum* ponto do grid (um passo consultado
  falhou e nada foi aceito) é descartada para aquele experimento. Caso contrário, um limiar poderia
  parecer melhor ao escalar casos difíceis para um passo que falhou neles (linhas de erro saem do
  denominador da acurácia). O relatório informa quantas linhas foram descartadas.
- **Validação cruzada.** k-fold estratificado (por categoria, sobre ids de caso, seed fixa; o mesmo
  algoritmo de `scripts/analysis/tune_router.py`, portanto os mesmos folds para o mesmo conjunto de casos). Cada método é reajustado em k-1 folds e
  pontuado no fold retido; as linhas retidas agregadas dão a acurácia joint e o custo com ICs de 95%
  por cluster bootstrap (`eval/stats.bootstrap_mean`, reamostrando ids de caso). As escolhas por fold
  mostram quão estável é a escolha. As colunas "dev" são ajustadas e pontuadas nas mesmas linhas
  (otimistas); cite a coluna de CV.

## Ressalvas

- Os limiares vivem na escala de confiança **gravada** na rodada shadow. O relatório conta
  quantas decisões de regex/BM25 carregam `usage.raw_confidence`; `0` significa que a rodada é anterior aos
  mapas de calibração e seus limiares estão na escala bruta: rode a rodada shadow de novo com as
  configs atuais antes de aplicá-los.
- O estágio de tool foi gravado para a skill que o próprio pipeline da rodada shadow escolheu. Limiares
  que transformam uma skill gravada errada em uma certa não conseguem reexecutar o estágio de tool e são
  contados como 0, o que enviesa levemente a busca em direção aos limiares gravados; `joint cov.`
  (tabela de Pareto) exclui essas linhas.
- Com ~150 casos dev os ICs são largos (±7 pp): diferenças entre métodos dentro dos ICs não são
  evidência. A regra (b) é especialmente instável por fold com suporte pequeno.

## Exemplo (rodada shadow dev de 2026-09-29, `docs/results/shadow-dev-routing-only.jsonl`)

Reavaliada em `/tmp` e calibrada com os padrões (sem orçamento). E9 (regex → jev → llm para
a skill, jev → llm para a tool); 135 de 151 linhas estão livres de erro em todo ponto do grid:

| método | limiares de skill | limiares de tool | joint dev % | joint retido no CV % [IC 95%] | US$/1k de roteamento no CV [IC 95%] |
|---|---|---|---|---|---|
| configurado (YAML) | regex=0.90, jev=0.75 | jev=0.70 | 78.5 | = dev (sem ajuste) | 0.597 [0.428, 0.788] |
| (a) joint máximo | regex=0.89, jev=0.60 | jev=0.99 | 80.7 | 79.3 [71.9, 85.9] | 1.576 [1.280, 1.897] |
| (b) regra de precisão | regex=0.71, jev=0.92 | jev=0.74 | 78.5 | 77.8 [70.4, 84.4] | 1.023 [0.798, 1.268] |

A fronteira de Pareto do E9 mostra o trade-off: o limiar do jev no estágio de tool compra +2.2 pp de joint
(78.5 → 80.7) por ~4× o custo de roteamento (0.39 → 1.63 US$/1k), tudo dentro do IC. Esta rodada
é anterior aos mapas de calibração de regex/BM25 (0/405 decisões carregam `raw_confidence`), então estes
números ilustram a ferramenta; rode de novo a rodada shadow dev antes de aplicar qualquer limiar.
