# Investigação física do interpretador AT — 27/10/2026

Porta verificada: Prolific PL2303, USB 067b:2303, `/dev/ttyUSB0`,
38400 baud. Abertura exclusiva, sem outro processo identificado na porta.
Não foram enviados requests de ECU, leitura DTC, mudanças de sessão, resets,
clear-DTC ou comandos de atuação. Somente comandos AT do próprio adaptador.

## Evidência

Com pausa de 150 ms entre comandos, ATI declarou ELM327 v1.5, ATDPN retornou 6
e ATDP informou ISO 15765-4 (CAN 11/500). ATH1, AT H1, AT H 1 e ath1 retornaram
OK. ATH0 e AT H0 também foram aceitos. ATE1 habilitou eco, confirmado com ATI e
H1; ATE0 voltou a desabilitá-lo. Bytes transmitidos e prompts foram conferidos.

A sequência exata ATI, ATE0, ATL0, ATSP6, AT H1 foi comparada:

| Intervalo após cada prompt | Resposta a AT H1 |
|---|---|
| 0 ms, primeira execução | ? |
| 20 ms | OK |
| 150 ms | OK |
| 0 ms, repetição | OK |

Assim, a rejeição foi reproduzida e é intermitente/dependente das condições de
envio. Não se sustenta a hipótese de H1 permanentemente ausente nem de simples
problema de espaços. A causa interna exata do firmware não foi comprovada.

Com intervalo de 50 ms, a configuração completa do leitor passou fisicamente:
ATE0, ATL0, ATSP6, AT H1, ATS1, ATD0, ATAL, ATR1, ATCEA, ATCAF0, ATCFC1,
ATFCSH740, ATFCSD30000A, ATFCSM1, ATSH740, ATSTFF, ATAT0 e ATCRA760 retornaram OK;
ATDPN retornou 6. Esse resultado comprova aceitação pelo interpretador nesta
execução, não implementação correta dos filtros ou dos frames CAN transmitidos.

## Alteração

`ELMLink` agora aguarda um intervalo mínimo de 50 ms após o último prompt antes
do próximo comando. O timeout da transação começa depois da escrita. A espera
é seguida pela checagem de bytes pendentes, preservando a detecção de respostas
atrasadas. Não há retry, descarte de erros ou CR vazio. O intervalo também se
aplica aos requests permitidos pelo leitor.

CLI: `--command-gap-ms` aceita valores finitos de 0 a 1000, padrão 50.
Esse intervalo é diferente de `--stmin-ms`, que controla o espaçamento solicitado
entre quadros ISO-TP, não entre comandos seriais.

Dois testes com relógio e serial simulados reproduzem o interpretador que
responde ? sem intervalo e OK com recuperação de pelo menos 20 ms. Os 63 testes
do leitor passaram. Nenhuma consulta ao veículo fez parte da validação física.

## Próxima reprodução manual

Com o DDT4All fechado:

```bash
./venv/bin/python -m ddt4all.diagnostics.abs_reader --command-gap-ms 50
```

Esse comando completo, diferentemente da sondagem física aqui realizada, tenta
identificação e leitura de DTCs. Não foi executado nesta investigação.
Somente um resultado válido em 760 com assinatura correspondente permite
atribuir DTCs ao ABS. A filtragem e a comunicação com o módulo continuam sem
validação física.

## Timeout na identificação: hipótese de preenchimento

Na reprodução manual posterior, a configuração terminou, mas o request
`0221800000000000` não recebeu byte algum nem prompt em 5 s. Isso não equivale
à resposta NO DATA e não determina se o request chegou fisicamente ao ABS.

Foi acrescentado `--padding adapter` para comparar a mesma consulta com `022180`,
sem zeros explícitos. O modo padrão continua `explicit`. Com CAF0, o ELM genuíno
mantém o PCI fornecido e completa o quadro com padding, segundo o datasheet.
Isso é uma comparação de compatibilidade do clone, não uma causa comprovada.
Os filtros, assinatura e validações de origem/completude permanecem obrigatórios.
Nenhuma consulta física foi realizada para validar essa hipótese.

```bash
./venv/bin/python -m ddt4all.diagnostics.abs_reader --timeout 5 --padding adapter
```

A repetição manual com `--padding adapter` também recebeu zero bytes em 5 s.
Essa comparação não demonstrou solução por preenchimento. Em seguida, foram
consultados somente ATI, ATCS, ATRV, ATDP e ATDPN: o adaptador respondeu ELM327
v1.5, T:00 R:00, 13.6 V, ISO 15765-4 (CAN 11/500) e 6. São valores informados pelo
firmware; os contadores não comprovam transmissão nem saúde da rede.

`--echo` habilita ATE1; o restante da configuração permanece igual. Um timeout
informa se o comando completo apareceu como eco nos bytes recebidos. Eco confirma
recepção serial pelo interpretador, não transmissão CAN ou resposta de ECU.
O teste seguinte é manual; não foi enviado request ao veículo nesta investigação:

```bash
./venv/bin/python -m ddt4all.diagnostics.abs_reader --timeout 5 --padding adapter --echo
```
