from datetime import datetime, timedelta
from meshtastic.serial_interface import SerialInterface
from meshtastic.tcp_interface import TCPInterface
from pubsub import pub
from random import choice
from time import time, sleep
from typing import TypedDict, Literal
import argparse
import asyncio
import json
import string
import sys


logfile = None
interface: SerialInterface | None = None


type Bandwidth      = Literal[62,125,250,500]
type SpreadFactor   = Literal[5,6,7,8,9,10,11,12]
type CodingRate     = Literal[5,6,7,8]
type Station        = Literal['A','B','C','D']

class Config(TypedDict):
    test_case_duration      : int
    test_case_padding       : int
    transmission_padding    : int
    frequency               : list[float]
    bandwidth               : list[Bandwidth]
    spread_factor           : list[SpreadFactor]
    coding_rate             : list[CodingRate]
    payload_size            : list[int]
    power                   : list[int]
    start_at                : int
    stations                : list[Station]

class RunConfig(TypedDict):
    this_station            : Station
    port                    : str
    # hostname: str

class RadioConfig(TypedDict):
    bw                      : Bandwidth
    sf                      : SpreadFactor
    cr                      : CodingRate
    freq                    : float
    pow                     : int

class CuesheetEntry(TypedDict):
    start                   : int   # Start case at T-s
    end                     : int   # End case at T-s
    between                 : int   # seconds between transmissions
    freq                    : float
    bw                      : Bandwidth
    sf                      : SpreadFactor
    cr                      : CodingRate
    pow                     : int
    size                    : int
    sender                  : Station

type Cuesheet = list[CuesheetEntry]

def prepareConfig ():
    parser = argparse.ArgumentParser(
        prog='ModulationJam',
        description='',
        epilog='',
    )

    parser = argparse.ArgumentParser(prog='ModulationJam')
    subparsers = parser.add_subparsers(help='')
    parser_a = subparsers.add_parser('run', help='')
    parser_a.add_argument('--test-case-duration', type=int, default=600, help='The total duration in seconds of each test case, including padding.')
    parser_a.add_argument('--test-case-padding', type=int, default=60, help='The number of seconds between actual execution of test cases.')
    parser_a.add_argument('--transmission-padding', type=int, default=2, help='The number of seconds between each test transmission.')
    parser_a.add_argument('--frequency', type=float, action='append', default=[], help='The frequency in MHz to center on. Set repeatedly to test multiple frequencies.')
    parser_a.add_argument('--bandwidth', type=float, action='append', choices=(62,125,250,500), default=[], help='The bandwidths in kHz to test (62 for 62.5kHz). Set repeatedly to test multiple bandwidths.')
    parser_a.add_argument('--spread-factor', type=int, action='append', choices=(5,6,7,8,9,10,11,12), default=[], help='The spread factors to test. Set repeatedly to test multiple spread factors.')
    parser_a.add_argument('--coding-rate', type=int, action='append', choices=(5,6,7,8), default=[], help='The coding rate to test. Set repeatedly to test multiple coding rates.')
    parser_a.add_argument('--payload-size', type=int, action='append', default=[], help='The total payload size to set. Set repeatedly to test multiple payload sizes. default (22,)')
    parser_a.add_argument('--power', type=int, action='append', default=[], help='The power in dBm to test. Set repeatedly to test mutliple power settings.')
    parser_a.add_argument('--start-at', type=int, default=5, help='Start at the next %Nth minute of the hour; default 5, ie starts at the next minute that is a multiple of 5.')
    parser_a.add_argument('--stations', type=str, action='append', choices=('A','B','C','D'), default=[], help='The identifiers of all participating stations..')
    parser_a.add_argument('--this-station', type=str, required=True, choices=('A','B','C','D'), help='The identifier for this station.')
    parser_a.add_argument('--port', type=str, required=False, help='The serial port of the node device.')
    # parser_a.add_argument('--hostname', type=str, required=False, help='The tcp hostname of the node device')

    cli_args = parser.parse_args(sys.argv[1:])

    LIST_DEFAULTS = {
        'frequency': [915.100],
        'bandwidth': (62,125,250,500),
        'spread_factor': (5,6,7,8,9,10,11,12),
        'coding_rate': (5,6,7,8),
        'payload_size': (40,),
        'power': (22,),
        'stations': ('A','B'),
    }

    config: Config = {
        'test_case_duration': cli_args.test_case_duration,
        'test_case_padding': cli_args.test_case_padding,
        'transmission_padding': cli_args.transmission_padding,
        'frequency': cli_args.frequency,
        'bandwidth': cli_args.bandwidth,
        'spread_factor': cli_args.spread_factor,
        'coding_rate': cli_args.coding_rate,
        'payload_size': cli_args.payload_size,
        'power': cli_args.power,
        'start_at': cli_args.start_at,
        'stations': cli_args.stations,
    }

    run_config: RunConfig = {
        'this_station': cli_args.this_station,
        'port': cli_args.port,
        # 'hostname': cli_args.hostname,
    }

    for k,v in config.items():
        if not v and k in LIST_DEFAULTS:
            config[k] = LIST_DEFAULTS[k]

    return (config, run_config)


def buildCueSheet (config: Config):
    cuesheet: Cuesheet = []
    t = 0
    num_permutations = 0
    for freq in config['frequency']:
        for bw in config['bandwidth']:
            for sf in config['spread_factor']:
                for cr in config['coding_rate']:
                    for pow in config['power']:
                        num_permutations += 1
                        for size in config['payload_size']:
                            for sender in config['stations']:
                                start_t = t
                                end_t = t + config['test_case_duration']
                                start_padding_t = int(config['test_case_padding'] / 4 * 3) # Allow more time at the start for radio changes
                                end_padding_t = int(config['test_case_padding'] / 4) # Small buffer at the end in case the stations are out of sync
                                cuesheet.append({
                                    'start': start_t + start_padding_t,                  # Start case at T-s
                                    'end': end_t - end_padding_t,                     # End case at T-s
                                    'between': config['transmission_padding'],          # seconds between transmissions
                                    'freq': freq,
                                    'bw': bw,
                                    'sf': sf,
                                    'cr': cr,
                                    'pow': pow,
                                    'size': size,
                                    'sender': sender,
                                })
                                t = end_t
    print(num_permutations, 'permutations', len(cuesheet), 'tests')
    print(t / (60.0 * 60.0), 'hours')
    return cuesheet


def log (**parts):
    if not logfile:
        raise Exception('No logfile')
    ts = time()
    msg = '\t'.join(map(lambda x: str(x), parts.values()))
    line = f'{ts}\t{msg}\n';
    print(line)
    logfile.write(json.dumps({**parts, 'ts': ts}) + '\n')


def configureRadio (conf: RadioConfig):
    if not interface:
        raise Exception('No interface connected')
    node = interface.getNode('^all')
    changed = False

    use_preset = False
    bandwidth = conf['bw']
    spread_factor = conf['sf']
    coding_rate = conf['cr']
    override_frequency = conf['freq']
    tx_power = conf['pow']
    tx_enabled = True
    hop_limit = 0

    if use_preset != node.localConfig.lora.use_preset:
        changed = True
        node.localConfig.lora.use_preset = use_preset
    if bandwidth != node.localConfig.lora.bandwidth:
        changed = True
        node.localConfig.lora.bandwidth = bandwidth
    if spread_factor != node.localConfig.lora.spread_factor:
        changed = True
        node.localConfig.lora.spread_factor = spread_factor
    if coding_rate != node.localConfig.lora.coding_rate:
        changed = True
        node.localConfig.lora.coding_rate = coding_rate
    if override_frequency != node.localConfig.lora.override_frequency:
        changed = True
        node.localConfig.lora.override_frequency = override_frequency
    if tx_power != node.localConfig.lora.tx_power:
        changed = True
        node.localConfig.lora.tx_power = tx_power
    if tx_enabled != node.localConfig.lora.tx_enabled:
        changed = True
        node.localConfig.lora.tx_enabled = tx_enabled
    if hop_limit != node.localConfig.lora.hop_limit:
        changed = True
        node.localConfig.lora.hop_limit = hop_limit

    if changed:
        node.beginSettingsTransaction()
        node.writeConfig('lora')
        node.commitSettingsTransaction()
    return changed


def reconnectRadio ():
    global interface
    if not interface:
        raise Exception('No interface connected')
    reconnected = None
    reconnected_node = None
    while not reconnected and not reconnected_node:
        try:
            reconnected = SerialInterface(interface.devPath, noNodes=True)
        except:
            pass
        sleep(1)
        if reconnected:
            reconnected_node = interface.getNode('^all')
        sleep(2)
    interface = reconnected


def onReceiveText (packet, interface):
    log(
        event       = 'received',
        packet_id   = packet['id'],
        text        = packet['decoded']['payload'].decode('utf-8'),
    )


txed = dict()
active_tx_id = None
active_tx_ms = None
def onStatus (line: str):
    global active_tx_id
    global active_tx_ms
    if 'Started Tx' in line:
        _, parts = line.split('Started Tx (id=')
        active_tx_id = parts.split(' ')[0]
        print('active_tx_id',active_tx_id)
    elif active_tx_id:
        # This assumes there is only ever one active transmission at a time (weird if not true!)
        if 'Packet TX' in line:
            active_tx_ms = line.split(':').pop().strip()
            print('active_tx_ms', active_tx_ms, active_tx_id)
        elif 'Completed sending' in line and active_tx_ms:
            active_tx_num = int(active_tx_id, 16)
            txed[active_tx_num] = int(active_tx_ms.replace('ms',''))
            print('active_tx_num', active_tx_num, active_tx_id, txed[active_tx_num])
            active_tx_id = None
            active_tx_ms = None


async def waitForTx (packet_id: int):
    print('waiting for tx', packet_id)
    s = time()
    timed_out = False
    while not packet_id in txed and not timed_out:
        # sleep(0.1)
        await asyncio.sleep(0.1)
        if time() - s > 45:
            timed_out = True
    ms = txed.pop(packet_id, None) # pop to avoid a memory leak
    if timed_out:
        print(packet_id, 'timed out')
    else:
        print(packet_id, 'sent in', ms)
    return ms


async def runCues (cuesheet: Cuesheet, run_config: RunConfig):
    t = 0
    num_packets = 0
    scenario_prefix = ''
    start = time()

    async def sendPacket (sender, size):
        if not interface:
            raise Exception('No interface connected')
        text = f'{time()},{t},{num_packets}|'
        while len(text) < size:
            text += choice(string.ascii_letters)
        print(t, sender, 'sending', text)
        packet = interface.sendText(text)
        log(event='queued',packet_id=packet.id,scenario=scenario_prefix)
        ms = await waitForTx(packet.id)
        if ms:
            log(event='sent',packet_id=packet.id,duration_ms=ms,text=text)

    while cuesheet:
        scenario = cuesheet.pop(0)
        print(scenario)
        print('configure radio')
        scenario_prefix = f'{scenario['freq']},{scenario['bw']},{scenario['sf']},{scenario['cr']},{scenario['pow']}'
        configureRadio(scenario)
        reconnectRadio()
        print('waiting for start')
        while t < scenario['start']:
            t = time() - start
            sleep(0.1)
        print('starting scenario')

        while t < scenario['end']:
            t = time() - start
            if scenario['sender'] == run_config['this_station']:
                num_packets += 1
                await sendPacket(scenario['sender'], scenario['size'])
                await asyncio.sleep(scenario['between'])
            else:
                # Wait until the next scenario and just listen
                wait_for_s = max(scenario['end'] - t,0.5)
                await asyncio.sleep(wait_for_s)
        print('scenario complete')


def sleepUntilStart (config):
    n = datetime.now()
    start_at = datetime(n.year,n.month,n.day,n.hour,n.minute) + timedelta(minutes=config['start_at'] - n.minute % config['start_at'])
    print('sleeping', start_at - datetime.now(), 'until', start_at)
    while datetime.now() < start_at:
        sleep(0.1)
    print('starting')


def main ():
    config, run_config = prepareConfig()
    global interface
    interface = SerialInterface(run_config['port'], noNodes=True) # Confirm radio is connectable
    cuesheet = buildCueSheet(config) # Do this before sleeping so the timing is displayed


    sleepUntilStart(config)

    pub.subscribe(onStatus, 'meshtastic.log')
    pub.subscribe(onReceiveText, 'meshtastic.receive.text')
    global logfile
    station = run_config['this_station']
    logfile = open('./' + station + '-' + str(time()) + '.jsonl', 'a')


    asyncio.run(runCues(cuesheet, run_config))

main()
