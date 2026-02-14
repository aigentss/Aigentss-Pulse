
import unittest
import sys
import os
import time
import logging

# Add parent directory to path to import prometheus_metrics
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from unittest.mock import MagicMock, patch
import prometheus_metrics

# Configure logging
logging.basicConfig(level=logging.DEBUG)

class TestContainerMetrics(unittest.TestCase):
    
    def test_cpu_percentage_calculation_with_host_cores(self):
        """
        Verify CPU % is calculated correctly relative to HOST cores.
        Scenario: 
        - Host has 24 cores (like user's VPS)
        - Container uses 2.4 seconds of CPU over a 10 second window
        - Expected: (2.4 / 10 / 24) * 100 = 1.0%
        """
        print("\n--- Testing 24-core CPU calculation ---")
        
        # Reset cache for clean test
        prometheus_metrics._DOCKER_CPU_CACHE = {}
        
        with patch('time.time') as mock_time:
            # T0
            mock_time.return_value = 1000.0
            
            # First scrape (T0)
            metrics_t0 = """
# HELP container_cpu_usage_seconds_total Cumulative cpu time consumed in seconds.
# TYPE container_cpu_usage_seconds_total counter
container_cpu_usage_seconds_total{cpu="total",id="docker-1",image="test_img",name="test_fe"} 100.0
# HELP container_memory_usage_bytes Current memory usage in bytes.
# TYPE container_memory_usage_bytes gauge
container_memory_usage_bytes{id="docker-1",image="test_img",name="test_fe"} 52428800
"""
            # Parse T0
            print("Scraping T0...")
            prometheus_metrics._parse_container_metrics(metrics_t0, "1.2.3.4", num_cores=24)
            
            # T1 = T0 + 10 seconds
            mock_time.return_value = 1010.0
            
            # Second scrape (T1)
            # usage increased by 2.4 seconds (100.0 -> 102.4)
            metrics_t1 = """
container_cpu_usage_seconds_total{cpu="total",id="docker-1",image="test_img",name="test_fe"} 102.4
container_memory_usage_bytes{id="docker-1",image="test_img",name="test_fe"} 52428800
"""
            
            # Parse T1
            print("Scraping T1 (10s later)...")
            results = prometheus_metrics._parse_container_metrics(metrics_t1, "1.2.3.4", num_cores=24)
            
            self.assertEqual(len(results), 1)
            container = results[0]
            
            # Calculation:
            # cpu_delta = 2.4 seconds
            # time_delta = 10.0 seconds
            # cores = 24
            # fraction = 2.4 / 10.0 = 0.24 cores used
            # % of total system = (0.24 / 24) * 100 = 1.0%
            
            print(f"Result CPU: {container['cpu_percent']}%")
            self.assertEqual(container['cpu_percent'], 1.0)
            print("✅ CPU Calculation Verified for 24-core host")

    def test_memory_parsing_aggregate_selection(self):
        """
        Verify we strictly select the aggregate memory metric (fewest labels).
        User reported 1600GB memory because we were summing up multiple lines.
        """
        print("\n--- Testing Memory Metric De-duplication ---")
        
        # Mock cAdvisor output with multiple lines for same container
        metrics = """
# Aggregate line (Target) - fewest labels
container_memory_usage_bytes{id="docker-1",image="waha_img",name="waha"} 104857600

# Granular lines (Should be ignored)
container_memory_usage_bytes{id="docker-1",image="waha_img",name="waha",endpoint="http"} 2048
container_memory_usage_bytes{id="docker-1",image="waha_img",name="waha",scope="hierarchy"} 104857600
"""
        results = prometheus_metrics._parse_container_metrics(metrics, "1.2.3.4", num_cores=4)
        
        self.assertEqual(len(results), 1)
        # Should be 100 MB (104857600 bytes)
        print(f"Result Memory: {results[0]['memory_mb']} MB")
        self.assertEqual(results[0]['memory_mb'], 100.0)
        self.assertEqual(results[0]['name'], 'waha')
        print("✅ Memory Metric Selection Verified")

if __name__ == '__main__':
    unittest.main()
