
import re
import math

def test_regex_parsing():
    print("Testing Regex Logic...")
    
    # regex from prometheus_metrics.py
    # match = re.search(r'\s+([\d.eE+-]+)(?:\s+\d+)?$', line)
    
    test_cases = [
        # Standard cases
        ('container_memory_usage_bytes{id="123"} 123456', 123456.0, "Standard Int"),
        ('container_memory_usage_bytes{id="123"} 1.23e+05', 123000.0, "Scientific Notation"),
        ('container_memory_usage_bytes{id="123"} 123456 1700000000000', 123456.0, "With Timestamp"),
        
        # Tricky cases
        ('container_memory_usage_bytes{id="123",image="foo"} 0', 0.0, "Zero"),
        ('container_cpu_usage_seconds_total{cpu="total"} 0.123 1700000000000', 0.123, "Float with Timestamp"),
        
        # The Problematic Case (inconsistent spacing or multiple numbers)
        # Note: cAdvisor sometimes outputs lines that act weird if split() is used blindly
        # But our regex should anchor to the end.
        
        # "Missing" value (should not match or fail gracefully)
        ('container_memory_usage_bytes{id="123"}', None, "No Value"),
        
        # The specific case the user mentioned (though they didn't give the exact string, we simulate "value then timestamp")
        ('container_memory_usage_bytes{...} 55555 1234567890', 55555.0, "Value + Timestamp"),
    ]
    
    passes = 0
    for line, expected, case_name in test_cases:
        match = re.search(r'\s+([\d.eE+-]+)(?:\s+\d+)?$', line)
        if match:
            try:
                val = float(match.group(1))
                if expected is None:
                    print(f"❌ {case_name}: Expected None, got {val}")
                elif math.isclose(val, expected, rel_tol=1e-9):
                    print(f"✅ {case_name}: {val}")
                    passes += 1
                else:
                    print(f"❌ {case_name}: Expected {expected}, got {val}")
            except ValueError:
                print(f"❌ {case_name}: ValueError parsing match '{match.group(1)}'")
        else:
            if expected is None:
                print(f"✅ {case_name}: Correctly matched nothing")
                passes += 1
            else:
                 print(f"❌ {case_name}: No match found")

    print(f"\nPassed {passes}/{len(test_cases)} tests.")

if __name__ == "__main__":
    test_regex_parsing()
