"""No device paths are opened. All serial traffic is scripted in memory."""
from collections import deque
from copy import deepcopy
import json
import zipfile

import pytest
from ddt4all.diagnostics.abs_reader import (
    ABSReader, DiagnosticError, ELMLink, Frame, Profile, PROFILE_FILES,
    decode_dtcs, load_profiles, main, parse_frames, reassemble,
)


@pytest.fixture
def profile():
    return Profile('abs35', PROFILE_FILES['abs35'], {
        'ecuname': 'ABS - X95 Version 3.5', 'endian': 'Big',
        'obd': {'protocol': 'CAN', 'send_id': '740', 'recv_id': '760', 'baudrate': 500000},
        'autoidents': [{'diagversion': '8', 'supplier': '368', 'soft': '7160', 'version': '8013'}],
        'requests': [
            {'name': 'StartDiagnosticSession', 'sentbytes': '10C0'},
            {'name': 'DataRead.Identification.RenaultR2', 'sentbytes': '2180', 'minbytes': 26,
             'receivebyte_dataitems': {'DiagnosticIdentificationCode': {'firstbyte': 8},
                                       'SupplierNumber.ITG': {'firstbyte': 9},
                                       'SoftwareNumber': {'firstbyte': 17}, 'EditionNumber': {'firstbyte': 19}}},
            {'name': 'ReadDTCInformation.ReportDTC', 'sentbytes': '1902FF', 'shiftbytescount': 4}],
        'data': {'DiagnosticIdentificationCode': {'byte': True},
                 'SupplierNumber.ITG': {'bytescount': 3, 'bytesascii': True},
                 'SoftwareNumber': {'bytescount': 2}, 'EditionNumber': {'bytescount': 2},
                 'DTCDeviceIdentifier': {'lists': {'16436': 'Capteur vitesse roue AVD'}},
                 'DTCFailureType': {'lists': {'17': 'circuit short to ground'}}}})


def identification():
    data = bytearray(26)
    data[:2] = b'\x61\x80'
    data[7] = 8
    data[8:11] = b'368'
    data[16:18] = bytes.fromhex('7160')
    data[18:20] = bytes.fromhex('8013')
    return bytes(data)


def frames(payload, can_id=0x760):
    if len(payload) <= 7:
        return [Frame(can_id, bytes([len(payload)]) + payload)]
    result = [Frame(can_id, bytes([0x10 | len(payload) >> 8, len(payload) & 255]) + payload[:6])]
    for seq, offset in enumerate(range(6, len(payload), 7), 1):
        result.append(Frame(can_id, bytes([0x20 | (seq & 15)]) + payload[offset:offset + 7]))
    return result


def lines(payload, can_id=0x760):
    return [f'{frame.can_id:03X} ' + frame.data.hex(' ').upper() for frame in frames(payload, can_id)]


class FakeSerial:
    def __init__(self, script, echo=False, chunk=1):
        self.script = deque(script)
        self.echo = echo
        self.chunk = chunk
        self.pending = bytearray()
        self.writes = []
        self.closed = False

    @property
    def in_waiting(self):
        return len(self.pending)

    def write(self, data):
        assert self.script, f'Unexpected write {data!r}'
        expected, response = self.script.popleft()
        assert data == (expected + '\r').encode()
        self.writes.append(expected)
        self.pending.extend((data if self.echo else b'') + response)
        return len(data)

    def read(self, count):
        count = min(count, self.chunk)
        result = bytes(self.pending[:count])
        del self.pending[:count]
        return result

    def reset_input_buffer(self):
        self.pending.clear()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.closed = True


def reply(payload, can_id=0x760):
    return ('\r'.join(lines(payload, can_id)) + '\r>').encode()


def diagnostic_script(identity=None, dtcs=b'\x59\x02\xff\x40\x34\x11\x28', can_id=0x760):
    return [('0221800000000000', reply(identity or identification(), can_id)),
            ('031902FF00000000', reply(dtcs, can_id))]


@pytest.mark.parametrize('echo', [False, True])
@pytest.mark.parametrize('chunk', [1, 2, 64])
def test_serial_fragmentation_echo_and_prompt(echo, chunk):
    serial = FakeSerial([('ATI', b'ELM327 v1.5\r>'), ('ATE0', b'OK\r>')], echo, chunk)
    link = ELMLink(serial, 0.1)
    assert link.transact('ATI') == ['ELM327 v1.5']
    link.at_ok('ATE0')
    assert serial.writes == ['ATI', 'ATE0']


def test_read_dtcs_only_after_positive_identification(profile):
    serial = FakeSerial(diagnostic_script(), echo=True)
    result = ABSReader(ELMLink(serial), [profile]).run()
    assert result['state'] == 'confirmed'
    assert result['identity']['soft'] == '7160'
    record = result['dtcs'][0]
    assert record['dtc'] == '403411'
    assert record['description'] == 'Capteur vitesse roue AVD'
    assert record['failure_description'] == 'circuit short to ground'
    assert record['status'] == '28'
    assert record['active_status_bits'] == ['confirmedDTC', 'testFailedSinceLastClear']
    assert not any(cmd.startswith('0210') for cmd in serial.writes)


def test_empty_dtcs_require_complete_positive_response(profile):
    serial = FakeSerial(diagnostic_script(dtcs=b'\x59\x02\xff'))
    result = ABSReader(ELMLink(serial), [profile]).run()
    assert result['state'] == 'confirmed'
    assert result['dtcs'] == []


@pytest.mark.parametrize('response', [b'NO DATA\r>', b'>'])
def test_no_abs_response_is_not_no_dtcs(profile, response):
    serial = FakeSerial([('0221800000000000', response)])
    with pytest.raises(DiagnosticError) as caught:
        ABSReader(ELMLink(serial), [profile]).run()
    assert caught.value.state == 'no_communication'
    assert len(serial.writes) == 1


def test_wrong_ecu_identity_refuses_to_query_dtcs(profile):
    other = bytearray(identification())
    other[8:11] = b'999'
    serial = FakeSerial(diagnostic_script(bytes(other)))
    with pytest.raises(DiagnosticError) as caught:
        ABSReader(ELMLink(serial), [profile]).run()
    assert caught.value.state == 'identity_mismatch'
    assert len(serial.writes) == 1


def test_unknown_edition_is_not_approximate_match(profile):
    other = bytearray(identification())
    other[18:20] = bytes.fromhex('FFFF')
    with pytest.raises(DiagnosticError, match='assinaturas'):
        ABSReader(None, [profile]).identify(bytes(other))


def test_foreign_ecu_and_ignored_filter_are_rejected(profile):
    serial = FakeSerial(diagnostic_script(can_id=0x7E8))
    with pytest.raises(DiagnosticError) as caught:
        ABSReader(ELMLink(serial), [profile]).run()
    assert caught.value.state == 'wrong_origin'
    assert '7E8' in str(caught.value)
    assert len(serial.writes) == 1


def test_supplied_vin_frame_structure_complete_but_wrong_origin():
    # Same FF=0x14/CF21/CF22 structure as the supplied capture; VIN anonymized.
    payload = b'\x62\xf1\x90' + b'X' * 17
    captured = lines(payload, 0x7E8)
    with pytest.raises(DiagnosticError) as caught:
        reassemble(parse_frames(captured))
    assert caught.value.state == 'wrong_origin'
    assert reassemble(parse_frames(captured), 0x7E8) == [payload]


def test_supplied_dtc_first_frame_not_attributable_to_abs():
    captured = parse_frames(['7E8 11 07 59 02 FF 00 11 77'])
    with pytest.raises(DiagnosticError) as caught:
        reassemble(captured)
    assert caught.value.state == 'wrong_origin'
    with pytest.raises(DiagnosticError, match='6/263') as caught:
        reassemble(captured, 0x7E8)
    assert caught.value.state == 'incomplete'


def test_complete_multiframe_with_sequence_wrap():
    payload = bytes(range(200))
    assert reassemble(frames(payload)) == [payload]


@pytest.mark.parametrize('fault', ['truncated', 'sequence', 'duplicate', 'missing_first'])
def test_incomplete_multiframe(fault):
    captured = frames(identification())
    if fault == 'truncated':
        captured.pop()
    elif fault == 'sequence':
        captured[1] = Frame(0x760, b'\x22' + captured[1].data[1:])
    elif fault == 'duplicate':
        captured.insert(2, captured[1])
    else:
        captured.pop(0)
    with pytest.raises(DiagnosticError) as caught:
        reassemble(captured)
    assert caught.value.state == 'incomplete'


def test_foreign_frame_mixed_with_expected_cannot_be_silently_accepted():
    captured = frames(identification()) + frames(b'\x59\x02\xff', 0x7E8)
    with pytest.raises(DiagnosticError) as caught:
        reassemble(captured)
    assert caught.value.state == 'wrong_origin'


@pytest.mark.parametrize('nrc', [0x11, 0x22, 0x7F])
def test_negative_response(profile, nrc):
    serial = FakeSerial([('0221800000000000', reply(bytes([0x7F, 0x21, nrc])))])
    with pytest.raises(DiagnosticError) as caught:
        ABSReader(ELMLink(serial), [profile]).run()
    assert caught.value.state == 'negative_response'
    assert f'{nrc:02X}' in str(caught.value)


def test_pending_followed_by_final_reply(profile):
    response = reply(b'\x7f\x21\x78')[:-1] + reply(identification())
    serial = FakeSerial([('0221800000000000', response)])
    assert ABSReader(ELMLink(serial), [profile]).query(b'\x21\x80') == identification()


def test_pending_without_final_is_not_retried(profile):
    serial = FakeSerial([('0221800000000000', reply(b'\x7f\x21\x78'))])
    with pytest.raises(DiagnosticError) as caught:
        ABSReader(ELMLink(serial), [profile]).query(b'\x21\x80')
    assert caught.value.state == 'pending'
    assert len(serial.writes) == 1


def test_timeout_poison_link_no_second_write():
    serial = FakeSerial([('ATI', b'ELM327 v1.5\r')])
    link = ELMLink(serial, 0.001)
    with pytest.raises(DiagnosticError) as caught:
        link.transact('ATI')
    assert caught.value.state == 'timeout'
    assert 'comando: ATI' in str(caught.value)
    assert 'recebidos:' in str(caught.value)
    with pytest.raises(DiagnosticError) as caught:
        link.transact('ATI')
    assert caught.value.state == 'desynchronized'
    assert len(serial.writes) == 1


def test_identification_timeout_names_stage_without_disclosing_payload():
    serial = FakeSerial([('0221800000000000', b'private-response\r')])
    with pytest.raises(DiagnosticError) as caught:
        ELMLink(serial, 0.002).transact('0221800000000000')
    assert caught.value.state == 'timeout'
    assert 'identificação ABS (2180)' in str(caught.value)
    assert 'private-response' not in str(caught.value)


def test_late_unconsumed_response_prevents_next_command():
    serial = FakeSerial([])
    serial.pending.extend(b'760 03 59 02 FF\r>')
    with pytest.raises(DiagnosticError) as caught:
        ELMLink(serial).transact('ATI')
    assert caught.value.state == 'desynchronized'
    assert serial.writes == []


def test_two_prompts_cannot_be_reused():
    serial = FakeSerial([('ATI', b'ELM327 v1.5\r>OK\r>')], chunk=64)
    with pytest.raises(DiagnosticError) as caught:
        ELMLink(serial).transact('ATI')
    assert caught.value.state == 'desynchronized'


@pytest.mark.parametrize('bad_reply', [b'?\r>', b'NO DATA\r>', b'OK\rCAN ERROR\r>'])
def test_at_requires_unambiguous_ok(bad_reply):
    serial = FakeSerial([('ATSH740', bad_reply)])
    with pytest.raises(DiagnosticError) as caught:
        ELMLink(serial).at_ok('ATSH740')
    assert caught.value.state == 'adapter_error'


def test_ath1_failure_reports_rejection_without_vehicle_data():
    serial = FakeSerial([('ATH1', b'?\rprivate-vehicle-data\r>')])
    with pytest.raises(DiagnosticError) as caught:
        ELMLink(serial).at_ok('ATH1')
    assert 'ATH1' in str(caught.value)
    assert '"?"' in str(caught.value)
    assert 'conteúdo omitido' in str(caught.value)
    assert 'private-vehicle-data' not in str(caught.value)


@pytest.mark.parametrize('payload', [b'\x59\x02', b'\x59\x02\xff\x40', b'\x57\x00\x00'])
def test_bad_dtc_length_never_means_no_fault(profile, payload):
    with pytest.raises(DiagnosticError):
        decode_dtcs(payload, profile)


@pytest.mark.parametrize('command', [b'\x14\xff\xff\xff', b'\x11\x01', b'\x31\x01', b'\x2e\xf1\x90', b'\x3b\x14\x00'])
def test_writes_resets_actuations_and_clear_requests_blocked(profile, command):
    with pytest.raises(DiagnosticError) as caught:
        ABSReader(None, [profile]).query(command)
    assert caught.value.state == 'blocked'


def test_session_requires_explicit_ack_before_any_serial_access():
    with pytest.raises(SystemExit) as caught:
        main(['--session', '10C0'])
    assert caught.value.code == 2


def test_session_only_when_explicit(profile):
    serial = FakeSerial([diagnostic_script()[0], ('0210C00000000000', reply(b'\x50\xc0'))] + diagnostic_script())
    assert ABSReader(ELMLink(serial), [profile]).run(session=True)['state'] == 'confirmed'


def test_profiles_loaded_from_zip_without_qt_or_vehicle(profile, tmp_path, capsys):
    database = tmp_path / 'ecu.zip'
    with zipfile.ZipFile(database, 'w') as archive:
        for key, name in PROFILE_FILES.items():
            definition = deepcopy(profile.definition)
            definition['ecuname'] = key
            archive.writestr(name, json.dumps(definition))
    assert len(load_profiles(database)) == 4
    assert main(['--database', str(database), '--list']) == 0
    assert len(json.loads(capsys.readouterr().out)) == 4


@pytest.mark.parametrize('line', ['760 8 03 59 02 FF 00 00 00 00', '59 02 FF', '760 00', '760 02 59'])
def test_missing_headers_dlc_or_bad_pci_not_guessed(line):
    with pytest.raises(DiagnosticError):
        reassemble(parse_frames([line]))


def setup_script(filter_mode='cra'):
    commands = ['ATE0', 'ATL0', 'ATSP6', 'AT H1', 'ATS1', 'ATD0', 'ATAL', 'ATR1', 'ATCEA',
                'ATCAF0', 'ATCFC1', 'ATFCSH740', 'ATFCSD30000A', 'ATFCSM1',
                'ATSH740', 'ATSTFF', 'ATAT0']
    commands += ['ATCRA760'] if filter_mode == 'cra' else ['ATCF760', 'ATCM7FF']
    return [('ATI', b'ELM327 v1.5\r>')] + [(cmd, b'OK\r>') for cmd in commands] + [('ATDPN', b'6\r>')]


@pytest.mark.parametrize('filter_mode', ['cra', 'mask'])
def test_setup_and_ignored_filter_cannot_attribute_foreign_reply(profile, filter_mode):
    serial = FakeSerial(setup_script(filter_mode) + diagnostic_script(can_id=0x7E8))
    link = ELMLink(serial)
    link.configure(filter_mode)
    with pytest.raises(DiagnosticError) as caught:
        ABSReader(link, [profile]).run()
    assert caught.value.state == 'wrong_origin'
    assert '031902FF00000000' not in serial.writes
    assert serial.writes.index('ATSP6') < serial.writes.index('ATCAF0')


@pytest.mark.parametrize('response', [b'A6\r>', b'7\r>', b'?\r>'])
def test_wrong_protocol_refused_before_identification(response):
    script = setup_script()
    script[-1] = ('ATDPN', response)
    serial = FakeSerial(script)
    with pytest.raises(DiagnosticError) as caught:
        ELMLink(serial).configure()
    assert caught.value.state == 'adapter_error'
    assert len(serial.script) == 0


def test_multiple_final_responses_refused(profile):
    duplicate = reply(identification())[:-1] + reply(identification())
    serial = FakeSerial([('0221800000000000', duplicate)])
    with pytest.raises(DiagnosticError) as caught:
        ABSReader(ELMLink(serial), [profile]).run()
    assert caught.value.state == 'desynchronized'


def test_wrong_service_refused_even_on_expected_can_id(profile):
    serial = FakeSerial([('0221800000000000', reply(b'\x62\xf1\x90' + b'X' * 17))])
    with pytest.raises(DiagnosticError) as caught:
        ABSReader(ELMLink(serial), [profile]).run()
    assert caught.value.state == 'response_mismatch'


def test_cli_serial_parameters_and_close_on_failure(profile, tmp_path, monkeypatch, capsys):
    import serial as serial_module
    database = tmp_path / 'ecu.zip'
    with zipfile.ZipFile(database, 'w') as archive:
        for name in PROFILE_FILES.values():
            archive.writestr(name, json.dumps(profile.definition))
    serial = FakeSerial(setup_script() + [('0221800000000000', b'NO DATA\r>')])
    received_kwargs = {}

    def open_fake(**kwargs):
        received_kwargs.update(kwargs)
        return serial

    monkeypatch.setattr(serial_module, 'Serial', open_fake)
    assert main(['--database', str(database), '--port', '/dev/fake', '--timeout', '2']) == 2
    result = json.loads(capsys.readouterr().out)
    assert result['state'] == 'no_communication'
    assert result['dtcs'] is None
    assert received_kwargs['port'] == '/dev/fake'
    assert received_kwargs['baudrate'] == 38400
    assert received_kwargs['timeout'] <= 0.05
    assert received_kwargs['rtscts'] is False
    assert serial.closed


def test_session_not_sent_when_identity_unverified(profile):
    serial = FakeSerial([('0221800000000000', reply(identification(), 0x7E8))])
    with pytest.raises(DiagnosticError):
        ABSReader(ELMLink(serial), [profile]).run(session=True)
    assert serial.writes == ['0221800000000000']


def test_dtcs_from_foreign_ecu_after_valid_identification_still_refused(profile):
    script = diagnostic_script()
    script[-1] = ('031902FF00000000', reply(b'\x59\x02\xff', 0x7E8))
    with pytest.raises(DiagnosticError) as caught:
        ABSReader(ELMLink(FakeSerial(script)), [profile]).run()
    assert caught.value.state == 'wrong_origin'


def test_late_fragmented_bytes_with_whitespace_prefix_refused():
    serial = FakeSerial([])
    serial.pending.extend(b'\r\n760 03 59 02 FF\r>')
    with pytest.raises(DiagnosticError) as caught:
        ELMLink(serial).transact('ATI')
    assert caught.value.state == 'desynchronized'
    assert serial.writes == []


def test_stale_can_reply_mixed_with_ati_not_accepted():
    serial = FakeSerial([('ATI', b'760 03 59 02 FF\rELM327 v1.5\r>')])
    with pytest.raises(DiagnosticError) as caught:
        ELMLink(serial).configure()
    assert caught.value.state == 'adapter_error'
    assert serial.writes == ['ATI']


def test_identification_remains_distinct_from_incomplete_dtcs(profile):
    script = diagnostic_script()
    script[-1] = ('031902FF00000000', b'760 11 07 59 02 FF 00 11 77\r>')
    reader = ABSReader(ELMLink(FakeSerial(script)), [profile])
    with pytest.raises(DiagnosticError) as caught:
        reader.run()
    assert caught.value.state == 'incomplete'
    assert reader.confirmed_identity['profile'] == 'abs35'


@pytest.mark.parametrize('gap,expected', [(0, ['?']), (0.05, ['OK'])])
def test_clone_requires_recovery_time_after_protocol_prompt(monkeypatch, gap, expected):
    from types import SimpleNamespace
    import ddt4all.diagnostics.abs_reader as module
    clock = SimpleNamespace(now=0.0)
    waits = []

    def sleep(seconds):
        waits.append(seconds)
        clock.now += seconds

    monkeypatch.setattr(module, 'time', SimpleNamespace(monotonic=lambda: clock.now, sleep=sleep))

    class SlowInterpreter(FakeSerial):
        def write(self, data):
            if data == b'ATSP6\r':
                self.protocol_prompt_at = clock.now
            elif data == b'AT H1\r':
                accepted = clock.now - self.protocol_prompt_at >= 0.02
                self.script[0] = ('AT H1', b'OK\r>' if accepted else b'?\r>')
            return super().write(data)

    serial = SlowInterpreter([('ATSP6', b'OK\r>'), ('AT H1', b'OK\r>')])
    link = ELMLink(serial, command_gap=gap)
    assert link.transact('ATSP6') == ['OK']
    assert link.transact('AT H1') == expected
    assert serial.writes == ['ATSP6', 'AT H1']  # No retry or blank CR.
    assert sum(waits) == gap


def test_adapter_padding_sends_same_read_requests_without_explicit_zeros(profile):
    script = [('022180', reply(identification())),
              ('031902FF', reply(b'\x59\x02\xff'))]
    serial = FakeSerial(script)
    result = ABSReader(ELMLink(serial, command_gap=0), [profile], padding='adapter').run()
    assert result['state'] == 'confirmed'
    assert result['dtcs'] == []
    assert serial.writes == ['022180', '031902FF']


def test_adapter_padding_timeout_identifies_request():
    serial = FakeSerial([('022180', b'')])
    with pytest.raises(DiagnosticError) as caught:
        ELMLink(serial, timeout=0.001).transact('022180')
    assert 'identificação ABS (2180)' in str(caught.value)
    assert 'comando: 022180' in str(caught.value)


def test_adapter_padding_still_blocks_foreign_origin(profile):
    serial = FakeSerial([('022180', reply(identification(), 0x7E8))])
    with pytest.raises(DiagnosticError) as caught:
        ABSReader(ELMLink(serial), [profile], padding='adapter').run()
    assert caught.value.state == 'wrong_origin'
    assert serial.writes == ['022180']


def test_timeout_distinguishes_echo_from_final_response():
    serial = FakeSerial([('022180', b'')], echo=True)
    with pytest.raises(DiagnosticError) as caught:
        ELMLink(serial, timeout=0.002).transact('022180')
    assert caught.value.state == 'timeout'
    assert 'eco do comando: sim' in str(caught.value)


def test_echo_setup_changes_only_adapter_echo_setting():
    script = setup_script()
    script[1] = ('ATE1', b'OK\r>')
    serial = FakeSerial(script, echo=True)
    ELMLink(serial, command_gap=0).configure(echo=True)
    assert serial.writes[1] == 'ATE1'
    assert not any(command[0].isdigit() for command in serial.writes)
