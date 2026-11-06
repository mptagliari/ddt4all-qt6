# Leitura direta do ABS/ESP — Fluence X38

## Resultado desta investigação

Foi implementado `ddt4all.diagnostics.abs_reader`, independente de Qt e das
rotinas de conexão da aplicação. Não houve abertura real da serial nem consultas
no veículo nesta missão. As alterações de ciclo de vida anteriores foram
preservadas e não reinvestigadas.

Os dados fornecidos ainda **não comprovam comunicação com o ABS**. Comprovam que
o adaptador reportou respostas no identificador 7E8 e que a captura DTC está
incompleta. O leitor agora permite um teste manual controlado sem aceitar isso
como DTCs do ABS. Não foi demonstrado que o hardware seja incapaz de acessar o ABS.

## Base realmente inspecionada

Fonte: arquivo local `ecu.zip`, definições abaixo e índice `db.json`.
Todos os quatro alvos estão associados ao projeto **x38** no índice. São
candidatos; o ano do carro e o nome do perfil não comprovam a ECU instalada.
A associação de um perfil EV ao projeto x38 não transforma um Fluence CVT em EV.

| Chave CLI | Definição no ZIP | Projetos no índice |
|---|---|---|
| `abs23` | `ABS___X95_Version_2.3.json` | x38, x95, x96 |
| `abs35` | `ABS___X95_Version_3.5_20101102T102139.json` | x38, x95, x95Ph2, x96 |
| `esc-ev` | `ESC_HSA_L38_EV_Version_1.0_20110406T151732.json` | x38 |
| `esp-hsa` | `ESP___X95_HSA_1.0.json` | x38, x95, x96 |

### Matriz de transporte e requests

Estes valores foram verificados nas quatro definições, não inferidos de um
scanner OBD genérico:

| Perfil | Protocolo | Tx / Rx CAN | Velocidade | Endereço funcional DDT | Identificação | Leitura DTC | Sessões declaradas |
|---|---|---|---|---|---|---|---|
| abs23 | CAN, IDs de 11 bits | 740 / 760 | 500 kbps | 01 | 2180 | 1902FF | 10C0, 10F0 |
| abs35 | CAN, IDs de 11 bits | 740 / 760 | 500 kbps | 01 | 2180 | 1902FF | 10C0, 10F0 |
| esc-ev | CAN, IDs de 11 bits | 740 / 760 | 500 kbps | 01 | 2180 | 1902FF | 10C0, 10F0 |
| esp-hsa | CAN, IDs de 11 bits | 740 / 760 | 500 kbps | 01 | 2180 | 1902FF | 10C0, 10F0 |

O endereço DDT `01` não é um byte extra no quadro CAN e não é o ID funcional
OBD `7DF`. As definições e o transporte existente usam ISO-TP com endereçamento
normal; o leitor desabilita endereçamento estendido com `ATCEA` e acrescenta PCI.

`DataRead.Identification.RenaultR2`: request `2180`, resposta positiva `6180`,
comprimento mínimo 26 bytes. Campos de identificação, com posições baseadas em 1:

| Campo | Primeiro byte | Comprimento / interpretação |
|---|---|---|
| DiagnosticIdentificationCode | 8 | 1 byte; valor decimal na assinatura |
| SupplierNumber.ITG | 9 | 3 bytes ASCII |
| SoftwareNumber | 17 | 2 bytes, hexadecimal big endian |
| EditionNumber | 19 | 2 bytes, hexadecimal big endian |

Todas as assinaturas examinadas têm fornecedor ASCII `368`. A seleção exige
coincidência exata dos quatro campos; não existe aproximação por fornecedor ou
somente número de software.

| Perfil | Código diagnóstico | Software → edições aceitas |
|---|---|---|
| abs23 | 8 | 5360 → 3006, 3007, 3010, 3012; 6160 → 4009, 4008, 4011, 4010 |
| abs35 | 8 | 7160 → 8013, 8012; 7260 → 9005, 9004; 8161 → 0014, 0013; 7361 → 2003, 2002; 8261 → 2008 |
| esc-ev | 5 | 7260 → 3010, 3014, 3024 |
| esp-hsa | 4 | 5260 → 2006, 2005, 2011, 2012; 5160 → 2004, 2005 |

Há outros requests de identificação, incluindo `21A0`, `21F0` e `21FE` nas
respectivas definições. O leitor não os envia: a identificação Renault `2180`
fornece os campos necessários. VIN `22F190` não identifica unicamente um ABS.

### Sessão: declarada não significa obrigatória

Os requests `2180` e `1902FF` têm `deny_sds: []`. Isso não prova que o módulo
instalado permita ambos na sessão atual. O DDT4All abre normalmente `10C0`;
a base também define `10F0` de fabricante. O leitor não usa `10F0`.

Por padrão, **nenhuma mudança de sessão é enviada**. Se a ECU negar um serviço,
o programa informa o NRC e para, sem tentar sessões automaticamente.

Existe uma opção explícita `--session 10C0 --ack-session-change`, para uma
reprodução separadamente autorizada após análise do resultado padrão. `10C0`
é mudança de estado diagnóstico, não uma leitura pura. A base a denomina
ExtendedDiagnostic; não prova ausência de efeitos colaterais em todo firmware.
Por isso a ferramenta exige primeiro identificação positiva por 2180 em 760,
envia 10C0 somente após isso, verifica resposta 50C0 e reidentifica antes de ler
DTCs. Se a identificação não funcionar na sessão atual, ela não envia 10C0 às
cegas. Não envia reset, sessão de fabricante, security access, tester-present ou
rotinas. Fechar a serial não restaura a sessão da ECU; não há comando automático
de restauração. A opção deve permanecer desligada no teste inicial.

### Formato de falhas

Nas quatro definições, `ReadDTCInformation.ReportDTC` envia `1902FF`, com mínimo
de 3 bytes e `shiftbytescount=4`. O payload completo esperado é:

```
59 02 MM [DD DD FT SS] ...
```

`MM` é a máscara de status suportados, não uma contagem de DTCs. Cada registro
possui identificador de dispositivo de 16 bits, tipo de falha de 8 bits e status
de 8 bits. O leitor usa `DTCDeviceIdentifier.lists`, `DTCFailureType.lists` e,
quando FT=00 e aplicável, `DTCDeviceAndFailureTypeOBD.lists` da definição confirmada.
Há 36/34/55/59 descrições de dispositivos, respectivamente. Descrições ausentes
ficam `null`; não são inventadas ou traduzidas para códigos DF/P sem uma tabela.

Os bits de status 0..7 correspondem a testFailed, testFailedThisOperationCycle,
pendingDTC, confirmedDTC, testNotCompletedSinceLastClear, testFailedSinceLastClear,
testNotCompletedThisOperationCycle e warningIndicatorRequested. São exibidos
status bruto, máscara e bits ativos suportados. Ver implementação primária de
[ReadDTCInformation no udsoncan](https://udsoncan.readthedocs.io/en/v1.18.1/_modules/udsoncan/services/ReadDTCInformation.html)
para a estrutura de registros de 3 bytes DTC + 1 status.

Somente `59 02 MM` completo, após identificação correta e origem 760, permite
concluir que nenhum registro foi retornado para a máscara FF. Isso não exclui
um problema mecânico/hidráulico, nem falhas com status não suportados.

## Respostas fornecidas: fato versus hipótese

### Fatos verificáveis sem hardware

- As três linhas 7E8 da consulta 22F190 contêm um First Frame com tamanho `0x014`
  e dois Consecutive Frames 21/22. Total: 6 + 7 + 7 = 20 bytes de payload.
  A estrutura fornecida é completa, mas a origem reportada é 7E8, não 760.
  Não é necessário reproduzir ou salvar o VIN para verificar essa estrutura.
- `7E8 11 07 59 02 FF 00 11 77` contém First Frame anunciando `0x107` = **263**
  bytes. Apenas 6 bytes do payload estão presentes. Nenhum registro completo
  pode ser atribuído ao ABS a partir dessa captura.
- `59 02` corresponde ao serviço consultado, mas não identifica o módulo.
- Os quatro perfis esperam resposta 760. Uma resposta reportada como 7E8 é
  rejeitada mesmo que o firmware tenha respondido OK a ATCRA760.

### Hipóteses ainda abertas

1. Filtro ATCRA ignorado ou comportamento incompatível do clone.
2. Header ATSH ignorado/substituído, enviando por outro endereço.
3. Protocolo/formatação redefinidos entre a configuração e a consulta.
4. Resposta anterior ainda na serial ou repetida por CR vazio.
5. Controle de fluxo ausente/incorreto ou buffers insuficientes, explicando
   receber somente FF. A captura também pode ter sido interrompida pelo programa.
6. ABS sem alimentação/sessão adequada, com falha de rede ou perfil incompatível.

Não é possível distinguir essas causas somente por OK e pelos quadros recebidos.
O ID de resposta não revela diretamente o ID realmente transmitido. Um analisador
CAN independente ou comparação controlada com interface conhecida permitiria
verificar a transmissão e separar causas. Isso não foi executado.

## Transporte existente e desenho do leitor

O DDT4All em `ELM.init_can`/`set_can_addr` configura SH, FC SH/SD/SM, CAF, CFC e
CRA. O caminho comum usa H0, CAF0 e monta PCI no software. Há reaplicação de CAF0
após trocar protocolo porque alguns clones alteram a formatação nessa operação.
O novo leitor não altera essas rotinas.

No leitor, a configuração vem antes das consultas: protocolo 6 fixo, H1, D0,
S1, CAF0, CEA desligado, respostas habilitadas, CFC1, Tx740 e filtro Rx760.
O protocolo reportado por ATDPN também deve ser 6. Cada comando AT deve retornar
somente OK; essa verificação detecta rejeição, não comprova execução física.

Segundo o [datasheet primário ELM327](https://elmelectronics.com/wp-content/uploads/2020/05/ELM327DSL.pdf),
CAF0 deixa o PCI a cargo do cliente; CFC1 controla separadamente o envio automático
de Flow Control. SH define transmissão; CRA ou CF/CM selecionam recepção. FC SH/SD/SM
controlam o header e conteúdo do FC, não o request diagnóstico. H1 permite
inspecionar o ID reportado. Um CR sozinho repete o comando anterior.

Configuração de FC: header 740, dados `30 00 0A`, modo 1. O BS zero permite o
restante do bloco e STmin 10 ms solicita espaçamento para reduzir pressão sobre
a UART a 38400 baud. `--stmin-ms` permite 0..127 ms. Isso é transporte ISO-TP,
não atuação hidráulica ou reprogramação. O clone e a ECU podem não respeitá-lo;
a montagem só é aceita se todos os quadros chegarem corretamente.

A filtragem da aplicação é independente: **qualquer ID estrangeiro invalida a
transação**, inclusive se quadros 760 também estiverem presentes. O parser não
remove headers para fazer uma resposta de outro módulo parecer válida. Não
assume que isso comprove bits físicos do barramento: depende da fidelidade do
header reportado pelo adaptador.

A ferramenta monta ISO-TP normal clássico: comprimento SF/FF, sequência CF,
wrap do contador, completude e padding final. Não implementa CAN FD, IDs de 29
bits ou endereçamento estendido. O FC fica no adaptador; se o clone não o executar,
o resultado é incompleto, não há envio manual especulativo para outros módulos.

O sincronismo espera um prompt inteiro por comando e elimina apenas o eco exato.
Não envia CR vazio, não reutiliza cache, não repete consultas em loop. Bytes
pendentes não vazios, respostas duplicadas e timeout invalidam o link. Response
Pending só é aceito se a resposta final vier antes do mesmo prompt; do contrário
o leitor para sem reenviar. Não há log de payloads/VIN.

## Uso manual

### Inspeção offline, sem serial

Na pasta do projeto:

```bash
./venv/bin/python -m ddt4all.diagnostics.abs_reader --list
QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest tests/unit/diagnostics -v
```

### Teste real proposto, não executado nesta missão

Fechar o DDT4All e qualquer outro programa que use a porta. Manter o veículo
parado com ignição na condição adequada. Não usar teste rodando o carro, dada
a anomalia de frenagem relatada. Executar manualmente somente quando autorizado:

```bash
./venv/bin/python -m ddt4all.diagnostics.abs_reader \
  --database ecu.zip --port /dev/ttyUSB0 --baudrate 38400 --timeout 3
```

Se a sessão Linux ainda não incorporou o grupo dialout já atribuído:

```bash
sg dialout -c './venv/bin/python -m ddt4all.diagnostics.abs_reader --timeout 3'
```

Não usar sudo. A ferramenta pede exclusividade Linux e fecha a porta em sucesso
e falha. Auto seleciona entre as quatro assinaturas exatas; `--profile abs35`
restringe candidatos e **não** força uma identificação. Não há varredura de ECUs,
comandos de escrita, clear-DTC, reset de ECU, codificação ou atuação.

Em reprodução separada, `--filter mask` testa CF760/CM7FF em vez de CRA760.
Não existe fallback automático entre métodos. Não mudar filtros, baudrate e
sessão simultaneamente: isso impediria atribuir uma diferença a uma causa.

### Resultado e próximo passo

Saída JSON; código de saída 0 para leitura confirmada (incluindo lista vazia),
2 para erro/resultado não conclusivo. Não confundir os estados:

| Estado | Significado |
|---|---|
| confirmed | Origem 760, assinatura exata e resposta DTC completa |
| wrong_origin | Outro CAN ID reportado; nada atribuído ao ABS |
| identity_mismatch | Assinatura diferente, desconhecida ou ambígua; sem consulta DTC |
| incomplete | Transporte ou registros incompletos; sem conclusão sobre falhas |
| no_communication | NO DATA/prompt sem quadros; não é ausência de falhas |
| negative_response | ECU retornou NRC, incluindo possível restrição de sessão |
| pending | NRC78 sem resposta final no prompt; sem repetição automática |
| timeout / desynchronized | Transação sem prompt ou bytes ambíguos; reiniciar o leitor |
| adapter_error / format_error / response_mismatch | Configuração, PCI ou resposta incompatível |

Em falha DTC após identificação válida, `identification_confirmed` preserva a
assinatura confirmada separadamente; `dtcs` fica null. Guardar esse JSON e a linha
de comando usada, sem pedir captura de VIN. Um NRC após identificação é evidência
diferente de ausência de comunicação e deve orientar a análise de sessão.

## Validação realizada

- **133 testes passaram**, sendo **60 novos** para o leitor e 73 preexistentes.
- Testes cobrem serial normal, eco, prompt fragmentado, filtros reportando OK mas
  deixando passar 7E8, origem errada após identificação, VIN anonimizado com a
  estrutura real, FF DTC de 263 bytes, ISO-TP completo/truncado/fora de sequência,
  wrap, DTC positivo/vazio, identidade errada/edição desconhecida, NRC, pending,
  timeout, bytes atrasados, formatação e bloqueio de serviços proibidos.
- CLI testada com porta falsa, parâmetros seriais e fechamento em falha. Nenhuma
  instância real de Serial foi criada nos testes.
- As quatro definições reais foram carregadas offline e cada primeira assinatura
  foi sintetizada e reconhecida corretamente contra todos os perfis.
- Importação verificada sem carregar Qt, USB ou serial; --list/--help não abrem
  dispositivo. `compileall` e `git diff --check` passaram.

```bash
QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest
```

## Limites e recomendação de hardware

Ainda faltam uma transação 2180 de 760 que coincida com a base e uma resposta
1902FF completa dessa mesma origem. Nenhum DTC real do ABS foi obtido nesta missão.
O leitor rejeita os dados anteriores de forma demonstrável; não prova uma falha
interna específica do ELM ou do ABS.

A string ELM327 v1.5 e o nome USB ELS27 não comprovam recursos implementados.
Não há justificativa suficiente para recomendar compra de outro adaptador agora.
Se a reprodução controlada mantiver IDs errados com ambos os filtros ou respostas
truncadas apesar do FC configurado, o próximo passo é comparação com interface
conhecida ou captura CAN para verificar Tx740/Rx760 e FC. Se apenas a interface
atual falhar nas mesmas condições, haverá fundamento para substituí-la. Se ambas
falharem, alimentação/rede/sessão/ECU continuam em aberto.

Não foram criados commits, PRs ou push. O programa não modifica o banco nem o
funcionamento existente do DDT4All.
