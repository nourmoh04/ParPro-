import csv
import os
import sys
import time
from datetime import datetime

import psutil


CPU_WARNING_LIMIT = 90.0
RAM_WARNING_LIMIT = 85.0
DEFAULT_INTERVAL_SECONDS = 1


def ensure_reports_folder():
    os.makedirs("reports", exist_ok=True)


def get_output_path(label):
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return os.path.join("reports", f"resource_{label}_{timestamp}.csv")


def monitor(label, interval_seconds=DEFAULT_INTERVAL_SECONDS):
    ensure_reports_folder()
    output_path = get_output_path(label)

    print("====================================")
    print("Resource Monitor Started")
    print(f"Label: {label}")
    print(f"Output CSV: {output_path}")
    print(f"CPU warning limit: {CPU_WARNING_LIMIT}%")
    print(f"RAM warning limit: {RAM_WARNING_LIMIT}%")
    print("Press CTRL + C to stop monitoring.")
    print("====================================")

    with open(output_path, mode="w", newline="", encoding="utf-8") as file:
        writer = csv.writer(file)
        writer.writerow(["timestamp", "cpu_percent", "ram_percent", "warning"])

        try:
            while True:
                cpu_percent = psutil.cpu_percent(interval=interval_seconds)
                ram_percent = psutil.virtual_memory().percent

                warnings = []

                if cpu_percent >= CPU_WARNING_LIMIT:
                    warnings.append(f"CPU >= {CPU_WARNING_LIMIT}%")

                if ram_percent >= RAM_WARNING_LIMIT:
                    warnings.append(f"RAM >= {RAM_WARNING_LIMIT}%")

                warning_text = " | ".join(warnings)

                now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

                writer.writerow([now, cpu_percent, ram_percent, warning_text])
                file.flush()

                line = f"[{now}] CPU: {cpu_percent:.1f}% | RAM: {ram_percent:.1f}%"

                if warning_text:
                    line += f"  WARNING: {warning_text}"

                print(line)

        except KeyboardInterrupt:
            print("\nMonitoring stopped.")
            print(f"Results saved to: {output_path}")


if __name__ == "__main__":
    label = "test"

    if len(sys.argv) > 1:
        label = sys.argv[1]

    monitor(label)