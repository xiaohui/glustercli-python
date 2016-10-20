# -*- coding: utf-8 -*-
#
#  Copyright (c) 2016 Red Hat, Inc. <http://www.redhat.com>
#  This file is part of GlusterFS.
#
#  This file is licensed to you under your choice of the GNU Lesser
#  General Public License, version 3 or any later version (LGPLv3 or
#  later), or the GNU General Public License, version 2 (GPLv2), in all
#  cases as published by the Free Software Foundation.
#
import xml.etree.cElementTree as etree

ParseError = etree.ParseError if hasattr(etree, 'ParseError') else SyntaxError


class GlusterCmdOutputParseError(Exception):
    pass


def _parse_a_vol(volume_el):
    value = {
        'name': volume_el.find('name').text,
        'uuid': volume_el.find('id').text,
        'type': volume_el.find('typeStr').text.upper().replace('-', '_'),
        'status': volume_el.find('statusStr').text,
        'num_bricks': int(volume_el.find('brickCount').text),
        'distribute': int(volume_el.find('distCount').text),
        'stripe': int(volume_el.find('stripeCount').text),
        'replica': int(volume_el.find('replicaCount').text),
        'transport': volume_el.find('transport').text,
        'bricks': [],
        'options': []
    }

    if value['transport'] == '0':
        value['transport'] = 'TCP'
    elif value['transport'] == '1':
        value['transport'] = 'RDMA'
    else:
        value['transport'] = 'TCP,RDMA'

    for b in volume_el.findall('bricks/brick'):
        value['bricks'].append({"name": b.find("name").text,
                                "uuid": b.find("hostUuid").text})

    for o in volume_el.findall('options/option'):
        value['options'].append({"name": o.find('name').text,
                                 "value": o.find('value').text})

    return value


def parse_volume_info(info):
    tree = etree.fromstring(info)
    volumes = []
    for el in tree.findall('volInfo/volumes/volume'):
        try:
            volumes.append(_parse_a_vol(el))
        except (ParseError, AttributeError, ValueError) as e:
            raise GlusterCmdOutputParseError(e)

    return volumes


def _parse_a_node(node_el):
    brick_path = (node_el.find('hostname').text + ":" +
                  node_el.find('path').text)
    value = {
        'name': brick_path,
        'uuid': node_el.find('peerid').text,
        'online': True if node_el.find('status').text == "1" else False,
        'pid': node_el.find('pid').text,
        'size_total': node_el.find('sizeTotal').text,
        'size_free': node_el.find('sizeFree').text,
        'device': node_el.find('device').text,
        'block_size': node_el.find('blockSize').text,
        'mnt_options': node_el.find('mntOptions').text,
        'fs_name': node_el.find('fsName').text,
        'ports': {
            "tcp": node_el.find('ports').find("tcp").text,
            "rdma": node_el.find('ports').find("rdma").text
        }
    }

    return value


def _parse_volume_status(data):
    tree = etree.fromstring(data)
    nodes = []
    for el in tree.findall('volStatus/volumes/volume/node'):
        try:
            nodes.append(_parse_a_node(el))
        except (ParseError, AttributeError, ValueError) as e:
            raise GlusterCmdOutputParseError(e)

    return nodes


def parse_volume_status(status_data, volinfo):
    nodes_data = _parse_volume_status(status_data)
    tmp_brick_status = {}
    for node in nodes_data:
        tmp_brick_status[node["name"]] = node

    volumes = []
    for v in volinfo:
        volumes.append(v.copy())
        volumes[-1]["bricks"] = []

        for b in v["bricks"]:
            brick_status_data = tmp_brick_status.get(b["name"], None)
            if brick_status_data is None:
                # Default Status
                volumes[-1]["bricks"].append({
                    "name": b["name"],
                    "uuid": b["uuid"],
                    "online": False,
                    "ports": {"tcp": "N/A", "rdma": "N/A"},
                    "pid": "N/A",
                    "size_total": "N/A",
                    "size_free": "N/A",
                    "device": "N/A",
                    "block_size": "N/A",
                    "mnt_options": "N/A",
                    "fs_name": "N/A"
                })
            else:
                volumes[-1]["bricks"].append(brick_status_data.copy())

    return volumes


def _parse_profile_info_clear(el):
    clear = {
        'volname': el.find('volname').text,
        'bricks': []
    }

    for b in el.findall('brick'):
        clear['bricks'].append({'brick_name': b.find('brickName').text,
                                'clear_stats': b.find('clearStats').text})

    return clear


def _bytes_size(size):
    traditional = [
        (1024**5, 'PB'),
        (1024**4, 'TB'),
        (1024**3, 'GB'),
        (1024**2, 'MB'),
        (1024**1, 'KB'),
        (1024**0, 'B')
    ]

    for factor, suffix in traditional:
        if size > factor:
            break
    return str(int(size / factor)) + suffix


def _parse_profile_block_stats(b_el):
    stats = []
    for b in b_el.findall('block'):
        size = _bytes_size(int(b.find('size').text))
        stats.append({size: {'reads': int(b.find('reads').text),
                             'writes': int(b.find('writes').text)}})
    return stats


def _parse_profile_fop_stats(fop_el):
    stats = []
    for f in fop_el.findall('fop'):
        name = f.find('name').text
        stats.append({name: {'hits': int(f.find('hits').text),
                             'max_latency': float(f.find('maxLatency').text),
                             'min_latency': float(f.find('minLatency').text),
                             'avg_latency': float(f.find('avgLatency').text),
                             }})
    return stats


def _parse_profile_bricks(brick_el):
    cumulative_block_stats = []
    cumulative_fop_stats = []
    cumulative_total_read_bytes = 0
    cumulative_total_write_bytes = 0
    cumulative_total_duration = 0

    interval_block_stats = []
    interval_fop_stats = []
    interval_total_read_bytes = 0
    interval_total_write_bytes = 0
    interval_total_duration = 0

    brick_name = brick_el.find('brickName').text

    if brick_el.find('cumulativeStats') is not None:
        cumulative_block_stats = _parse_profile_block_stats(brick_el.find('cumulativeStats/blockStats'))
        cumulative_fop_stats = _parse_profile_fop_stats(brick_el.find('cumulativeStats/fopStats'))
        cumulative_total_read_bytes = int(brick_el.find('cumulativeStats').find('totalRead').text)
        cumulative_total_write_bytes = int(brick_el.find('cumulativeStats').find('totalWrite').text)
        cumulative_total_duration = int(brick_el.find('cumulativeStats').find('duration').text)

    if brick_el.find('intervalStats') is not None:
        interval_block_stats = _parse_profile_block_stats(brick_el.find('intervalStats/blockStats'))
        interval_fop_stats = _parse_profile_fop_stats(brick_el.find('intervalStats/fopStats'))
        interval_total_read_bytes = int(brick_el.find('intervalStats').find('totalRead').text)
        interval_total_write_bytes = int(brick_el.find('intervalStats').find('totalWrite').text)
        interval_total_duration = int(brick_el.find('intervalStats').find('duration').text)

    profile_brick = {
        'brick_name': brick_name,
        'cumulative_block_stats': cumulative_block_stats,
        'cumulative_fop_stats': cumulative_fop_stats,
        'cumulative_total_read_bytes': cumulative_total_read_bytes,
        'cumulative_total_write_bytes': cumulative_total_write_bytes,
        'cumulative_total_duration': cumulative_total_duration,
        'interval_block_stats': interval_block_stats,
        'interval_fop_stats': interval_fop_stats,
        'interval_total_read_bytes': interval_total_read_bytes,
        'interval_total_write_bytes': interval_total_write_bytes,
        'interval_total_duration': interval_total_duration,
    }

    return profile_brick


def _parse_profile_info(el):
    profile = {
        'volname': el.find('volname').text,
        'bricks': []
    }

    for b in el.findall('brick'):
        profile['bricks'].append(_parse_profile_bricks(b))

    return profile


def parse_volume_profile_info(info, op):
    xml = etree.fromstring(info)
    profiles = []
    for el in xml.findall('volProfile'):
        try:
            if op == "clear":
                profiles.append(_parse_profile_info_clear(el))
            else:
                profiles.append(_parse_profile_info(el))

        except (ParseError, AttributeError, ValueError) as e:
            raise GlusterCmdOutputParseError(e)

    return profiles


def parse_volume_options(data):
    raise NotImplementedError("Volume Options")


def get_bricks(volume_info, volname):
    return volume_info[volname]["bricks"]


def parse_georep_status(data, volinfo):
    raise NotImplementedError("Georep Status")


def parse_bitrot_scrub_status(data):
    raise NotImplementedError("Bitrot Scrub Status")


def parse_rebalance_status(data):
    raise NotImplementedError("Rebalance Status")


def parse_quota_list_paths(data):
    raise NotImplementedError("Quota List Paths")


def parse_quota_list_objects(data):
    raise NotImplementedError("Quota List Objects")


def parse_georep_config(data):
    raise NotImplementedError("Georep Config")


def parse_remove_brick_status(data):
    raise NotImplementedError("Remove Brick Status")


def parse_tier_detach(data):
    raise NotImplementedError("Tier detach Status")


def parse_tier_status(data):
    raise NotImplementedError("Tier Status")


def parse_volume_list(data):
    raise NotImplementedError("Volumes List")


def parse_heal_info(data):
    raise NotImplementedError("Heal Info")


def parse_heal_statistics(data):
    raise NotImplementedError("Heal Statistics")


def parse_snapshot_status(data):
    raise NotImplementedError("Snapshot Status")


def parse_snapshot_info(data):
    raise NotImplementedError("Snapshot Info")


def parse_snapshot_list(data):
    raise NotImplementedError("Snapshot List")


def _parse_a_peer(peer):
    value = {
        'uuid': peer.find('uuid').text,
        'hostname': peer.find('hostname').text,
        'connected': peer.find('connected').text
    }

    if value['connected'] == '0':
        value['connected'] = "Disconnected"
    elif value['connected'] == '1':
        value['connected'] = "Connected"

    return value


def parse_peer_status(data):
    tree = etree.fromstring(data)
    peers = []
    for el in tree.findall('peerStatus/peer'):
        try:
            peers.append(_parse_a_peer(el))
        except (ParseError, AttributeError, ValueError) as e:
            raise GlusterCmdOutputParseError(e)

    return peers


def parse_pool_list(data):
    tree = etree.fromstring(data)
    pools = []
    for el in tree.findall('peerStatus/peer'):
        try:
            pools.append(_parse_a_peer(el))
        except (ParseError, AttributeError, ValueError) as e:
            raise GlusterCmdOutputParseError(e)

    return pools
