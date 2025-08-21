import os
import argparse

def extract_title(filepath):
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            lines = f.readlines()
            if lines[0].strip() == "---":
                for i in range(1, len(lines)):
                    if lines[i].strip().startswith("title:"):
                        return lines[i].strip().split(":", 1)[1].strip().strip('"')
                    if lines[i].strip() == "---":
                        break
    except Exception:
        pass
    return None

def generate_sitemap(root_dir, out_file, indexes=False):
    urls = []
    for subdir, _, files in os.walk(root_dir):
        for file in files:
            if file.endswith(".md"):
                full_path = os.path.join(subdir, file)
                rel_path = os.path.relpath(full_path, root_dir).replace(os.sep, "/")
                title = extract_title(full_path)
                if not title:
                    title = rel_path
                urls.append((title, rel_path))

    urls.sort(key=lambda x: x[1])
    with open(out_file, "w", encoding="utf-8") as f:
        f.write("# Sitemap\n\n")
        for title, path in urls:
            f.write(f"- [{title}]({path})\n")
    print(f"Sitemap generated: {out_file}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=".")
    parser.add_argument("--out", default="Sitemap.md")
    parser.add_argument("--indexes", action="store_true")
    args = parser.parse_args()
    generate_sitemap(args.root, args.out, args.indexes)
