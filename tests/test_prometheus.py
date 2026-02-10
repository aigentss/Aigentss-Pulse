import pytest
from prometheus_metrics import _parse_cpu_usage, _parse_memory_usage, _parse_disk_usage

def test_parse_cpu():
    metrics = (
        'node_cpu_seconds_total{cpu="0",mode="idle"} 100\n'
        'node_cpu_seconds_total{cpu="0",mode="user"} 100\n'
        'node_cpu_seconds_total{cpu="1",mode="idle"} 100\n'
        'node_cpu_seconds_total{cpu="1",mode="user"} 100\n'
    )
    # Total = 400, Idle = 200 -> Used = 50%
    assert _parse_cpu_usage(metrics) == 50.0

def test_parse_memory():
    metrics = (
        'node_memory_MemTotal_bytes 1000\n'
        'node_memory_MemAvailable_bytes 400\n'
    )
    # Used = 600/1000 = 60%
    assert _parse_memory_usage(metrics) == 60.0

def test_parse_disk():
    metrics = (
        'node_filesystem_size_bytes{mountpoint="/"} 1000\n'
        'node_filesystem_avail_bytes{mountpoint="/"} 250\n'
    )
    # Used = 750/1000 = 75%
    assert _parse_disk_usage(metrics) == 75.0
