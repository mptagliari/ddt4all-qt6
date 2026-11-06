"""Read-only Fluence ABS reader. No hardware is accessed on import or --list.

Only two ECU requests are allowed: identification 2180 and DTC read 1902FF.
An optional, explicit 10C0 session change is NOT part of the default operation.
"""
import argparse
from dataclasses import dataclass
import json
import math
from pathlib import Path
import re
import sys
import time
import zipfile


PROFILE_FILES = {
    'abs23': 'ABS___X95_Version_2.3.json',
    'abs35': 'ABS___X95_Version_3.5_20101102T102139.json',
    'esc-ev': 'ESC_HSA_L38_EV_Version_1.0_20110406T151732.json',
    'esp-hsa': 'ESP___X95_HSA_1.0.json',
}
STATUS_BITS = (
    'testFailed', 'testFailedThisOperationCycle', 'pendingDTC', 'confirmedDTC',
    'testNotCompletedSinceLastClear', 'testFailedSinceLastClear',
    'testNotCompletedThisOperationCycle', 'warningIndicatorRequested',
)
NRC = {0x11: 'serviceNotSupported', 0x12: 'subFunctionNotSupported',
       0x13: 'incorrectMessageLengthOrInvalidFormat', 0x21: 'busyRepeatRequest',
       0x22: 'conditionsNotCorrect', 0x31: 'requestOutOfRange',
       0x33: 'securityAccessDenied', 0x78: 'responsePending',
       0x7E: 'subFunctionNotSupportedInActiveSession',
       0x7F: 'serviceNotSupportedInActiveSession'}


class DiagnosticError(Exception):
    def __init__(self, state, message):
        super().__init__(message)
        self.state = state


@dataclass
class Profile:
    key: str
    filename: str
    definition: dict

    @property
    def name(self):
        return self.definition['ecuname']

    @property
    def requests(self):
        return {r['name']: r for r in self.definition['requests']}

    def request(self, name, expected):
        request = self.requests[name]
        if request['sentbytes'].upper() != expected:
            raise DiagnosticError('definition_error', 'Request da base não corresponde à allowlist.')
        return request

    def summary(self):
        return {'profile': self.key, 'name': self.name, 'file': self.filename,
                **self.definition['obd'], 'identification': '2180', 'dtc_read': '1902FF',
                'session_default': 'none', 'session_optional': '10C0',
                'autoidents': self.definition['autoidents']}


def load_profiles(database):
    """Load exactly the four reviewed definitions; never execute database content."""
    profiles = []
    with zipfile.ZipFile(database) as archive:
        for key, filename in PROFILE_FILES.items():
            definition = json.loads(archive.read(filename))
            profile = Profile(key, filename, definition)
            obd = definition['obd']
            if (obd['protocol'], obd['send_id'], obd['recv_id'], obd['baudrate']) != (
                    'CAN', '740', '760', 500000) or definition.get('endian') != 'Big':
                raise DiagnosticError('definition_error', 'Endereçamento ou endian da base não revisado.')
            profile.request('DataRead.Identification.RenaultR2', '2180')
            profile.request('StartDiagnosticSession', '10C0')
            dtc_request = profile.request('ReadDTCInformation.ReportDTC', '1902FF')
            if dtc_request.get('shiftbytescount') != 4:
                raise DiagnosticError('definition_error', 'Formato DTC da base não revisado.')
            profiles.append(profile)
    return profiles


class ELMLink:
    """One command, one complete prompt. A timeout permanently poisons this link.

    Never send a blank CR (ELM repeats the previous command). Never discard late
    replies and continue: they might otherwise be mistaken for a new response.
    """
    def __init__(self, serial_port, timeout=3.0, command_gap=0.05):
        if not math.isfinite(timeout) or timeout <= 0:
            raise ValueError('timeout must be positive')
        if not math.isfinite(command_gap) or not 0 <= command_gap <= 1:
            raise ValueError('command_gap must be 0..1 seconds')
        self.command_gap = command_gap
        self._last_prompt = None
        self.serial = serial_port
        self.timeout = timeout
        self.synchronized = True

    def transact(self, command):
        if not self.synchronized:
            raise DiagnosticError('desynchronized', 'Link perdeu sincronismo; feche e reinicie a ferramenta.')
        try:
            if self._last_prompt is not None:
                remaining = self.command_gap - (time.monotonic() - self._last_prompt)
                if remaining > 0:
                    time.sleep(remaining)
            pending = bytearray()
            drain_deadline = time.monotonic() + self.timeout
            while self.serial.in_waiting:
                pending.extend(self.serial.read(min(self.serial.in_waiting, 4096)))
                if len(pending) > 65536 or time.monotonic() >= drain_deadline:
                    raise DiagnosticError('desynchronized', 'Fluxo pendente antes da consulta; operação cancelada.')
            if pending.strip():
                raise DiagnosticError('desynchronized', 'Bytes pendentes antes da consulta; operação cancelada.')
            self.serial.write((command + '\r').encode('ascii'))
            deadline = time.monotonic() + self.timeout
            received = bytearray()
            while time.monotonic() < deadline:
                count = max(1, min(self.serial.in_waiting, 4096))
                received.extend(self.serial.read(count))
                if len(received) > 65536:
                    raise DiagnosticError('adapter_error', 'Resposta excede limite do leitor.')
                if b'>' in received:
                    body, trailing = bytes(received).split(b'>', 1)
                    if trailing.strip():
                        raise DiagnosticError('desynchronized', 'Mais de uma resposta no mesmo prompt.')
                    self._last_prompt = time.monotonic()
                    normalized = command.replace(' ', '').upper()
                    lines = [line.strip() for line in body.decode('ascii').replace('\r', '\n').split('\n')]
                    return [line for line in lines if line and line.replace(' ', '').upper() != normalized]
            compact = command.replace(' ', '').upper()
            echo = any(line.replace(b' ', b'').upper() == compact.encode('ascii')
                       for line in bytes(received).replace(b'\n', b'\r').split(b'\r'))
            stage = ('identificação ABS (2180)' if compact in {'022180', '0221800000000000'} else
                     'leitura DTC (1902FF)' if compact in {'031902FF', '031902FF00000000'} else
                     'mudança de sessão (10C0)' if compact in {'0210C0', '0210C00000000000'} else
                     'configuração/identificação do adaptador' if compact.startswith('AT') else
                     'comando não identificado')
            # Only report allowlisted requests/AT text, never response payloads.
            known_request = compact in {'022180', '031902FF', '0210C0', '0221800000000000', '031902FF00000000', '0210C00000000000'}
            safe_command = command if known_request else compact if re.fullmatch(r'AT[A-Z0-9@ ]{1,24}', compact) else '<omitido>'
            raise DiagnosticError(
                'timeout', f'Timeout aguardando prompt >; etapa: {stage}; comando: {safe_command}; '
                f'recebidos: {len(received)} bytes; eco do comando: {"sim" if echo else "não"}; '
                f'limite: {self.timeout:g} s. '
                'Nenhuma conclusão sobre DTCs.')
        except (DiagnosticError, OSError, UnicodeError):
            self.synchronized = False
            raise

    def at_ok(self, command):
        response = self.transact(command)
        if response != ['OK']:
            self.synchronized = False
            # Stray vehicle data must not become diagnostic log output.
            safe_tokens = {'OK', '?', 'NO DATA', 'ERROR', 'CAN ERROR', 'BUS ERROR',
                           'BUS BUSY', 'BUFFER FULL', 'STOPPED', 'UNABLE TO CONNECT'}
            summary = [line if line.upper() in safe_tokens else
                       f'<resposta não reconhecida: {len(line)} caracteres; conteúdo omitido>'
                       for line in response]
            raise DiagnosticError(
                'adapter_error', 'Comando AT recusado ou resposta ambígua: ' + command
                + '; resposta: ' + json.dumps(summary, ensure_ascii=False))

    def configure(self, filter_mode='cra', stmin_ms=10, echo=False):
        if not 0 <= stmin_ms <= 127:
            raise ValueError('STmin must be 0..127 ms')
        identity = self.transact('ATI')
        if len(identity) != 1 or not re.fullmatch(r'(?:ELM327|ELS27)\b.*', identity[0], re.IGNORECASE):
            raise DiagnosticError('adapter_error', 'ATI não identifica uma interface ELM compatível.')
        # Protocol first: some clones reset formatting settings on AT SP/TP.
        for command in ('ATE1' if echo else 'ATE0', 'ATL0', 'ATSP6', 'AT H1', 'ATS1', 'ATD0', 'ATAL', 'ATR1', 'ATCEA',
                        'ATCAF0', 'ATCFC1', 'ATFCSH740', f'ATFCSD3000{stmin_ms:02X}', 'ATFCSM1',
                        'ATSH740', 'ATSTFF', 'ATAT0'):
            self.at_ok(command)
        if filter_mode == 'cra':
            self.at_ok('ATCRA760')
        elif filter_mode == 'mask':
            self.at_ok('ATCF760')
            self.at_ok('ATCM7FF')
        else:
            raise ValueError('invalid filter mode')
        if self.transact('ATDPN') != ['6']:
            raise DiagnosticError('adapter_error', 'Protocolo 6 fixo não confirmado pelo adaptador.')


@dataclass(frozen=True)
class Frame:
    can_id: int
    data: bytes


def parse_frames(lines):
    frames = []
    for line in lines:
        upper = line.upper()
        if upper == 'SEARCHING...':
            continue
        if upper == 'NO DATA':
            raise DiagnosticError('no_communication', 'NO DATA: sem resposta, não significa ausência de falhas.')
        if any(word in upper for word in ('ERROR', 'STOPPED', 'UNABLE', 'BUS BUSY', 'BUFFER FULL', '?')):
            raise DiagnosticError('adapter_error', 'Erro reportado pelo adaptador: ' + upper)
        compact = re.sub(r'\s+', '', upper)
        if not re.fullmatch(r'[0-9A-F]{5,19}', compact) or (len(compact) - 3) % 2:
            raise DiagnosticError('format_error', 'Quadro sem cabeçalho CAN/PCI válido; CAF0/H1/D0 não comprovados.')
        can_id = int(compact[:3], 16)
        data = bytes.fromhex(compact[3:])
        if can_id > 0x7FF or not 1 <= len(data) <= 8:
            raise DiagnosticError('format_error', 'Quadro não é CAN clássico de 11 bits.')
        frames.append(Frame(can_id, data))
    if not frames:
        raise DiagnosticError('no_communication', 'Prompt recebido sem quadros CAN.')
    return frames


def reassemble(frames, expected_id=0x760):
    """Strict classic ISO-TP normal addressing; collect complete messages only."""
    foreign = sorted({frame.can_id for frame in frames if frame.can_id != expected_id})
    if foreign:
        raise DiagnosticError('wrong_origin', 'Recebido CAN ' + ', '.join(f'{x:03X}' for x in foreign)
                              + f'; esperado {expected_id:03X}. DTCs não atribuídos ao ABS.')
    messages = []
    payload = None
    length = 0
    sequence = 1
    for frame in frames:
        data = frame.data
        kind = data[0] >> 4
        if kind == 0:
            if payload is not None:
                raise DiagnosticError('incomplete', 'Single Frame interrompeu resposta multiframe.')
            size = data[0] & 15
            if not 1 <= size <= 7 or len(data) < size + 1:
                raise DiagnosticError('incomplete', 'Comprimento inválido de Single Frame.')
            messages.append(data[1:1 + size])
        elif kind == 1:
            if payload is not None or len(data) != 8:
                raise DiagnosticError('incomplete', 'First Frame truncado ou duplicado.')
            length = ((data[0] & 15) << 8) | data[1]
            if not 8 <= length <= 4095:
                raise DiagnosticError('format_error', 'Comprimento First Frame não suportado.')
            payload = bytearray(data[2:])
            sequence = 1
        elif kind == 2:
            if payload is None or (data[0] & 15) != sequence:
                raise DiagnosticError('incomplete', 'Consecutive Frame sem início ou sequência incorreta.')
            remaining = length - len(payload)
            needed = min(7, remaining)
            if len(data) < needed + 1:
                raise DiagnosticError('incomplete', 'Consecutive Frame truncado.')
            payload.extend(data[1:1 + needed])
            sequence = (sequence + 1) & 15
            if len(payload) == length:
                messages.append(bytes(payload))
                payload = None
        else:
            raise DiagnosticError('format_error', 'PCI inesperado; formatação ou transporte não confirmado.')
    if payload is not None:
        raise DiagnosticError('incomplete', f'ISO-TP incompleto: {len(payload)}/{length} bytes. Sem DTCs conclusivos.')
    return messages


class ABSReader:
    def __init__(self, link, profiles, padding='explicit'):
        if padding not in {'explicit', 'adapter'}:
            raise ValueError('invalid padding mode')
        self.padding = padding
        self.link = link
        self.profiles = profiles
        self.confirmed_identity = None

    def query(self, request):
        allowed = (b'\x21\x80', b'\x19\x02\xff', b'\x10\xc0')
        if request not in allowed:
            raise DiagnosticError('blocked', 'Request não pertence à allowlist do leitor.')
        # All allowed requests fit a classic CAN Single Frame. No functional 7DF.
        frame = bytes([len(request)]) + request
        if self.padding == 'explicit':
            frame = frame.ljust(8, b'\x00')
        command = frame.hex().upper()
        messages = reassemble(parse_frames(self.link.transact(command)))
        finals = []
        for response in messages:
            if response[:1] == b'\x7f':
                if len(response) != 3 or response[1] != request[0]:
                    raise DiagnosticError('response_mismatch', 'Resposta negativa não corresponde ao request.')
                if response[2] == 0x78:
                    continue  # Accept a final reply already present before the same prompt.
                code = response[2]
                raise DiagnosticError('negative_response', f'NRC {code:02X}: {NRC.get(code, "desconhecido")}.')
            positive_prefix = (bytes([request[0] + 0x40]) + request[1:]
                               if request[0] != 0x19 else b'\x59\x02')
            if not response.startswith(positive_prefix):
                raise DiagnosticError('response_mismatch', 'Serviço ou identificador da resposta não corresponde à consulta.')
            finals.append(response)
        if not finals:
            raise DiagnosticError('pending', 'Somente responsePending; resposta final não recebida, sem repetição automática.')
        if len(finals) != 1:
            raise DiagnosticError('desynchronized', 'Respostas finais duplicadas/ambíguas; atribuição recusada.')
        return finals[0]

    def identify(self, response):
        matches = []
        for profile in self.profiles:
            request = profile.request('DataRead.Identification.RenaultR2', '2180')
            if len(response) < request['minbytes'] or response[:2] != b'\x61\x80':
                continue
            fields = {}
            for field, output in (('DiagnosticIdentificationCode', 'diagversion'),
                                  ('SupplierNumber.ITG', 'supplier'),
                                  ('SoftwareNumber', 'soft'), ('EditionNumber', 'version')):
                item = request['receivebyte_dataitems'][field]
                data_type = profile.definition['data'][field]
                offset = item['firstbyte'] - 1
                size = data_type.get('bytescount', 1)
                value = response[offset:offset + size]
                if len(value) != size:
                    raise DiagnosticError('incomplete', 'Identificação não contém os campos exigidos pela base.')
                if output == 'diagversion':
                    fields[output] = str(int.from_bytes(value, 'big'))
                elif data_type.get('bytesascii'):
                    try:
                        fields[output] = value.decode('ascii').strip()
                    except UnicodeError:
                        raise DiagnosticError('identity_mismatch', 'Fornecedor não é ASCII válido.') from None
                else:
                    fields[output] = value.hex().upper()
            if any(all(str(expected[k]).upper() == fields[k].upper() for k in fields)
                   for expected in profile.definition['autoidents']):
                matches.append((profile, fields))
        if len(matches) != 1:
            raise DiagnosticError('identity_mismatch', 'Identificação não corresponde unicamente às assinaturas ABS/ESP selecionadas.')
        return matches[0]

    def run(self, session=False):
        profile, identity = self.identify(self.query(b'\x21\x80'))
        if session:
            self.query(b'\x10\xc0')
            second_profile, second_identity = self.identify(self.query(b'\x21\x80'))
            if second_profile.key != profile.key or second_identity != identity:
                raise DiagnosticError('identity_mismatch', 'Identificação mudou após a troca de sessão.')
        self.confirmed_identity = {'profile': profile.key, 'ecu': profile.name,
                                   'rx_id': '760', 'identity': identity}
        response = self.query(b'\x19\x02\xff')
        return {'state': 'confirmed', **self.confirmed_identity, **decode_dtcs(response, profile)}


def decode_dtcs(payload, profile):
    if len(payload) < 3 or payload[:2] != b'\x59\x02' or (len(payload) - 3) % 4:
        raise DiagnosticError('incomplete', 'Lista DTC não contém cabeçalho e registros completos de 4 bytes.')
    mask = payload[2]
    data = profile.definition['data']
    descriptions = data['DTCDeviceIdentifier'].get('lists', {})
    obd_descriptions = data.get('DTCDeviceAndFailureTypeOBD', {}).get('lists', {})
    failure_types = data['DTCFailureType'].get('lists', {})
    records = []
    for offset in range(3, len(payload), 4):
        record = payload[offset:offset + 4]
        device = int.from_bytes(record[:2], 'big')
        failure = record[2]
        status = record[3]
        records.append({'dtc': record[:3].hex().upper(), 'device': f'{device:04X}',
                        'failure_type': f'{failure:02X}',
                        'description': descriptions.get(str(device)) or (obd_descriptions.get(str(device)) if failure == 0 else None),
                        'failure_description': failure_types.get(str(failure)),
                        'status': f'{status:02X}',
                        'active_status_bits': [label for bit, label in enumerate(STATUS_BITS) if status & mask & (1 << bit)]})
    return {'status_availability_mask': f'{mask:02X}', 'dtcs': records,
            'conclusion': 'DTCs lidos do módulo identificado.' if records else
                          'Resposta válida do módulo identificado: nenhum DTC retornado para máscara FF.'}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database', type=Path, default=Path('ecu.zip'))
    parser.add_argument('--profile', choices=['auto', *PROFILE_FILES], default='auto')
    parser.add_argument('--list', action='store_true', help='Inspeciona a base, sem abrir serial.')
    parser.add_argument('--port', default='/dev/ttyUSB0')
    parser.add_argument('--baudrate', type=int, default=38400)
    parser.add_argument('--timeout', type=float, default=3.0)
    parser.add_argument('--echo', action='store_true', help='Habilita eco serial para investigar recebimento do comando.')
    parser.add_argument('--padding', choices=['explicit', 'adapter'], default='explicit',
                        help='Preenchimento enviado pelo leitor ou delegado ao ELM em CAF0.')
    parser.add_argument('--command-gap-ms', type=float, default=50,
                        help='Intervalo após prompt: 0..1000 ms; padrão 50 para clones.')
    parser.add_argument('--filter', choices=['cra', 'mask'], default='cra')
    parser.add_argument('--stmin-ms', type=int, default=10, help='Separação ISO-TP solicitada: 0..127 ms; padrão 10.')
    parser.add_argument('--session', choices=['none', '10C0'], default='none',
                        help='10C0 muda sessão: exige --ack-session-change. Não é executado por padrão.')
    parser.add_argument('--ack-session-change', action='store_true')
    args = parser.parse_args(argv)
    if not math.isfinite(args.timeout) or args.timeout <= 0 or args.baudrate <= 0:
        parser.error('timeout e baudrate devem ser positivos')
    if not math.isfinite(args.command_gap_ms) or not 0 <= args.command_gap_ms <= 1000:
        parser.error('command-gap-ms deve estar entre 0 e 1000')
    if not 0 <= args.stmin_ms <= 127:
        parser.error('stmin-ms deve estar entre 0 e 127')
    if args.session != 'none' and not args.ack_session_change:
        parser.error('Leia a análise de sessão na documentação antes de usar --ack-session-change.')
    reader = None
    try:
        profiles = load_profiles(args.database)
        if args.profile != 'auto':
            profiles = [p for p in profiles if p.key == args.profile]
        if args.list:
            print(json.dumps([p.summary() for p in profiles], ensure_ascii=False, indent=2))
            return 0
        import serial  # No serial/USB/Qt detection at import time.
        kwargs = {'port': args.port, 'baudrate': args.baudrate, 'timeout': min(args.timeout, 0.05),
                  'write_timeout': args.timeout, 'rtscts': False, 'dsrdtr': False, 'xonxoff': False}
        if sys.platform.startswith('linux'):
            kwargs['exclusive'] = True
        with serial.Serial(**kwargs) as connection:
            connection.reset_input_buffer()  # Only once, before our first command.
            link = ELMLink(connection, args.timeout, args.command_gap_ms / 1000)
            link.configure(args.filter, args.stmin_ms, echo=args.echo)
            reader = ABSReader(link, profiles, padding=args.padding)
            result = reader.run(args.session == '10C0')
    except DiagnosticError as error:
        result = {'state': error.state, 'message': str(error), 'dtcs': None,
                  'identification_confirmed': reader.confirmed_identity if reader else None}
    except (OSError, ValueError, KeyError, zipfile.BadZipFile) as error:
        result = {'state': 'transport_or_definition_error', 'message': str(error), 'dtcs': None}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result['state'] == 'confirmed' else 2


if __name__ == '__main__':
    raise SystemExit(main())
