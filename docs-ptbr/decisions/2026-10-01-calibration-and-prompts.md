# Decisão: variantes de prompt e mapas de calibração para os roteadores LLM/Jev (insumo do pré-registro)

Data: 2026-10-01. Responsável: líder do estudo. Status: decidido antes de qualquer chamada ao test_v2.

1. **Variantes de prompt.** Aplicar `config/prompt_selection.yaml` conforme selecionado pela regra
   one-SE pré-declarada: Sonnet 5, Haiku 4.5 e Jev usam P0 nas duas trilhas (canônica = tuned). As
   alternativas de argmax `raw_best` (Sonnet/Haiku P0+P4, Jev P0+P6c) NÃO são aplicadas; elas são
   reportadas como sensibilidade apenas no dev. Jev P0+P6c é reportado, adicionalmente, como variante de custo numa
   rodada routing-only exploratória (rotulada como exploratória, fora de H1-H3).
2. **Mapas de calibração.** Um mapa é aplicado a um (modelo, trilha, estágio) somente quando seu ECE
   com cross-fitting no dev é menor que o ECE bruto (`ece_cal < ece_raw` em prompt_selection.yaml).
   Caso contrário, usa-se a confiança bruta. Mesma regra para toda estratégia. Os limiares da cascata são então
   calibrados numa rodada shadow no dev com essas configs finais (D5).
3. **Qwen3-8B (E6b)** segue o mesmo procedimento de seleção no dev antes do congelamento; seu resultado é
   anexado a prompt_selection.yaml com select_prompts.py, e a regra canônica é recalculada
   entre os quatro roteadores do tipo LLM.
