import os
import argparse
import re

def check_links(root_dir, report_dir):
    if not os.path.exists(report_dir):
        os.makedirs(report_dir)
    report_file = os.path.join(report_dir, "link_report.txt")
    with open(report_file, "w") as report:
        for subdir, _, files in os.walk(root_dir):
            for file in files:
                if file.endswith(".md"):
                    path = os.path.join(subdir, file)
                    with open(path, "r", encoding="utf-8") as f:
                        content = f.read()
                    links = re.findall(r'!?\[.*?\]\((.*?)\)', content)
                    for link in links:
                        if link.startswith("http"):
                            continue
                        if not os.path.exists(os.path.join(subdir, link)):
                            report.write(f"Broken link in {path}: {link}\n")
    print(f"Link report saved to {report_file}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=".")
    parser.add_argument("--report-dir", default="reports")
    args = parser.parse_args()
    check_links(args.root, args.report_dir)
