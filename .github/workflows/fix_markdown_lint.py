import os

def fix_markdown_file(path):
    with open(path, "r", encoding="utf-8") as f:
        lines = f.read().splitlines()

    fixed = []
    for i, line in enumerate(lines):
        if line.startswith("##") and (i == 0 or lines[i - 1].strip() != ""):
            fixed.append("")
        fixed.append(line)

    # Leerzeile vor/ nach "## Tags"
    for i in range(len(fixed)):
        if fixed[i].strip().lower() == "## tags":
            if i > 0 and fixed[i - 1].strip() != "":
                fixed.insert(i, "")
            if i + 2 < len(fixed) and fixed[i + 2].strip() != "":
                fixed.insert(i + 2, "")
            break

    # Nur eine Leerzeile am Ende
    while fixed and fixed[-1].strip() == "":
        fixed.pop()
    fixed.append("")

    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(fixed))

def fix_all_markdown_files(root_dir):
    for subdir, _, files in os.walk(root_dir):
        for file in files:
            if file.endswith(".md"):
                fix_markdown_file(os.path.join(subdir, file))

if __name__ == "__main__":
    fix_all_markdown_files(".")