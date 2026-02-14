
import unittest
import sys
import os
import logging
from unittest.mock import patch, MagicMock

# Add parent directory to path to import prometheus_metrics
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import prometheus_metrics

# Configure logging to see debug output
logging.basicConfig(level=logging.DEBUG)

class TestTimestampParsing(unittest.TestCase):
    
    def test_timestamp_at_end_of_line(self):
        """
        Reproduce the bug where cAdvisor appends a timestamp at the end of the line.
        Example: metric_name{labels} VALUE TIMESTAMP
        Current parser blindly takes .split()[-1], which is the timestamp.
        """
        print("\n--- Testing Timestamp Parsing Logic ---")
        
        # Scenario: Hostinger VPS cAdvisor output with timestamp
        # Value is 100MB (104857600), Timestamp is 1.77T (1771093414000)
        metrics_text = """
# HELP container_memory_usage_bytes Current memory usage in bytes.
# TYPE container_memory_usage_bytes gauge
container_memory_usage_bytes{id="docker-1",name="n8n",image="n8n:latest"} 104857600 1771093414000
"""
        # Parse with assumption of 4 cores (irrelevant for memory but required arg)
        results = prometheus_metrics._parse_container_metrics(metrics_text, "test-host", num_cores=4)
        
        self.assertEqual(len(results), 1)
        container = results[0]
        
        print(f"Parsed Memory: {container['memory_mb']} MB")
        
        # Expected: ~100 MB
        # Actual (Bug): ~1,689,040 MB (because it parsed 1771093414000 as bytes)
        
        # We verify if it parsed the Value (104857600) or the Timestamp (1771093414000)
        # 104857600 bytes = 100 MB
        # 1771093414000 bytes = 1689040 MB
        
        if container['memory_mb'] > 1000000:
            print("❌ BUG REPRODUCED: Parser took the timestamp as value!")
            self.fail(f"Parser took timestamp as value! Got {container['memory_mb']} MB instead of ~100 MB")
        else:
            print("✅ Parser correctly identified the value.")
            self.assertAlmostEqual(container['memory_mb'], 100.0, delta=1.0)

    def test_standard_format_no_timestamp(self):
        """Verify we don't break standard format (no timestamp)."""
        print("\n--- Testing Standard Format (No Timestamp) ---")
        metrics_text = """
container_memory_usage_bytes{id="docker-2",name="standard",image="img"} 209715200
"""
        results = prometheus_metrics._parse_container_metrics(metrics_text, "test-host", num_cores=4)
        self.assertEqual(len(results), 1)
        # 200 MB
        self.assertEqual(results[0]['memory_mb'], 200.0)
        print("✅ Standard format still works.")

if __name__ == '__main__':
    unittest.main()
