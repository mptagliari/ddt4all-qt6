# Investigação do ciclo de vida serial

## Resultado e alcance

Foram confirmados bugs de gerenciamento da conexão, reproduzidos com mocks.
O log fornecido não contém a pilha de chamada de `ELM reset...`; portanto não
permite atribuir o fechamento daquela execução a um desses caminhos com certeza.
Não foi feita comunicação com o adaptador ou veículo nesta investigação.

A abertura da serial e a resposta OBD genérica fornecidas pelo usuário são
independentes da identificação e comunicação com o ABS. Não confirmam o ABS,
a implementação de ATCRA, nem a validade do resultado "sem DTC".

## Ciclo de vida anterior

1. `main.main` construía ELM e atribuía a `options.elm` antes da janela principal.
2. `MainWidget` carregava `EcuScanner`/`EcuDatabase`. Esse carregamento não possui
   a conexão e não chama seu fechamento.
3. `changeECU`/`set_param_file` criavam `ParamWidget`. `initXML` chamava `initELM`,
   que chamava `EcuFile.connect_to_hardware`: configuração CAN/ISO e sessão,
   usando o mesmo `options.elm`, sem reconstruir a serial.
4. As consultas e timers da página consultavam o global. O sniffer também usa
   o global em sua thread. Não foi encontrada uma cópia permanente do objeto ELM
   no scanner ou parser de ECU. Plugins podem obter/atribuir esse global pelo
   adaptador de macros; plugins externos não foram executados nem auditados.
5. `sendElm` chamava `reconnect_elm` quando `connectionStat()` era falso.
6. `MainWidget.closeEvent` fazia `del options.elm`. Isso removia uma referência;
   outra referência Python podia manter o objeto vivo. O teste de referência
   fraca confirma que a exclusão do global não implica destruição imediata.

A seleção normal de ECU não chama `del options.elm`. O fechamento no encerramento
é esperado; o fechamento seguido de uso da mesma conexão não é.

## Defeitos comprovados

- `elm_checker` construía o teste em `options.elm` e chamava `__del__()`
  explicitamente ao terminar. O global continuava referenciando o objeto fechado.
  Não há destruição Python nessa chamada direta: seu corpo apenas executa.
  `Port.close()` deixava `hdr=None`, mas `ELM.connectionStatus` continuava verdadeiro.
  Uma nova chamada ao destrutor tentava escrever ATZ nesse Port sem handler,
  reproduzindo a mensagem informada. Exceções também escapavam da limpeza do teste.
- `reconnect_elm` construía o novo ELM antes de liberar o anterior, pois Python
  avalia o lado direito da atribuição primeiro. A porta Linux é aberta com
  `exclusive=True`, logo o transporte antigo podia impedir a nova abertura.
  Mesmo sem exclusividade, o destrutor antigo podia enviar ATZ depois da abertura
  nova. A reprodução verifica a ordem de fechar/abrir com uma referência antiga
  mantida viva; não depende de contagem imediata de referências.
- Quando a reconexão retornava falso, `sendElm` prosseguia e consultava o objeto
  antigo/inválido. O indicador podia permanecer incoerente com o transporte.
- Uma exceção no construtor podia reter a serial até a coleta do objeto parcial.
- Uma exceção em `Port.close` anulava `hdr`, mas podia manter
  `connectionStatus=True`. A limpeza de buffers antes de fechar também podia
  impedir que o fechamento fosse tentado.
- `Port.write` segurava Lock e, em um caminho de erro, chamava `close`, que tentava
  adquirir o mesmo Lock. Um teste com thread e timeout comprova a correção da
  possibilidade de deadlock usando RLock.
- Fechar uma página não parava os dois QTimers sem parent. Um teste Qt real,
  com inicialização de ECU simulada, confirmou timers ainda ativos após close.
  Isso pode gerar consultas de páginas antigas, mas não foi provado como origem
  do fechamento observado. O sniffer não foi executado; não se afirma segurança
  geral de acesso concorrente à conexão.

## Correções

- `close_elm` desanexa o global e fecha explicitamente; `replace_elm` fecha antes
  de construir. Inicialização principal e reconexões usam esses caminhos.
- `ELM.close` é idempotente, invalida o objeto e libera transporte e arquivos.
  Construtores parciais também são limpos. O destrutor é apenas uma salvaguarda
  sem enviar ATZ; tentativas de baudrate usam close explícito.
- O teste do adaptador possui uma conexão local, limpa em finally, sem publicar
  o objeto temporário no global.
- `connectionStat` verifica transporte, handler e estado de abertura serial.
  `send_raw` rejeita transporte fechado e detecta falha de escrita.
- A UI cancela consultas se a recuperação falhar, verifica a reinicialização
  antes de mostrar conectado e informa falhas de transporte. Ler DTC numa
  conexão fechada é cancelado, sem exibir "sem DTC" por esse caminho.
- Os timers pertencem à página e param em close; ambos também param ao sair da
  janela principal. O fechamento da conexão ocorre após parar o sniffer.

Não foram alterados os comandos de ABS, decodificação de DTC, filtros CAN,
reconhecimento USB nem as rotinas específicas dos demais adaptadores.

## ELS27 e aviso USB

`UsbCan.init` pode rotular um conversor PL2303/FTDI/CH340/CP210x como ELS27 quando
não reconhece o texto do descritor. `get_string_descriptor` captura a falha de
permissão e devolve um rótulo genérico. Isso explica por que o rótulo não comprova
firmware ELS27. A leitura do descritor usa libusb e é independente da abertura da
serial por PySerial. O log confirma que a abertura serial continuou normalmente.

O tipo de conexão é selecionado separadamente na UI. Escolher ELS27 muda o fluxo:
há pré-teste com ATZ no checker e comandos adicionais ATSP6/ATSH81 no construtor.
O texto do log fornecido indica configurações STD_USB. Não foi encontrada prova
de que o simples rótulo USB tenha escolhido o ramo ELS27 naquela execução.
Esses ramos foram preservados; não se presume que configurem fisicamente pinos
nem que o clone implemente seus comandos corretamente.

## Validação

Python 3.13, PyQt5, pytest 7.4.4; testes sem hardware, com Qt offscreen:

```bash
QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest
```

Resultado: **73 passed** (57 existentes e 16 regressões novas).
Quatro regressões iniciais foram também executadas numa cópia temporária do
código HEAD anterior às alterações: todas falharam, expondo global fechado,
limpeza tardia, estado incorreto após falha de close e consulta após recuperação
malsucedida. O teste de timers também falhou antes da correção e passou depois.
`compileall` e `git diff --check` passaram.

Para repetir somente os cenários de conexão:

```bash
QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest tests/unit/core/elm/test_lifecycle.py -v
```

A carga de 5.673 definições é simulada no teste de ownership; não se afirma que
o teste carregue a base real ou execute cliques completos na janela principal.
A página Qt real é usada no teste de timers; demais fluxos de UI são exercitados
pelos métodos com dependências simuladas.

## Rastrear uma nova execução manual

Não executar testes reais automaticamente. Uma reprodução real deve ser
combinada separadamente e restrita às consultas não destrutivas autorizadas.
Não usar a bateria completa "Testar adaptador" como substituto de uma consulta
mínima revisada: ela percorre a tabela de comandos de compatibilidade.

Para habilitar apenas o rastreamento de ciclo de vida ao iniciar manualmente:

```bash
sg dialout -c './venv/bin/python -' <<'PY'
import logging
from ddt4all.main import main
logger = logging.getLogger('ddt4all.core.elm.elm')
logger.setLevel(logging.DEBUG)
handler = logging.StreamHandler()
handler.setFormatter(logging.Formatter('%(asctime)s %(message)s'))
logger.addHandler(handler)
raise SystemExit(main())
PY
```

A instrumentação nova registra IDs dos objetos, tipo de adaptador, baudrate e
pilha do fechamento, sem conteúdo das consultas, VIN ou respostas. O logging
normal da aplicação é separado; não habilitar logs completos do veículo para
esta investigação.

Na repetição autorizada, registrar a ação imediatamente anterior ao erro.
Esperado: a seleção de ECU e de página mantém o mesmo ID de ELM; uma substituição
registra detach/close antes do create seguinte; saída fecha uma vez sem ATZ.
Se o fechamento reaparecer, a pilha identificará o chamador concreto. Não concluir
que ABS respondeu sem identificação e resposta válidas do próprio módulo.

Não foi validada compatibilidade física com outros adaptadores, sistemas
operacionais, estabilidade da alimentação do carro, filtragem CAN do clone ou
comportamento do painel. Os sintomas de frenagem continuam exigindo investigação
separada; a correção da conexão não constitui diagnóstico ou reparo do ABS.
