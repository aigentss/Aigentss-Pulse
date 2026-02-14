
import unittest
from unittest.mock import MagicMock, patch
import time
import prometheus_metrics

class TestContainerMetrics(unittest.TestCase):
    
    def test_cpu_percentage_calculation_with_host_cores(self):
        """
        Verify CPU % is calculated correctly relative to HOST cores.
        Scenario: 
        - Host has 24 cores (like user's VPS)
        - Container uses 2.4 seconds of CPU over a 10 second window
        - Expected: (2.4 / 10 / 24) * 100 = 1.0%
        """
        # Mock time to control delta
        with patch('time.time') as mock_time:
            # T0
            mock_time.return_value = 1000.0
            
            # First scrape (T0)
            # container_cpu_usage_seconds_total = 100.0
            metrics_t0 = """
container_cpu_usage_seconds_total{id="docker-1",name="test_fe",cpu="total"} 100.0
container_memory_usage_bytes{id="docker-1",name="test_fe"} 50000000
"""
            # Parse T0 - should initialize cache
            prometheus_metrics._parse_container_metrics(metrics_t0, "1.2.3.4", num_cores=24)
            
            # T1 = T0 + 10 seconds
            mock_time.return_value = 1010.0
            
            # Second scrape (T1)
            # usage increased by 2.4 seconds (100.0 -> 102.4)
            metrics_t1 = """
container_cpu_usage_seconds_total{id="docker-1",name="test_fe",cpu="total"} 102.4
container_memory_usage_bytes{id="docker-1",name="test_fe"} 50000000
"""
            
            # Parse T1 - should calculate percentage
            results = prometheus_metrics._parse_container_metrics(metrics_t1, "1.2.3.4", num_cores=24)
            
            self.assertEqual(len(results), 1)
            container = results[0]
            
            # Calculation:
            # cpu_delta = 102.4 - 100.0 = 2.4 seconds
            # time_delta = 1010.0 - 1000.0 = 10.0 seconds
            # cores = 24
            # % = (2.4 / 10.0 / 24) * 100 = 1.0%
            
            print(f"\nCalculated CPU: {container['cpu_percent']}%")
            self.assertEqual(container['cpu_percent'], 1.0)
            
    def test_memory_parsing_aggregate_selection(self):
        """
        Verify we strictly select the aggregate memory metric (fewest labels).
        User reported 1600GB memory because we were summing up multiple lines.
        """
        # Mock cAdvisor output with multiple lines for same container (common behavior)
        metrics = """
# Aggregate line (Target) - fewest labels
container_memory_usage_bytes{id="docker-1",name="waha"} 104857600

# Granular lines (Should be ignored)
container_memory_usage_bytes{id="docker-1",name="waha",endpoint="http"} 2048
container_memory_usage_bytes{id="docker-1",name="waha",scope="hierarchy"} 104857600
"""
        results = prometheus_metrics._parse_container_metrics(metrics, "1.2.3.4", num_cores=4)
        
        self.assertEqual(len(results), 1)
        # Should be 100 MB (104857600 bytes)
        self.assertEqual(results[0]['memory_mb'], 100.0)
        self.assertEqual(results[0]['name'], 'waha')

if __name__ == '__main__':
    unittest.main()
